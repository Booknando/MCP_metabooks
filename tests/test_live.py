"""Suíte AO VIVO: as 12 tools contra a API real da Metabooks.

Desativada por padrão. Para rodar, na SUA máquina (nunca em CI compartilhado):

    export METABOOKS_LIVE=1
    export METABOOKS_USERNAME=...        # ou METABOOKS_METADATA_TOKEN=...
    export METABOOKS_PASSWORD=...
    export METABOOKS_COVER_TOKEN=...     # opcional; sem ele as provas de capa pulam
    export METABOOKS_MMO_TOKEN=...       # opcional; sem ele as provas de mídia pulam
    pytest tests/test_live.py -v

Complementa `scripts/smoke_live.py`: o script valida a FORMA das respostas da
API; esta suíte valida o RESULTADO das tools como o Claude as vê — projeção
compacta preenchida, imagem renderizável, download confinado.

Somente leitura. Grava apenas na `tmp_path` do pytest. Faz um único login por
sessão de teste (o lifespan do servidor desloga no fim, liberando o slot da MVB).

Personalize com variáveis de ambiente:
    METABOOKS_LIVE_BUSCA   termo da busca de prova (padrão: Linux)
    METABOOKS_LIVE_ISBN    ISBN-13 de prova (padrão: o 1º resultado da busca)
    METABOOKS_LIVE_EDITORA MVB ID de editora para a prova de /publisher
"""

from __future__ import annotations

import os

import pytest

from .conftest import images_of, json_of, text_of

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        os.environ.get("METABOOKS_LIVE", "").strip().lower() not in ("1", "true", "yes"),
        reason="suíte ao vivo desativada; defina METABOOKS_LIVE=1 para habilitar",
    ),
]

BUSCA = os.environ.get("METABOOKS_LIVE_BUSCA", "Linux")
ISBN_FIXO = os.environ.get("METABOOKS_LIVE_ISBN")
EDITORA_FIXA = os.environ.get("METABOOKS_LIVE_EDITORA")

TEM_CAPA = bool(os.environ.get("METABOOKS_COVER_TOKEN"))
TEM_MMO = bool(os.environ.get("METABOOKS_MMO_TOKEN"))

precisa_capa = pytest.mark.skipif(not TEM_CAPA, reason="METABOOKS_COVER_TOKEN ausente")
precisa_mmo = pytest.mark.skipif(not TEM_MMO, reason="METABOOKS_MMO_TOKEN ausente")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def live(monkeypatch, tmp_path):
    """Sessão MCP real: sem transporte mockado, credenciais do ambiente.

    Os downloads são desviados para a tmp_path do pytest — a suíte nunca escreve
    em ~/Downloads.
    """
    if not any((
        os.environ.get("METABOOKS_USERNAME") and os.environ.get("METABOOKS_PASSWORD"),
        os.environ.get("METABOOKS_METADATA_TOKEN"),
    )):
        pytest.skip("sem credenciais de metadados no ambiente")

    from mcp.shared.memory import create_connected_server_and_client_session

    from metabooks_mcp.server import build_server
    from metabooks_mcp.tools import _files

    destino = tmp_path / "downloads"
    destino.mkdir()
    monkeypatch.setenv(_files.ENV_DOWNLOAD_DIR, str(destino))

    # O servidor DO PACOTE, igual ao que o Claude Desktop inicia.
    mcp = build_server()

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        s._pasta_downloads = destino  # type: ignore[attr-defined]
        yield s


async def _primeiro_resultado(live) -> dict:
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 5,
    }))
    if not out.get("resultados"):
        pytest.skip(f"busca por {BUSCA!r} não devolveu resultados neste catálogo")
    return out["resultados"][0]


# --- busca ------------------------------------------------------------------

async def test_busca_devolve_identificacao_utilizavel(live):
    """A projeção compacta tem de vir preenchida com dados REAIS, não vazia."""
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 10,
    }))
    assert out["resultados"], "busca sem resultados"
    assert isinstance(out["total"], (int, float))
    assert out["pagina"] == 1, f"pagina deveria ser 1, veio {out['pagina']!r}"

    item = out["resultados"][0]
    assert item.get("titulo"), f"título ausente na projeção: {sorted(item)}"
    assert item.get("uuid") or item.get("isbn"), "nem uuid nem isbn na projeção"
    # A rede de segurança indica que a projeção não reconheceu o schema.
    assert "_dados_brutos_reduzidos" not in item, (
        "a projeção caiu na rede de segurança: os nomes de campo da API mudaram "
        "e as listas CANDIDATES em tools/_compact.py precisam ser atualizadas"
    )
    # Sinopse fora da lista: é o que fazia modelos pequenos escolherem errado.
    assert "descricao" not in item


