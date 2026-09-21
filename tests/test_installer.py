"""Regressões do instalador sem tocar no perfil real ou chamar a rede."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("installer", Path(__file__).parents[1] / "installer/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_merge_preserves_other_servers_and_env_file():
    original = {"theme": "dark", "mcpServers": {
        "other": {"command": "other"},
        "metabooks": {"command": "old", "args": ["--env-file", "/a b/.env"], "disabled": False}}}
    result = installer.merge_config(original, Path("/a b/python"), {"TOKEN": "secret"})
    assert result["theme"] == "dark"
    assert result["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert result["mcpServers"]["metabooks"]["args"][-2:] == ["--env-file", "/a b/.env"]
    assert original["mcpServers"]["metabooks"]["command"] == "old"


def test_backup_and_atomic_config(tmp_path):
    path = tmp_path / "Claude/config.json"
    path.parent.mkdir()
    raw = b'\xef\xbb\xbf{"mcpServers": {}, "theme": "dark"}'
    path.write_bytes(raw)
    original, config = installer.read_config(path)
    backup = installer.save_config(path, config, original)
    assert backup.read_bytes() == raw
    assert json.loads(path.read_text(encoding="utf-8")) == config


def test_concurrent_edit_is_not_overwritten(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"new": true}')
    with pytest.raises(ValueError, match="alterou"):
        installer.save_config(path, {}, b"{}")
    assert json.loads(path.read_text()) == {"new": True}


@pytest.mark.parametrize("text", ["broken", "[]", '{"mcpServers": []}'])
def test_invalid_json_untouched(tmp_path, text):
    path = tmp_path / "config.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        installer.read_config(path)
    assert path.read_text() == text


def test_failed_install_preserves_config_and_old_environment(tmp_path, monkeypatch):
    root = tmp_path / "install"
    old = root / "env-old"
    old.mkdir(parents=True)
    config = tmp_path / "config.json"
    config.write_bytes(b"{}")
    def fail(command, **kwargs):
        Path(command[-1]).mkdir()
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(installer.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install("source", root, config, {}, b"{}", {})
    assert list(root.iterdir()) == [old]
    assert config.read_bytes() == b"{}"


def test_success_checks_before_activation(tmp_path, monkeypatch):
    calls = []
    config = tmp_path / "config.json"
    def run(command, **kwargs):
        assert not config.exists()
        calls.append(command)
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install("local source", tmp_path / "install", config, {"TOKEN": "secret"}, None, {})
    assert len(calls) == 4
    entry = json.loads(config.read_text())["mcpServers"]["metabooks"]
    assert entry["env"] == {"TOKEN": "secret"}
    assert calls[1][-1] == "local source"


def test_missing_release_gives_actionable_error(monkeypatch):
    def missing(*args, **kwargs):
        raise installer.urllib.error.HTTPError("url", 404, "missing", {}, None)
    monkeypatch.setattr(installer.urllib.request, "urlopen", missing)
    with pytest.raises(ValueError, match="Ainda não há release"):
        installer.latest_source()
