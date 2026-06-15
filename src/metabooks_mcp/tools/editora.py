"""Tools de Editora — endpoint: /publisher"""

from typing import Annotated
from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_get_publisher(
        ctx: Context,
        mvb_id: Annotated[str, "MVB/MB ID da editora (ex.: 'BR0090053')"],
    ) -> dict:
        """Recupera dados cadastrais de uma editora: nome, endereço, e-mail, prefixos ISBN, CNPJ."""
        client = ctx.request_context.lifespan_context["metabooks"]
        return await client.get(f"publisher/{mvb_id}")
