"""Tools de Mídia/MMO — endpoint: /asset/mmo"""

from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP, Context

MEDIA_TYPE_LABELS: dict[str, str] = {
    "FRONTCOVER": "Capa (frente) [jpg]",
    "BACKCOVER": "Quarta capa [jpg]",
    "COVER_PACK": "Outras capas / orelha interna [jpg]",
    "FULL_COVER": "Capa completa [jpg]",
    "IMAGE_SAMPLE_CONTENT": "Imagem de amostra do miolo [jpg]",
    "TABLE_OF_CONTENT": "Sumário [pdf]",
    "DESCRIPTION": "Descrição / sinopse / orelha [pdf]",
    "AUTHOR_IMAGE": "Foto do autor [jpg]",
    "AUDIO_SAMPLE_CONTENT": "Amostra de áudio [mp3/wav]",
    "TEXT_SAMPLE_CONTENT": "Amostra de texto / primeiro capítulo [pdf/epub]",
    "REVIEW": "Resenha [pdf]",
    "INTRODUCTION": "Prefácio / introdução [pdf]",
    "PRODUCT_INDEX": "Índice remissivo [pdf]",
    "PUBLISHER_LOGO": "Logo da editora [jpg]",
    "IMPRINT_LOGO": "Logo do selo [jpg]",
    "SERIES_IMAGE": "Imagem da série [jpg]",
    "SERIES_LOGO": "Logo da série [jpg]",
    "PRESS_RELEASE": "Release de imprensa [pdf]",
    "PUBLISHERS_CATALOGUE": "Catálogo / preview da editora [pdf]",
    "STAGE_IMAGE": "Imagem de hierarquia [jpg]",
    "ERRATA": "Errata [pdf]",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_get_media_assets(
        ctx: Context,
        product_id: Annotated[str, "UUID do produto (32 chars)"],
        type_filter: Annotated[
            Optional[str],
            "Filtra por tipo de mídia (ex.: FRONTCOVER, TABLE_OF_CONTENT, TEXT_SAMPLE_CONTENT)",
        ] = None,
    ) -> dict:
        """Lista as URLs de mídia de um produto (capas, sumário, amostras). Exige METABOOKS_MMO_TOKEN."""
        client = ctx.request_context.lifespan_context["metabooks"]
        data = await client.get(f"asset/mmo/{product_id}", scope="mmo")
        assets: list[dict] = data if isinstance(data, list) else []
        if type_filter:
            assets = [a for a in assets if (a.get("type") or "").upper() == type_filter.upper()]
        enriched = [
            {**a, "label": MEDIA_TYPE_LABELS.get(a.get("type", ""), a.get("type", "?"))}
            for a in assets
        ]
        return {"count": len(enriched), "assets": enriched}
