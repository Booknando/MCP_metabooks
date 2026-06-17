"""MCP Server para integração com a API REST v2 da Metabooks."""

import argparse
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
        # Libera o slot de login paralelo antes de encerrar (no-op para token estático).
        await client.logout()
        await client.aclose()


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
            "  METABOOKS_BASE_URL                       — URL base (opcional, para override)\n\n"
            "Configure em ~/.config/metabooks-mcp/.env ou como variáveis de ambiente."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transporte MCP a usar (padrão: stdio)",
    )
    args = parser.parse_args()

    # FastMCP é criado aqui (não no nível do módulo) para evitar que os handlers
    # de atexit sejam registrados antes de --help sair via sys.exit().
    mcp = FastMCP(
        name="metabooks-mcp",
        instructions=(
            "Servidor MCP somente leitura para a API REST v2 da Metabooks. "
            "Módulos disponíveis: busca de produtos no catálogo bibliográfico (busca booleana, "
            "busca em lote por ISBN), detalhe de produto por UUID/ISBN/GTIN (JSON ou ONIX 3.0), "
            "busca em índice para autocompletar, visualização/download/URL de capas, "
            "visualização/download de mídia/MMO (capas extras, miolo, sumário) e dados "
            "cadastrais de editoras. "
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
    produtos.register(mcp)
    capas.register(mcp)
    midia.register(mcp)
    indice.register(mcp)
    editora.register(mcp)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
