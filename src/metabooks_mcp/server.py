"""MCP Server para integração com a API REST v2 da Metabooks."""

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

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
        await client.aclose()


mcp = FastMCP(
    name="metabooks-mcp",
    instructions=(
        "Servidor MCP somente leitura para a API REST v2 da Metabooks. "
        "Módulos disponíveis: busca de produtos no catálogo bibliográfico (busca booleana, "
        "busca em lote por ISBN), detalhe de produto por UUID/ISBN/GTIN (JSON ou ONIX 3.0), "
        "busca em índice para autocompletar, URLs de mídia/MMO e dados cadastrais de editoras. "
        "Credenciais: METABOOKS_USERNAME/METABOOKS_PASSWORD (produção) "
        "ou METABOOKS_METADATA_TOKEN (staging/rc). "
        "Capas e mídias exigem tokens dedicados: METABOOKS_COVER_TOKEN e METABOOKS_MMO_TOKEN."
    ),
    lifespan=lifespan,
)

# Módulos de conteúdo bibliográfico
produtos.register(mcp)
capas.register(mcp)
midia.register(mcp)
indice.register(mcp)
editora.register(mcp)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
