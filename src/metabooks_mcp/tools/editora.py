"""Tools de Editora — endpoint: /publisher"""

from typing import Annotated
from mcp.server.fastmcp import FastMCP, Context
from pydantic import Field

from ..client import path_segment


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_get_publisher(
        ctx: Context,
        mvb_id: Annotated[
            str,
            Field(description="MVB/MB ID da editora (ex.: 'BR0090053')"),
        ],
    ) -> dict:
        """Recupera dados cadastrais de uma editora: nome, endereço, e-mail, prefixos ISBN, CNPJ."""
        client = ctx.request_context.lifespan_context["metabooks"]
        return await client.get(f"publisher/{path_segment(mvb_id)}")
