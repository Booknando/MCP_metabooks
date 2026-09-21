"""Instalação real em perfil descartável, sem credenciais/API Metabooks."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", repo / "installer/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

with tempfile.TemporaryDirectory(prefix="metabooks installer ") as folder:
    root = Path(folder)
    config_path = root / "Claude/config.json"
    config_path.parent.mkdir()
    original = b'{"mcpServers": {"other": {"command": "preserve"}}, "theme": "dark"}'
    config_path.write_bytes(original)
    installer.install(str(repo), root / "environment with spaces", config_path,
                      {}, original, json.loads(original))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["mcpServers"]["other"]["command"] == "preserve"
    assert config["theme"] == "dark"
    backups = list(config_path.parent.glob("*.backup-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    python = config["mcpServers"]["metabooks"]["command"]
    subprocess.run([python, str(repo / "scripts/smoke_package.py")], check=True)
print("Instalador validado em perfil temporário, incluindo sessão MCP stdio.")