async def test_busca_paginacao_avanca(live):
    p1 = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 3, "page": 1,
    }))
    if p1["total"] <= 3:
        pytest.skip("catálogo pequeno demais para paginar")
    p2 = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 3, "page": 2,
    }))
    assert p2["pagina"] == 2, f"pagina deveria ser 2, veio {p2['pagina']!r}"
    ids1 = {r.get("uuid") for r in p1["resultados"]}
    ids2 = {r.get("uuid") for r in p2["resultados"]}
    assert ids1 and ids2 and not (ids1 & ids2), "páginas 1 e 2 repetiram registros"


async def test_busca_marca_titulo_exato_em_dado_real(live):
    """Busca pelo título exato de um item conhecido e confere a flag."""
    item = await _primeiro_resultado(live)
    titulo = item["titulo"]
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": f"TI={titulo}", "size": 25,
    }))
    if not out.get("resultados"):
        pytest.skip("busca por TI= não devolveu resultados")
    exatos = [r for r in out["resultados"] if r.get("titulo_exato")]
    assert exatos, (
        f"nenhum resultado marcado como titulo_exato para TI={titulo!r}; "
        "a comparação de igualdade em _compact.compact_search não está casando"
    )
    for r in exatos:
        assert r["titulo"].strip().lower() == titulo.strip().lower()


async def test_busca_boleana_com_qualificadores(live):
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": f"ST={BUSCA} and PF=E*", "size": 5,
    }))
    assert "total" in out  # aceitar 0 resultados; o que importa é não dar erro


async def test_busca_view_full_traz_json_cru(live):
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 2, "view": "full",
    }))
    assert isinstance(out, dict) and (out.get("content") or out.get("products"))


# --- lote e detalhe ---------------------------------------------------------

async def test_lote_de_isbns(live):
    item = await _primeiro_resultado(live)
    isbn = ISBN_FIXO or item.get("isbn")
    if not isbn:
        pytest.skip("sem ISBN para o lote")
    out = json_of(await live.call_tool("metabooks_batch_search_isbns", {
        "isbns": [isbn],
    }))
    assert out["resultados"], f"lote não achou o ISBN {isbn}"


async def test_detalhe_por_uuid(live):
    item = await _primeiro_resultado(live)
    if not item.get("uuid"):
        pytest.skip("sem UUID no resultado da busca")
    out = json_of(await live.call_tool("metabooks_get_product", {"id": item["uuid"]}))
    resumo = out["resumo"]
    assert resumo.get("titulo"), f"detalhe sem título: {sorted(resumo)}"
    assert "_dados_brutos_reduzidos" not in resumo, (
        "a projeção do DETALHE caiu na rede de segurança: o schema aninhado da "
        "API mudou e as listas CANDIDATES/_extract_* precisam ser atualizadas"
    )


async def test_detalhe_por_isbn13(live):
    item = await _primeiro_resultado(live)
    isbn = ISBN_FIXO or item.get("isbn")
    if not isbn:
        pytest.skip("sem ISBN de prova")
    out = json_of(await live.call_tool("metabooks_get_product", {
        "id": isbn, "id_type": "isbn13",
    }))
    assert out["resumo"].get("titulo")


@pytest.mark.parametrize("formato", ["onix30-short", "onix30-ref"])
async def test_detalhe_onix(live, formato):
    item = await _primeiro_resultado(live)
    if not item.get("uuid"):
        pytest.skip("sem UUID de prova")
    saida = text_of(await live.call_tool("metabooks_get_product", {
        "id": item["uuid"], "format": formato,
    }))
    assert saida.lstrip().startswith("<"), f"{formato} não voltou XML: {saida[:80]!r}"
    assert "ONIX" in saida[:400].upper()


async def test_multiplos_produtos(live):
    out = json_of(await live.call_tool("metabooks_search_products", {
        "search": BUSCA, "size": 3,
    }))
    uuids = [r["uuid"] for r in out["resultados"] if r.get("uuid")][:3]
    if len(uuids) < 2:
        pytest.skip("menos de dois UUIDs para consultar em lote")
    saida = json_of(await live.call_tool("metabooks_get_multiple_products", {"ids": uuids}))
    # Este endpoint só responde em application/json — se o MCP pedisse json-short
    # aqui, a chamada falharia com 406 e o teste pegaria.
    assert saida["resultados"], "multipleProducts não devolveu nada"


# --- índice e editora -------------------------------------------------------

@pytest.mark.parametrize(
    "campo", ["author", "publisher", "title", "keyword", "set", "collection", "identifier"]
)
async def test_indice(live, campo):
    """Um índice inexistente deve aparecer como erro, não como lista vazia silenciosa."""
    result = await live.call_tool("metabooks_index_search", {
        "field": campo, "term": BUSCA[:4],
    })
    assert not result.isError, (
        f"index/{campo} falhou; se este índice não existe na API, remova-o do "
        f"Literal de metabooks_index_search: {text_of(result)[:200]}"
    )
    out = json_of(result)
    assert out["field"] == campo and isinstance(out["count"], int)


