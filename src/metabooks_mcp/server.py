"""MCP Server para integração com a API REST v2 da Metabooks."""

import argparse
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

from . import __version__
from .client import MetabooksClient
from .tools import produtos, capas, midia, indice, editora

# Busca .env no diretório atual e em ~/.config/metabooks-mcp/ (útil para uso via uvx)
load_dotenv()
load_dotenv(os.path.expanduser("~/.config/metabooks-mcp/.env"))


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    client = MetabooksClient(
        username=os.environ.get("METABOOKS_USERNAME"),
        password=os.environ.get("METABOOKS_PASSWORD"),
        metadata_token=os.environ.get("METABOOKS_METADATA_TOKEN"),
        cover_token=os.environ.get("METABOOKS_COVER_TOKEN"),
        mmo_token=os.environ.get("METABOOKS_MMO_TOKEN"),
        base_url=os.environ.get("METABOOKS_BASE_URL"),
    )
    try:
        yield {"metabooks": client}
    finally:
        # Libera o slot de login paralelo antes de encerrar (no-op para token estático).
        await client.logout()
        await client.aclose()


def build_server() -> FastMCP:
    """Monta o servidor MCP completo, com as ferramentas já registradas.

    É o ÚNICO lugar que constrói o servidor: os testes e o CI importam esta
    função em vez de remontar um ``FastMCP`` na mão. Quando remontavam, o
    caminho real de inicialização ficava sem cobertura — foi assim que um
    ``FastMCP(version=...)`` inválido passou por uma suíte verde e por um CI
    verde e só quebrou na máquina de quem instalava.
    """
    # ATENÇÃO: `FastMCP.__init__` aceita uma lista FECHADA de parâmetros — não
    # há `**settings` nem `version`. Passar `version=` aqui levanta TypeError e
    # o servidor não sobe. A versão é publicada logo abaixo, no servidor de
    # baixo nível, que é quem monta o handshake.
    mcp = FastMCP(
        name="metabooks-mcp",
        instructions=(
            "Servidor MCP somente leitura para a API REST v2 da Metabooks. "
            "Módulos disponíveis: busca de produtos no catálogo bibliográfico (busca booleana, "
            "busca em lote por ISBN), detalhe de produto por UUID/ISBN/GTIN (JSON ou ONIX 3.0), "
            "busca em índice para autocompletar, visualização/download/URL de capas, "
            "visualização/download de mídia/MMO (capas extras, miolo, sumário) e dados "
            "cadastrais de editoras. "
            "FLUXO RECOMENDADO: primeiro identifique o título com metabooks_search_products "
            "(view='compact', padrão — lista enxuta sem sinopse); só então busque o detalhe "
            "com metabooks_get_product usando o UUID/ISBN retornado. Não peça 'full' sem "
            "necessidade. "
            "SINTAXE DE BUSCA (metabooks_search_products): " + produtos.SEARCH_SYNTAX + " "
            "DESAMBIGUAÇÃO: a busca compacta marca 'titulo_exato' e pode incluir um 'aviso'. "
            "Diante de vários resultados, título parcial ou autor homônimo, APRESENTE os "
            "candidatos e PEÇA CONFIRMAÇÃO ao usuário — nunca escolha um resultado por conta "
            "própria. O campo 'total' indica quantos resultados existem: se 'mostrando' < "
            "'total', há mais páginas; não trate a página atual como a lista completa. "
            "NÃO INVENTE: reporte só o que veio na resposta. Nunca infira disponibilidade, "
            "status de publicação, preço ou nível de completude/medalha que não estejam nos "
            "campos retornados. "
            "LIMITE DA API: esta versão é somente leitura — upload de capa, edição de sinopse "
            "ou qualquer alteração NÃO são suportados; diga isso claramente em vez de simular "
            "sucesso. "
            "LINGUAGEM: os campos compactos já vêm com nomes amigáveis em português; prefira-os "
            "e evite expor códigos técnicos ONIX crus (ex.: languageRole, salesRights) ao "
            "usuário final. "
            "IMPORTANTE sobre imagens: para EXIBIR qualquer imagem na conversa use as tools "
            "'view' (metabooks_view_cover, metabooks_view_media_asset), que devolvem a imagem "
            "inline. NUNCA cole URLs de /cover ou /asset/mmo como imagem markdown — elas exigem "
            "token no cabeçalho e não abrem no navegador (resultam em 'Mostrar Imagem' quebrado). "
            "Credenciais: METABOOKS_USERNAME/METABOOKS_PASSWORD (produção) "
            "ou METABOOKS_METADATA_TOKEN (staging/rc). "
            "Capas e mídias exigem tokens dedicados: METABOOKS_COVER_TOKEN e METABOOKS_MMO_TOKEN."
        ),
        lifespan=lifespan,
    )
    # O FastMCP não repassa versão ao servidor de baixo nível, então o handshake
    # reportaria a versão do pacote `mcp` em vez da do projeto. `Server.version`
    # é público e é o que vira `serverInfo.version` no initialize.
    mcp._mcp_server.version = __version__

    produtos.register(mcp)
    capas.register(mcp)
    midia.register(mcp)
    indice.register(mcp)
    editora.register(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="metabooks-mcp",
        description=(
            "MCP Server para a API REST v2 da Metabooks.\n\n"
            "Normalmente invocado pelo Claude Desktop ou outro cliente MCP via stdio.\n\n"
            "Variáveis de ambiente necessárias:\n"
            "  METABOOKS_USERNAME / METABOOKS_PASSWORD  — autenticação em produção\n"
            "  METABOOKS_METADATA_TOKEN                 — token de metadados (staging/rc)\n"
            "  METABOOKS_COVER_TOKEN                    — token para capas\n"
            "  METABOOKS_MMO_TOKEN                      — token para mídias (MMO)\n"
            "  METABOOKS_BASE_URL                       — URL base (opcional, para override)\n"
            "  METABOOKS_DOWNLOAD_DIR                   — pastas onde downloads podem ser gravados\n\n"
            "Configure em ~/.config/metabooks-mcp/.env ou como variáveis de ambiente.\n\n"
            "Só o transporte stdio é suportado: os transportes HTTP (sse, "
            "streamable-http) abririam uma porta local sem autenticação alguma, "
            "dando a qualquer processo da máquina uso pleno das credenciais "
            "Metabooks configuradas."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="Transporte MCP a usar (somente stdio; ver descrição acima)",
    )
    args = parser.parse_args()

    # O servidor é construído aqui (não no nível do módulo) para que --help saia
    # pelo argparse sem pagar o custo — e sem registrar handlers de atexit.
    build_server().run(transport=args.transport)


if __name__ == "__main__":
    main()
