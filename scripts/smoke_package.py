"""Valida o pacote instalado fora da árvore de código, sem rede/credenciais reais."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    expected = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("METABOOKS_") and key != "PYTHONPATH"}
    with tempfile.TemporaryDirectory(prefix="metabooks-package-") as directory:
        config = Path(directory) / ".env"
        config.write_text("METABOOKS_COVER_TOKEN=smoke-placeholder\nMETABOOKS_ENABLE_UI_APP=1\n", encoding="utf-8")
        # O diagnóstico confirma leitura do .env de CWD numa instalação normal.
        diagnostic = subprocess.run([sys.executable, "-m", "metabooks_mcp.server", "--diagnose"],
                                    cwd=directory, env=env, capture_output=True, text=True, check=True)
        report = json.loads(diagnostic.stdout)
        assert report["version"] == expected
        assert report["credentials_present"]["METABOOKS_COVER_TOKEN"]
        assert "smoke-placeholder" not in diagnostic.stdout
        # Evita que a configuração do usuário participe do subprocesso MCP.
        env["METABOOKS_ENV_FILE"] = str(config)
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "metabooks_mcp.server"], cwd=directory, env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                assert info.serverInfo.version == expected
                tools = await session.list_tools()
                assert len(tools.tools) == 12
                resource = await session.read_resource("ui://metabooks/cover")
                assert "<!DOCTYPE html>" in resource.contents[0].text
                print(f"OK: pacote {expected}, 12 ferramentas, handshake stdio, .env e recurso HTML")


if __name__ == "__main__":
    asyncio.run(main())
