"""As 12 tools através de uma sessão MCP real (schema + execução + resultado)."""

from __future__ import annotations

import pytest

from .conftest import images_of, json_of, text_of
from .fake_api import PRODUCT_ISBN, PRODUCT_UUID, PUBLISHER_ID

pytestmark = pytest.mark.anyio

TOOLS = {
    "metabooks_search_products",
    "metabooks_batch_search_isbns",
    "metabooks_get_product",
    "metabooks_get_multiple_products",
    "metabooks_view_cover",
    "metabooks_download_cover",
    "metabooks_get_cover_url",
    "metabooks_get_media_assets",
    "metabooks_view_media_asset",
    "metabooks_download_media_asset",
    "metabooks_index_search",
    "metabooks_get_publisher",
}


# --- registro ---------------------------------------------------------------

async def test_todas_as_tools_registradas(session):
    nomes = {t.name for t in (await session.list_tools()).tools}
    assert nomes == TOOLS


async def test_toda_tool_tem_descricao_e_schema(session):
    for tool in (await session.list_tools()).tools:
        assert tool.description, f"{tool.name} sem docstring"
        assert tool.inputSchema.get("type") == "object"


# --- busca ------------------------------------------------------------------

async def test_busca_compacta_por_padrao(session, api):
    out = json_of(await session.call_tool(
        "metabooks_search_products", {"search": "Dom Casmurro"}
    ))
    assert api.calls[-1]["accept"] == "application/json-short"
    assert out["total"] == 137 and out["pagina"] == 1
    primeiro = out["resultados"][0]
    assert primeiro["titulo"] == "Dom Casmurro" and primeiro["titulo_exato"] is True
    # Nenhuma sinopse na lista compacta — é o que fazia o modelo escolher errado.
    assert all("descricao" not in r for r in out["resultados"])


async def test_busca_full_devolve_json_cru(session, api):
    out = json_of(await session.call_tool(
        "metabooks_search_products", {"search": "Dom Casmurro", "view": "full"}
    ))
    assert api.calls[-1]["accept"] == "application/json"
    assert "content" in out and "mainDescription" in out["content"][0]


async def test_busca_encaminha_parametros(session, api):
    await session.call_tool("metabooks_search_products", {
        "search": "ST=Linux and PF=E*", "page": 2, "size": 100,
        "sort": "identifier", "direction": "asc", "active": True,
    })
    query = api.calls[-1]["query"]
    assert query == {
        "page": "2", "size": "100", "search": "ST=Linux and PF=E*",
        "sort": "identifier", "direction": "asc", "active": "true",
    }


@pytest.mark.parametrize(
    "args",
    [
        {"search": "x", "size": 9999},
        {"search": "x", "size": 0},
        {"search": "x", "page": 0},
        {"search": "x", "page": -5},
        {"search": "x", "sort": "coluna_inexistente"},
        {"search": "x", "direction": "cima"},
    ],
)
async def test_busca_recusa_parametros_fora_do_limite(session, api, args):
    antes = len(api.calls)
    result = await session.call_tool("metabooks_search_products", args)
    assert result.isError, f"{args} deveria falhar na validação"
    assert len(api.calls) == antes, "não deveria chegar a chamar a API"


async def test_busca_sem_resultados(session):
    out = json_of(await session.call_tool(
        "metabooks_search_products", {"search": "naoexiste"}
    ))
    assert out["resultados"] == []


# --- busca em lote ----------------------------------------------------------

async def test_lote_de_isbns(session, api):
    out = json_of(await session.call_tool(
        "metabooks_batch_search_isbns",
        {"isbns": [PRODUCT_ISBN, "9780000000001", "9789999999999"]},
    ))
    assert api.calls[-1]["method"] == "POST"
    assert api.calls[-1]["content_type"] == "application/json"
    # ISBN sem correspondência simplesmente não aparece.
    assert {r["isbn"] for r in out["resultados"]} == {PRODUCT_ISBN, "9780000000001"}


async def test_lote_recusa_lista_vazia_ou_gigante(session):
    assert (await session.call_tool("metabooks_batch_search_isbns", {"isbns": []})).isError
    grande = {"isbns": [str(i) for i in range(501)]}
    assert (await session.call_tool("metabooks_batch_search_isbns", grande)).isError


# --- detalhe ----------------------------------------------------------------

