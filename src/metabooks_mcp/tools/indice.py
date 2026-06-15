"""Tools de Índice — endpoint: /index"""

from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_index_search(
        ctx: Context,
        field: Annotated[
            Literal["author", "publisher", "title", "keyword", "set", "collection", "identifier"],
            "Índice a consultar: author, publisher, title, keyword, set, collection ou identifier",
        ],
        term: Annotated[str, "Termo de busca (retorna até 100 entradas, sem paginação)"],
    ) -> dict:
        """Consulta um índice para autocompletar/descobrir valores (autores, editoras, séries etc.)."""
        client = ctx.request_context.lifespan_context["metabooks"]
        data = await client.get(f"index/{field}/{term}")
        entries: list = data if isinstance(data, list) else []
        return {"field": field, "term": term, "count": len(entries), "entries": entries}
