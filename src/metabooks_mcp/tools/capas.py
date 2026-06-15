"""Tools de Capas — endpoint: /cover"""

from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP, Context


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_get_cover_url(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9783411046508)"],
        size: Annotated[
            Literal["s", "m", "l", "original"],
            "Tamanho: s (90px larg.), m (200px), l (599px alt.) ou original",
        ] = "m",
    ) -> dict:
        """Monta a URL de capa de um título por ISBN/GTIN. Exige METABOOKS_COVER_TOKEN."""
        client = ctx.request_context.lifespan_context["metabooks"]
        if not client.cover_token:
            return {
                "error": (
                    "Token de capa não configurado. Defina METABOOKS_COVER_TOKEN. "
                    "Capas exigem token dedicado — login/metadados não as acessa (seção 5.5.5)."
                )
            }
        size_segment = f"/{size}" if size != "original" else ""
        cover_url = f"{client.base_url}/cover/{id}{size_segment}"
        return {"id": id, "size": size, "cover_url": cover_url}