async def test_detalhe_compacto(session):
    out = json_of(await session.call_tool(
        "metabooks_get_product", {"id": PRODUCT_UUID}
    ))
    assert out["resumo"]["titulo"] == "Dom Casmurro"
    assert out["resumo"]["autores"][0].startswith("Machado de Assis")


async def test_detalhe_por_isbn13(session, api):
    await session.call_tool(
        "metabooks_get_product", {"id": PRODUCT_ISBN, "id_type": "isbn13"}
    )
    assert api.calls[-1]["path"] == f"/api/v2/product/{PRODUCT_ISBN}/isbn13"


@pytest.mark.parametrize("formato", ["onix30-short", "onix30-ref"])
async def test_detalhe_onix_volta_xml(session, api, formato):
    result = await session.call_tool(
        "metabooks_get_product", {"id": PRODUCT_UUID, "format": formato}
    )
    assert api.calls[-1]["accept"] == f"application/{formato}"
    assert "<ONIXMessage" in text_of(result)


async def test_detalhe_produto_inexistente_erra_claramente(session):
    result = await session.call_tool(
        "metabooks_get_product", {"id": "0" * 32}
    )
    assert result.isError


async def test_multiplos_produtos_usa_json_puro(session, api):
    """A collection anota: multipleProducts só responde em application/json."""
    out = json_of(await session.call_tool(
        "metabooks_get_multiple_products", {"ids": [PRODUCT_UUID]}
    ))
    assert api.calls[-1]["accept"] == "application/json"
    assert out["resultados"][0]["titulo"] == "Dom Casmurro"


async def test_multiplos_produtos_recusa_lista_gigante(session):
    assert (await session.call_tool(
        "metabooks_get_multiple_products", {"ids": ["a" * 32] * 251}
    )).isError


# --- índice e editora -------------------------------------------------------

async def test_indice(session, api):
    out = json_of(await session.call_tool(
        "metabooks_index_search", {"field": "author", "term": "Machado"}
    ))
    assert out["count"] == 1 and out["field"] == "author"
    assert api.calls[-1]["path"] == "/api/v2/index/author/Machado"


async def test_indice_recusa_campo_invalido(session):
    assert (await session.call_tool(
        "metabooks_index_search", {"field": "inventado", "term": "x"}
    )).isError


async def test_indice_nao_escapa_para_outro_endpoint(session, api):
    """Travessia de caminho: o termo tem de virar UM segmento codificado."""
    await session.call_tool(
        "metabooks_index_search",
        {"field": "author", "term": "../../publisher/BR0090012"},
    )
    caminho = api.calls[-1]["path"]
    # O termo vira UM segmento: as barras chegam ao servidor como %2F, então o
    # endpoint atingido continua sendo /index/author/... e não /publisher/...
    assert caminho.startswith("/api/v2/index/author/")
    # /api/v2/index/author/<termo> = 5 barras; nenhuma barra extra veio do termo.
    assert caminho.count("/") == 5
    assert "%2F" in caminho and "/publisher/" not in caminho


async def test_editora(session, api):
    out = json_of(await session.call_tool(
        "metabooks_get_publisher", {"mvb_id": PUBLISHER_ID}
    ))
    assert out["name"] == "Editora Contexto" and out["cnpj"]
    assert api.calls[-1]["path"] == f"/api/v2/publisher/{PUBLISHER_ID}"


async def test_editora_nao_escapa_para_outro_endpoint(session):
    result = await session.call_tool(
        "metabooks_get_publisher", {"mvb_id": "../../login"}
    )
    assert result.isError or "error" in text_of(result)


# --- capas ------------------------------------------------------------------

async def test_view_cover_devolve_imagem_inline(session, api):
    result = await session.call_tool("metabooks_view_cover", {"id": PRODUCT_ISBN})
    imagens = images_of(result)
    assert len(imagens) == 1 and imagens[0][:3] == b"\xff\xd8\xff"
    # Accept precisa ser */*: a API responde 406 a image/jpeg e 403 a image/*.
    assert api.calls[-1]["accept"] == "*/*"
    assert api.calls[-1]["path"] == f"/api/v2/cover/{PRODUCT_ISBN}/m"


@pytest.mark.parametrize("size", ["s", "m", "l"])
async def test_view_cover_tamanhos_leves(session, api, size):
    result = await session.call_tool(
        "metabooks_view_cover", {"id": PRODUCT_ISBN, "size": size}
    )
    assert images_of(result)
    assert api.calls[-1]["path"].endswith(f"/{size}")