async def test_editora(live):
    if not EDITORA_FIXA:
        pytest.skip("defina METABOOKS_LIVE_EDITORA=BR00xxxxx para checar /publisher")
    out = json_of(await live.call_tool("metabooks_get_publisher", {
        "mvb_id": EDITORA_FIXA,
    }))
    assert out and not out.get("error"), f"editora {EDITORA_FIXA} não retornou dados"


# --- capas ------------------------------------------------------------------

@precisa_capa
@pytest.mark.parametrize("size", ["s", "m", "l"])
async def test_view_cover(live, size):
    item = await _primeiro_resultado(live)
    isbn = ISBN_FIXO or item.get("isbn")
    if not isbn:
        pytest.skip("sem ISBN de prova")
    result = await live.call_tool("metabooks_view_cover", {"id": isbn, "size": size})
    imagens = images_of(result)
    if not imagens:
        pytest.skip(f"título {isbn} pode não ter capa: {text_of(result)[:160]}")
    assert imagens[0][:3] == b"\xff\xd8\xff", "não voltou JPEG"
    # O limite inline existe para o cartão da ferramenta renderizar.
    assert len(imagens[0]) < 200_000, f"{len(imagens[0])} bytes é grande para inline"


@precisa_capa
async def test_download_cover_confinado(live):
    item = await _primeiro_resultado(live)
    isbn = ISBN_FIXO or item.get("isbn")
    if not isbn:
        pytest.skip("sem ISBN de prova")
    out = json_of(await live.call_tool("metabooks_download_cover", {"id": isbn}))
    if "error" in out:
        pytest.skip(f"capa indisponível: {out['error'][:160]}")
    caminho = out["path"]
    assert str(live._pasta_downloads) in caminho, (
        f"gravou fora da pasta permitida: {caminho}"
    )
    from pathlib import Path

    assert Path(caminho).read_bytes()[:3] == b"\xff\xd8\xff"


@precisa_capa
async def test_download_cover_recusa_destino_externo(live):
    """A guarda de confinamento tem de valer também em produção."""
    item = await _primeiro_resultado(live)
    isbn = ISBN_FIXO or item.get("isbn")
    if not isbn:
        pytest.skip("sem ISBN de prova")
    out = json_of(await live.call_tool("metabooks_download_cover", {
        "id": isbn, "dest": "../../../../../../tmp/fora.jpg",
    }))
    assert "fora das pastas permitidas" in out.get("error", "")


# --- mídia / MMO ------------------------------------------------------------

@precisa_mmo
async def test_listagem_de_midia(live):
    item = await _primeiro_resultado(live)
    if not item.get("uuid"):
        pytest.skip("sem UUID de prova")
    out = json_of(await live.call_tool("metabooks_get_media_assets", {
        "product_id": item["uuid"],
    }))
    if out.get("count", 0) == 0:
        pytest.skip("este título não tem mídias cadastradas")
    for asset in out["assets"]:
        assert "url" not in asset, "URL crua não deve sair na listagem"
        assert asset["type"], "asset sem tipo"


@precisa_mmo
async def test_download_de_midia_passa_pela_guarda_de_host(live):
    """Regressão possível: se a MVB servir mídia de outro host, a guarda bloqueia."""
    item = await _primeiro_resultado(live)
    if not item.get("uuid"):
        pytest.skip("sem UUID de prova")
    lista = json_of(await live.call_tool("metabooks_get_media_assets", {
        "product_id": item["uuid"],
    }))
    alvo = next((a for a in lista.get("assets", []) if a.get("asset_id")), None)
    if not alvo:
        pytest.skip("nenhum asset com asset_id neste título")
    out = json_of(await live.call_tool("metabooks_download_media_asset", {
        "product_id": item["uuid"], "asset_id": alvo["asset_id"],
    }))
    assert "error" not in out, (
        f"download de mídia falhou — se a mensagem citar 'fora da API permitida', "
        f"a guarda em client._same_api_host está rejeitando mídia legítima: {out}"
    )
    assert str(live._pasta_downloads) in out["path"]


@precisa_mmo
async def test_view_de_midia_imagem(live):
    item = await _primeiro_resultado(live)
    if not item.get("uuid"):
        pytest.skip("sem UUID de prova")
    lista = json_of(await live.call_tool("metabooks_get_media_assets", {
        "product_id": item["uuid"],
    }))
    imagem = next(
        (a for a in lista.get("assets", []) if a.get("is_image") and a.get("asset_id")),
        None,
    )
    if not imagem:
        pytest.skip("nenhuma imagem de mídia com asset_id neste título")
    result = await live.call_tool("metabooks_view_media_asset", {
        "product_id": item["uuid"], "asset_id": imagem["asset_id"],
    })
    imagens = images_of(result)
    assert imagens, f"não voltou imagem: {text_of(result)[:200]}"
    from io import BytesIO

    from PIL import Image as PILImage

    with PILImage.open(BytesIO(imagens[0])) as img:
        assert max(img.size) <= 1024, "imagem não foi reduzida para render inline"
