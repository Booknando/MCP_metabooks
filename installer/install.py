"""Instalador guiado, somente biblioteca padrão; Python 3.12+."""
from __future__ import annotations

import argparse
import copy
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

REPO = "Booknando/MCP_metabooks"


def locations():
    if sys.platform == "win32":
        return (Path(os.environ["LOCALAPPDATA"]) / "MetabooksMCP",
                Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json")
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
        return base / "MetabooksMCP", base / "Claude/claude_desktop_config.json"
    raise ValueError("Use este instalador no Windows ou macOS.")


def read_config(path):
    raw = path.read_bytes() if path.exists() else None
    config = json.loads(raw.decode("utf-8-sig")) if raw is not None else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Configuração do Claude inválida. Corrija o JSON antes de continuar.")
    return raw, config


def merge_config(config, python, credentials):
    result = copy.deepcopy(config)
    servers = result.setdefault("mcpServers", {})
    old = servers.get("metabooks", {})
    if not isinstance(old, dict):
        raise ValueError("A entrada metabooks existente não é um objeto JSON.")
    entry = copy.deepcopy(old)
    entry.update(command=str(python), args=["-m", "metabooks_mcp.server"])
    old_args = old.get("args", [])
    if isinstance(old_args, list) and "--env-file" in old_args:
        index = old_args.index("--env-file")
        if index + 1 >= len(old_args):
            raise ValueError("--env-file existente não tem caminho.")
        entry["args"].extend(["--env-file", old_args[index + 1]])
    elif isinstance(old_args, list):
        entry["args"].extend(arg for arg in old_args if isinstance(arg, str) and arg.startswith("--env-file="))
    entry["env"] = credentials
    servers["metabooks"] = entry
    return result


def save_config(path, config, original):
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_bytes() if path.exists() else None
    if current != original:
        raise ValueError("O Claude alterou a configuração durante a instalação. Feche-o e tente novamente.")
    backup = None
    if original is not None:
        backup = path.with_name(path.name + ".backup-" + uuid.uuid4().hex)
        with backup.open("xb") as file:
            os.chmod(backup, 0o600)
            file.write(original)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".metabooks-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return backup


def latest_source():
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Metabooks-Installer"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError("Ainda não há release pública no GitHub. Baixe o ZIP da versão desejada e execute seu instalador.") from None
        raise
    tag = release["tag_name"]
    # Restrinja a origem ao repositório, sem executar conteúdo de campos da API.
    from urllib.parse import quote
    return f"https://github.com/{REPO}/archive/refs/tags/{quote(tag, safe='')}.zip"


def ask_credentials(existing):
    if not isinstance(existing, dict):
        raise ValueError("O campo env existente precisa ser um objeto JSON.")
    env = dict(existing)
    if env and input("Preservar as credenciais/configuração existentes? [S/n]: ").strip().lower() != "n":
        return env
    mode = input("Autenticação: [1] usuário/senha de produção; [2] token staging/RC (padrão 1): ").strip()
    for key in ("METABOOKS_USERNAME", "METABOOKS_PASSWORD", "METABOOKS_METADATA_TOKEN", "METABOOKS_BASE_URL"):
        env.pop(key, None)
    if mode == "2":
        env["METABOOKS_METADATA_TOKEN"] = getpass.getpass("Token de metadados: ").strip()
        base = input("Ambiente [staging/rc]: ").strip().lower()
        if base not in ("staging", "rc"):
            raise ValueError("Escolha staging ou rc.")
        env["METABOOKS_BASE_URL"] = f"https://{base}.kubernetes.br.metabooks.com/api/v2"
        required = ["METABOOKS_METADATA_TOKEN"]
    elif mode in ("", "1"):
        env["METABOOKS_USERNAME"] = input("Usuário Metabooks: ").strip()
        env["METABOOKS_PASSWORD"] = getpass.getpass("Senha Metabooks: ")
        required = ["METABOOKS_USERNAME", "METABOOKS_PASSWORD"]
    else:
        raise ValueError("Escolha 1 ou 2.")
    if any(not env[key].strip() for key in required):
        raise ValueError("As credenciais obrigatórias não podem ficar vazias.")
    for key, label in (("METABOOKS_COVER_TOKEN", "capas"), ("METABOOKS_MMO_TOKEN", "mídias")):
        token = getpass.getpass(f"Token de {label} (Enter preserva o existente ou deixa sem): ").strip()
        if token:
            env[key] = token
    return env


def install(source, root, config_path, credentials, original, config):
    root.mkdir(parents=True, exist_ok=True)
    # Não mova venvs: seus executáveis podem conter caminhos absolutos.
    environment = root / ("env-" + uuid.uuid4().hex)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    activated = False
    try:
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", source], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        subprocess.run([str(python), "-c", "from metabooks_mcp.server import build_server; build_server()"], check=True)
        updated = merge_config(config, python, credentials)
        backup = save_config(config_path, updated, original)
        activated = True
        print("Instalação concluída. Feche completamente e reabra o Claude Desktop.")
        print("Configuração:", config_path)
        if backup:
            print("Backup:", backup)
        print("Ambientes anteriores foram preservados para permitir restauração do backup.")
    finally:
        if not activated and environment.exists():
            shutil.rmtree(environment)


def main():
    parser = argparse.ArgumentParser(description="Instalar/configurar o Metabooks no Claude Desktop.")
    parser.add_argument("--update", action="store_true", help="Instalar a última release pública do GitHub preservando credenciais.")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise ValueError("Instale Python 3.12 ou mais recente em https://www.python.org/downloads/")
    root, config_path = locations()
    print("Metabooks MCP — instalação local, distribuição pelo GitHub.")
    print("Feche completamente o Claude Desktop antes de continuar.")
    print("Senhas/tokens ficam no JSON local do Claude e nos backups; não compartilhe esses arquivos.")
    input("Pressione Enter para continuar (Ctrl+C cancela): ")
    original, config = read_config(config_path)
    old = config.get("mcpServers", {}).get("metabooks", {})
    if not isinstance(old, dict) or not isinstance(old.get("env", {}), dict):
        raise ValueError("Entrada metabooks inválida na configuração do Claude.")
    if args.update:
        if not old:
            raise ValueError("Instale primeiro executando o instalador sem --update.")
        source = latest_source()
        credentials = old.get("env", {})
    else:
        source = Path(__file__).resolve().parents[1]
        if not (source / "pyproject.toml").is_file():
            raise ValueError("Extraia o ZIP completo antes de executar o instalador.")
        credentials = ask_credentials(old.get("env", {}))
    install(str(source), root, config_path, credentials, original, config)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInstalação cancelada.")
        sys.exit(1)
    except Exception as error:
        # Não imprima a configuração ou dados de autenticação.
        print(f"Falha: {error}", file=sys.stderr)
        sys.exit(1)