async def test_view_cover_nao_aceita_original(session):
    """'original' (~1.3 MB) não renderiza inline — só via download."""
    assert (await session.call_tool(
        "metabooks_view_cover", {"id": PRODUCT_ISBN, "size": "original"}
    )).isError


async def test_view_cover_capa_inexistente_devolve_erro_amigavel(session):
    out = json_of(await session.call_tool("metabooks_view_cover", {"id": "0000000000000"}))
    assert "Não foi possível obter a capa" in out["error"]


async def test_view_cover_sem_token_orienta_configuracao(session_sem_tokens):
    out = json_of(await session_sem_tokens.call_tool(
        "metabooks_view_cover", {"id": PRODUCT_ISBN}
    ))
    assert "METABOOKS_COVER_TOKEN" in out["error"]


async def test_download_cover_sem_token_orienta_configuracao(session_sem_tokens):
    out = json_of(await session_sem_tokens.call_tool(
        "metabooks_download_cover", {"id": PRODUCT_ISBN}
    ))
    assert "METABOOKS_COVER_TOKEN" in out["error"]


@pytest.mark.parametrize(
    "tool", ["metabooks_view_media_asset", "metabooks_download_media_asset"]
)
async def test_midia_sem_token_orienta_configuracao(session_sem_tokens, tool):
    out = json_of(await session_sem_tokens.call_tool(
        tool, {"product_id": PRODUCT_UUID, "media_type": "BACKCOVER"}
    ))
    assert "METABOOKS_MMO_TOKEN" in out["error"]


async def test_download_cover_grava_e_confina(session, downloads, api):
    out = json_of(await session.call_tool(
        "metabooks_download_cover", {"id": PRODUCT_ISBN}
    ))
    destino = downloads / f"capa_{PRODUCT_ISBN}_original.jpg"
    assert out["path"] == str(destino)
    assert destino.read_bytes()[:3] == b"\xff\xd8\xff"
    assert out["bytes"] == destino.stat().st_size
    assert api.calls[-1]["path"] == f"/api/v2/cover/{PRODUCT_ISBN}"


async def test_download_cover_recusa_destino_fora_da_pasta(session, downloads):
    out = json_of(await session.call_tool(
        "metabooks_download_cover",
        {"id": PRODUCT_ISBN, "dest": "../../../../../../tmp/roubado.jpg"},
    ))
    assert "fora das pastas permitidas" in out["error"]
    assert "pastas_permitidas" in out


async def test_download_cover_nao_sobrescreve_sem_pedido(session, downloads):
    alvo = downloads / "capa.jpg"
    alvo.write_bytes(b"conteudo original")
    out = json_of(await session.call_tool(
        "metabooks_download_cover", {"id": PRODUCT_ISBN, "dest": str(alvo)}
    ))
    assert "já existe" in out["error"]
    assert alvo.read_bytes() == b"conteudo original"

    out = json_of(await session.call_tool(
        "metabooks_download_cover",
        {"id": PRODUCT_ISBN, "dest": str(alvo), "overwrite": True},
    ))
    assert out["path"] == str(alvo)
    assert alvo.read_bytes()[:3] == b"\xff\xd8\xff"


async def test_download_cover_nao_grava_sobre_config(session, downloads):
    """Extensão forçada: um JPEG não pode virar claude_desktop_config.json."""
    config = downloads / "claude_desktop_config.json"
    config.write_text('{"mcpServers": {}}')
    out = json_of(await session.call_tool(
        "metabooks_download_cover", {"id": PRODUCT_ISBN, "dest": str(config)}
    ))
    assert out["path"].endswith(".json.jpg")
    assert config.read_text() == '{"mcpServers": {}}'


async def test_cover_url_nao_sugere_token_na_querystring(session):
    out = json_of(await session.call_tool(
        "metabooks_get_cover_url", {"id": PRODUCT_ISBN, "size": "original"}
    ))
    assert out["cover_url"].endswith(f"/cover/{PRODUCT_ISBN}")
    assert out["browser_openable"] is False
    assert "access_token" not in out["auth"]
    assert "Authorization" in out["auth"]


# --- mídia / MMO ------------------------------------------------------------

async def test_listar_midias_sem_urls_cruas(session):
    out = json_of(await session.call_tool(
        "metabooks_get_media_assets", {"product_id": PRODUCT_UUID}
    ))
    assert out["count"] == 6
    assert all("url" not in a for a in out["assets"])
    por_tipo = {a["type"]: a for a in out["assets"]}
    assert por_tipo["BACKCOVER"]["asset_id"] == "back0001"
    assert por_tipo["BACKCOVER"]["is_image"] is True
    assert por_tipo["TABLE_OF_CONTENT"]["is_image"] is False
    assert por_tipo["TABLE_OF_CONTENT"]["label"].endswith("[pdf]")


