"""Tools de Mídia/MMO — endpoint: /asset/mmo"""

import os
from io import BytesIO
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP, Context, Image

from ._files import resolve_target

try:  # Pillow é usado para reduzir imagens grandes antes de exibi-las inline.
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover - dependência opcional ausente
    PILImage = None

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

# Tipos que são imagens (podem ser exibidos inline). Os demais (PDF, áudio,
# epub) só fazem sentido via download.
IMAGE_TYPES: frozenset[str] = frozenset(
    t for t, label in MEDIA_TYPE_LABELS.items() if label.endswith("[jpg]")
)

# Imagens MMO vêm em resolução cheia (a quarta capa pode passar de 700 KB) e não
# têm variantes leves como o endpoint /cover. Para garantir o render inline no
# Claude Desktop, reduzimos o lado maior a este limite e recomprimimos em JPEG.
MAX_INLINE_DIMENSION = 1024
JPEG_QUALITY = 85


def _asset_id_of(asset: dict) -> Optional[str]:
    """ID estável de um arquivo MMO = último segmento da URL `/asset/mmo/file/<id>`.

    Retorna None para a capa frontal (cuja URL aponta para o endpoint /cover).
    """
    url = asset.get("url") or ""
    if "/asset/mmo/file/" in url:
        return url.rstrip("/").rsplit("/", 1)[-1]
    return None


def _scope_for_url(url: str) -> str:
    """A capa frontal usa o token de capa; os demais arquivos, o token de MMO."""
    return "cover" if "/cover/" in url else "mmo"


def _select_asset(
    assets: list[dict], asset_id: Optional[str], media_type: Optional[str], index: int
) -> Optional[dict]:
    """Seleciona um asset por asset_id, ou por tipo (+índice, ordenado por sequência)."""
    if asset_id:
        return next((a for a in assets if _asset_id_of(a) == asset_id), None)
    if media_type:
        matching = sorted(
            (a for a in assets if (a.get("type") or "").upper() == media_type.upper()),
            key=lambda a: a.get("sequenceNumber") or 0,
        )
        if 0 <= index < len(matching):
            return matching[index]
    return None


def _asset_summary(assets: list[dict]) -> list[dict]:
    """Resumo enxuto p/ mensagens de erro (sem URL crua)."""
    return [
        {
            "type": (a.get("type") or "").upper(),
            "asset_id": _asset_id_of(a),
            "sequenceNumber": a.get("sequenceNumber"),
        }
        for a in assets
    ]


def _ext_from_label(label: str) -> str:
    """Extensão a partir do rótulo (ex.: 'Sumário [pdf]' → 'pdf')."""
    if "[" in label and "]" in label:
        inside = label[label.rfind("[") + 1 : label.rfind("]")]
        return inside.split("/")[0].strip().lower() or "bin"
    return "bin"


