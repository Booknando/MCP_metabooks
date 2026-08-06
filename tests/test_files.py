"""Confinamento do destino de gravação (_files.resolve_target)."""

from __future__ import annotations

import os

import pytest

from metabooks_mcp.tools._files import (
    DestinationError,
    ENV_DOWNLOAD_DIR,
    allowed_roots,
    default_download_dir,
    resolve_target,
    safe_filename,
)


def test_dest_none_cai_na_raiz_permitida(downloads):
    target = resolve_target(None, "capa_123_m.jpg")
    assert target == str(downloads / "capa_123_m.jpg")


def test_dest_pasta_dentro_da_raiz(downloads):
    sub = downloads / "capas"
    sub.mkdir()
    target = resolve_target(str(sub), "capa.jpg")
    assert target == str(sub / "capa.jpg")


def test_dest_pasta_inexistente_dentro_da_raiz(downloads):
    target = resolve_target(str(downloads / "nova" / "pasta") + os.sep, "capa.jpg")
    assert target.startswith(str(downloads))


def test_dest_arquivo_dentro_da_raiz(downloads):
    target = resolve_target(str(downloads / "minha.jpg"), "capa.jpg", expected_ext="jpg")
    assert target == str(downloads / "minha.jpg")


@pytest.mark.parametrize(
    "dest",
    [
        "/etc/passwd",
        "~/.bashrc",
        "../../fora.jpg",
        "../../../../../../tmp/fora.jpg",
    ],
)
def test_recusa_destino_fora_da_raiz(downloads, dest):
    with pytest.raises(DestinationError, match="fora das pastas permitidas"):
        resolve_target(dest, "capa.jpg")


def test_recusa_travessia_ainda_que_comece_na_raiz(downloads):
    dest = str(downloads / ".." / ".." / "fora.jpg")
    with pytest.raises(DestinationError):
        resolve_target(dest, "capa.jpg")


def test_recusa_symlink_que_aponta_para_fora(downloads, tmp_path):
    if not hasattr(os, "symlink"):  # pragma: no cover - Windows sem privilégio
        pytest.skip("symlink indisponível")
    fora = tmp_path / "fora"
    fora.mkdir()
    link = downloads / "atalho"
    try:
        os.symlink(fora, link)
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("symlink indisponível")
    with pytest.raises(DestinationError):
        resolve_target(str(link / "capa.jpg"), "capa.jpg")


def test_nao_sobrescreve_sem_pedido(downloads):
    existente = downloads / "capa.jpg"
    existente.write_bytes(b"conteudo original")
    with pytest.raises(DestinationError, match="já existe"):
        resolve_target(str(existente), "capa.jpg", expected_ext="jpg")
    assert existente.read_bytes() == b"conteudo original"


def test_sobrescreve_com_overwrite(downloads):
    existente = downloads / "capa.jpg"
    existente.write_bytes(b"x")
    target = resolve_target(
        str(existente), "capa.jpg", expected_ext="jpg", overwrite=True
    )
    assert target == str(existente)


def test_extensao_e_forcada_para_o_tipo_real(downloads):
    """Um JPEG nunca deve ser gravado como .json/.py sobre um arquivo de config."""
    target = resolve_target(
        str(downloads / "claude_desktop_config.json"), "capa.jpg", expected_ext="jpg"
    )
    assert target.endswith("claude_desktop_config.json.jpg")


def test_nome_de_arquivo_higienizado(downloads):
    target = resolve_target(str(downloads / "a b;rm -rf.jpg"), "capa.jpg")
    assert os.path.basename(target) == "a_b_rm_-rf.jpg"


def test_safe_filename_remove_separadores():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("") == "arquivo"


def test_env_aceita_multiplas_raizes(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv(ENV_DOWNLOAD_DIR, os.pathsep.join([str(a), str(b)]))
    assert allowed_roots() == [str(a), str(b)]
    assert default_download_dir() == str(a)
    assert resolve_target(str(b / "x.jpg"), "capa.jpg") == str(b / "x.jpg")