async def test_listar_midias_com_filtro(session):
    out = json_of(await session.call_tool(
        "metabooks_get_media_assets",
        {"product_id": PRODUCT_UUID, "type_filter": "image_sample_content"},
    ))
    assert out["count"] == 2


async def test_ver_midia_por_asset_id(session, api):
    result = await session.call_tool(
        "metabooks_view_media_asset",
        {"product_id": PRODUCT_UUID, "asset_id": "back0001"},
    )
    assert images_of(result)
    assert api.calls[-1]["path"] == "/api/v1/asset/mmo/file/back0001"
    assert api.calls[-1]["token"] == "TOKEN-MMO"


async def test_ver_midia_por_tipo_e_indice(session, api):
    """index escolhe pela sequência, não pela ordem do JSON."""
    await session.call_tool("metabooks_view_media_asset", {
        "product_id": PRODUCT_UUID, "media_type": "IMAGE_SAMPLE_CONTENT", "index": 0,
    })
    assert api.calls[-1]["path"].endswith("sample01")
    await session.call_tool("metabooks_view_media_asset", {
        "product_id": PRODUCT_UUID, "media_type": "IMAGE_SAMPLE_CONTENT", "index": 1,
    })
    assert api.calls[-1]["path"].endswith("sample02")


async def test_capa_frontal_da_midia_usa_token_de_capa(session, api):
    """A URL da FRONTCOVER aponta para /cover — escopo decidido pela URL."""
    await session.call_tool("metabooks_view_media_asset", {
        "product_id": PRODUCT_UUID, "media_type": "FRONTCOVER",
    })
    assert api.calls[-1]["path"].startswith("/api/v2/cover/")
    assert api.calls[-1]["token"] == "TOKEN-COVER"


async def test_ver_midia_reduz_imagem_para_render_inline(session):
    result = await session.call_tool(
        "metabooks_view_media_asset",
        {"product_id": PRODUCT_UUID, "asset_id": "back0001"},
    )
    from io import BytesIO
    from PIL import Image as PILImage

    with PILImage.open(BytesIO(images_of(result)[0])) as img:
        assert max(img.size) <= 1024


async def test_ver_midia_recusa_nao_imagem(session):
    out = json_of(await session.call_tool(
        "metabooks_view_media_asset",
        {"product_id": PRODUCT_UUID, "media_type": "TABLE_OF_CONTENT"},
    ))
    assert "não é imagem" in out["error"]


async def test_ver_midia_exige_criterio(session):
    out = json_of(await session.call_tool(
        "metabooks_view_media_asset", {"product_id": PRODUCT_UUID}
    ))
    assert "asset_id OU media_type" in out["error"]


async def test_ver_midia_asset_inexistente_lista_disponiveis(session):
    out = json_of(await session.call_tool(
        "metabooks_view_media_asset",
        {"product_id": PRODUCT_UUID, "asset_id": "naoexiste"},
    ))
    assert "não encontrado" in out["error"]
    assert any(a["asset_id"] == "back0001" for a in out["available"])


@pytest.mark.parametrize(
    "media_type,ext,magic",
    [
        ("TABLE_OF_CONTENT", "pdf", b"%PDF"),
        ("BACKCOVER", "jpg", b"\xff\xd8\xff"),
        ("AUDIO_SAMPLE_CONTENT", "mp3", b"ID3"),
    ],
)
async def test_baixar_midia_detecta_extensao(session, downloads, media_type, ext, magic):
    out = json_of(await session.call_tool(
        "metabooks_download_media_asset",
        {"product_id": PRODUCT_UUID, "media_type": media_type},
    ))
    from pathlib import Path

    destino = Path(out["path"])
    assert destino.suffix == f".{ext}"
    assert destino.read_bytes().startswith(magic)
    assert str(downloads) in out["path"]


async def test_baixar_midia_recusa_destino_fora_da_pasta(session):
    out = json_of(await session.call_tool(
        "metabooks_download_media_asset",
        {"product_id": PRODUCT_UUID, "media_type": "TABLE_OF_CONTENT",
         "dest": "/etc/cron.d/backdoor"},
    ))
    assert "fora das pastas permitidas" in out["error"]