def _ext_from_bytes(data: bytes, fallback: str) -> str:
    """Extensão pelos bytes mágicos; cai para `fallback` se não reconhecer."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    if data[:4] == b"PK\x03\x04":  # zip-based: epub/docx
        return fallback if fallback in ("epub", "docx", "zip") else "epub"
    return fallback


def _looks_like_image(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"


def _downscale_to_jpeg(data: bytes, max_dim: int = MAX_INLINE_DIMENSION) -> bytes:
    """Reduz a imagem (mantendo proporção, só encolhe) e recomprime em JPEG."""
    with PILImage.open(BytesIO(data)) as img:
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim))
        out = BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()


async def _list_assets(client, product_id: str) -> list[dict]:
    data = await client.get(f"asset/mmo/{product_id}", scope="mmo")
    return data if isinstance(data, list) else []


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
        """Lista as mídias de um produto (capas, sumário, amostras). Exige METABOOKS_MMO_TOKEN.

        NÃO devolve URLs: os arquivos MMO exigem token no cabeçalho e não abrem no
        navegador. Para EXIBIR uma imagem use metabooks_view_media_asset; para
        BAIXAR qualquer arquivo (inclui PDF/áudio) use metabooks_download_media_asset
        — ambos aceitam product_id + asset_id (ou type + index).
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        assets = await _list_assets(client, product_id)
        if type_filter:
            assets = [a for a in assets if (a.get("type") or "").upper() == type_filter.upper()]
        enriched = []
        for a in assets:
            atype = (a.get("type") or "").upper()
            enriched.append(
                {
                    "type": atype,
                    "label": MEDIA_TYPE_LABELS.get(atype, atype or "?"),
                    "sequenceNumber": a.get("sequenceNumber"),
                    "asset_id": _asset_id_of(a),
                    "is_image": atype in IMAGE_TYPES,
                }
            )
        return {
            "count": len(enriched),
            "assets": enriched,
            "hint": (
                "Para EXIBIR uma imagem inline: metabooks_view_media_asset(product_id, asset_id=...) "
                "ou por tipo (media_type='BACKCOVER'/'IMAGE_SAMPLE_CONTENT', index p/ múltiplas). "
                "Para baixar qualquer arquivo: metabooks_download_media_asset. "
                "A capa frontal (FRONTCOVER) é melhor exibida por metabooks_view_cover (por ISBN). "
                "Não há URL para colar — os arquivos exigem token e não abrem no navegador."
            ),
        }

    @mcp.tool()
    async def metabooks_view_media_asset(
        ctx: Context,
        product_id: Annotated[str, "UUID do produto (32 chars)"],
        asset_id: Annotated[
            Optional[str],
            "ID do arquivo (campo asset_id de metabooks_get_media_assets). "
            "Tem prioridade sobre media_type/index.",
        ] = None,
        media_type: Annotated[
            Optional[str],
            "Tipo da mídia (ex.: BACKCOVER, IMAGE_SAMPLE_CONTENT) quando não se passa asset_id.",
        ] = None,
        index: Annotated[
            int,
            "Quando há vários do mesmo tipo (ex.: amostras do miolo), escolhe pela ordem "
            "de sequência (0 = primeira).",
        ] = 0,
    ):
        """Exibe uma imagem de mídia (quarta capa, miolo, foto do autor) inline na conversa.

        Busca o binário com o token MMO, reduz para um tamanho que renderiza inline
        e devolve a imagem — sem expor URL nem token. Só serve tipos de imagem; para
        PDF/áudio use metabooks_download_media_asset. Exige METABOOKS_MMO_TOKEN
        (e Pillow instalado no ambiente do MCP).
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        if not client.mmo_token:
            return {"error": "Token de MMO não configurado. Defina METABOOKS_MMO_TOKEN."}
        if PILImage is None:
            return {
                "error": (
                    "Pillow não está instalado no ambiente do MCP. Rode "
                    "'pip install pillow' no env do metabooks-mcp e reinicie o Claude Desktop."
                )
            }
        if not asset_id and not media_type:
            return {"error": "Informe asset_id OU media_type. Use metabooks_get_media_assets para listar."}

        assets = await _list_assets(client, product_id)
        asset = _select_asset(assets, asset_id, media_type, index)
        if asset is None:
            return {
                "error": "Asset não encontrado para os critérios informados.",
                "available": _asset_summary(assets),
            }
        atype = (asset.get("type") or "").upper()
        if atype not in IMAGE_TYPES:
            return {
                "error": (
                    f"O asset '{asset.get('label') or atype}' não é imagem ({atype}); "
                    "use metabooks_download_media_asset para baixá-lo."
                )
            }
        url = asset.get("url") or ""
        try:
            data = await client.get_bytes_from_url(url, scope=_scope_for_url(url), accept="*/*")
        except Exception as exc:  # noqa: BLE001 — erro amigável ao cliente MCP
            return {"error": f"Não foi possível buscar a mídia ({atype}): {exc}."}
        if not _looks_like_image(data):
            return {"error": f"O servidor não devolveu uma imagem para este asset ({atype})."}
        try:
            small = _downscale_to_jpeg(data)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Falha ao processar a imagem ({atype}): {exc}."}
        return Image(data=small, format="jpeg")

    @mcp.tool()
    async def metabooks_download_media_asset(
        ctx: Context,
        product_id: Annotated[str, "UUID do produto (32 chars)"],
        asset_id: Annotated[
            Optional[str],
            "ID do arquivo (campo asset_id de metabooks_get_media_assets). "
            "Tem prioridade sobre media_type/index.",
        ] = None,
        media_type: Annotated[
            Optional[str],
            "Tipo da mídia (ex.: TABLE_OF_CONTENT, AUDIO_SAMPLE_CONTENT) quando não se passa asset_id.",
        ] = None,
        index: Annotated[int, "Escolhe entre vários do mesmo tipo (0 = primeiro)."] = 0,
        dest: Annotated[
            Optional[str],
            "Destino opcional: caminho de arquivo OU pasta. Se omitido, salva em ~/Downloads.",
        ] = None,
    ) -> dict:
        """Baixa uma mídia (capa extra, miolo, sumário PDF, áudio…) e salva em arquivo.

        Funciona para qualquer tipo (imagem, PDF, áudio, epub) em resolução/qualidade
        originais. Para apenas exibir uma imagem na conversa, use
        metabooks_view_media_asset. Exige METABOOKS_MMO_TOKEN.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        if not client.mmo_token:
            return {"error": "Token de MMO não configurado. Defina METABOOKS_MMO_TOKEN."}
        if not asset_id and not media_type:
            return {"error": "Informe asset_id OU media_type. Use metabooks_get_media_assets para listar."}

        assets = await _list_assets(client, product_id)
        asset = _select_asset(assets, asset_id, media_type, index)
        if asset is None:
            return {
                "error": "Asset não encontrado para os critérios informados.",
                "available": _asset_summary(assets),
            }
        atype = (asset.get("type") or "").upper()
        url = asset.get("url") or ""
        try:
            data = await client.get_bytes_from_url(url, scope=_scope_for_url(url), accept="*/*")
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Não foi possível baixar a mídia ({atype}): {exc}."}

        ext = _ext_from_bytes(data, _ext_from_label(asset.get("label", "")))
        resolved_id = _asset_id_of(asset) or f"{atype.lower()}_{asset.get('sequenceNumber') or 0}"
        filename = f"midia_{product_id}_{resolved_id}.{ext}"
        target = resolve_target(dest, filename)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            return {"error": f"Falha ao salvar a mídia em {target}: {exc}"}

        return {
            "product_id": product_id,
            "type": atype,
            "asset_id": _asset_id_of(asset),
            "path": target,
            "bytes": len(data),
            "message": f"Mídia salva em {target} ({len(data) / 1024:.1f} KB).",
        }
