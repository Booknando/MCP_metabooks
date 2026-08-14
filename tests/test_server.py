"""O servidor DO PACOTE: construção, versão no handshake e schema das tools.

Estas provas existem porque um defeito real passou por uma suíte verde e por um
CI verde: `main()` construía o `FastMCP` com um argumento que o SDK não aceita
(`version=`), e nada exercitava esse caminho — o CI checava `--help` (que sai
pelo argparse antes da construção) e a suíte remontava um `FastMCP` próprio.
O servidor instalado morria com TypeError antes de registrar qualquer tool.
"""

from __future__ import annotations

import pytest

from metabooks_mcp import __version__
from metabooks_mcp.server import build_server

from .test_tools import TOOLS

pytestmark = pytest.mark.anyio


# --- construção -------------------------------------------------------------

def test_servidor_constroi():
    """Se o construtor do FastMCP recusar um argumento, o erro aparece aqui."""
    assert build_server() is not None


async def test_servidor_registra_as_doze_tools():
    tools = await build_server().list_tools()
    assert {t.name for t in tools} == TOOLS


# --- versão -----------------------------------------------------------------

def test_handshake_reporta_a_versao_do_projeto():
    """Sem isto o initialize devolve a versão do pacote `mcp`, não a do projeto.

    É o que o suporte usa para saber qual cópia o usuário está rodando — no canal
    ZIP não há gerenciador de pacotes para perguntar.
    """
    mcp = build_server()
    assert mcp._mcp_server.version == __version__
    opcoes = mcp._mcp_server.create_initialization_options()
    assert opcoes.server_version == __version__
    assert opcoes.server_name == "metabooks-mcp"


# --- schema das tools -------------------------------------------------------

async def test_todo_parametro_tem_descricao_no_schema():
    """`Annotated[x, "texto"]` com string pura é DESCARTADO pelo pydantic.

    Só `Field(description=...)` chega ao inputSchema. Sem esta prova, a sintaxe de
    busca e a explicação de cada parâmetro somem do schema sem quebrar teste
    nenhum — o modelo passa a chutar os argumentos.
    """
    sem_descricao = [
        f"{tool.name}.{nome}"
        for tool in await build_server().list_tools()
        for nome, esquema in (tool.inputSchema.get("properties") or {}).items()
        if not (esquema.get("description") or "").strip()
    ]
    assert not sem_descricao, f"parâmetros sem description no schema: {sem_descricao}"


async def test_sintaxe_de_busca_chega_ao_parametro_search():
    from metabooks_mcp.tools.produtos import SEARCH_SYNTAX

    tools = {t.name: t for t in await build_server().list_tools()}
    descricao = tools["metabooks_search_products"].inputSchema["properties"]["search"]["description"]
    assert descricao == SEARCH_SYNTAX


async def test_toda_tool_tem_descricao_propria():
    for tool in await build_server().list_tools():
        assert (tool.description or "").strip(), f"{tool.name} sem docstring"


# --- instruções -------------------------------------------------------------

def test_instructions_do_servidor_chegam_ao_cliente():
    """As instruções guiam o fluxo busca→detalhe e a desambiguação."""
    instrucoes = build_server().instructions or ""
    assert "FLUXO RECOMENDADO" in instrucoes
    assert "SINTAXE DE BUSCA" in instrucoes
