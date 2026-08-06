"""Contrato: o que o MCP faz × o que a collection Postman oficial documenta.

A collection (``tests/fixtures/Metabooks.postman_collection.json``, fornecida pela
MVB) é a única especificação executável que temos da API. Estes testes derivam
dela o conjunto de endpoints, parâmetros e limites e comparam com o que o
servidor MCP efetivamente emite, de modo que uma divergência (endpoint não
coberto, formato indevido, limite errado) apareça como falha e não como suposição.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

import pytest

from metabooks_mcp.tools.produtos import (
    MAX_BULK_IDS,
    MAX_BULK_ISBNS,
    MAX_PAGE_SIZE,
    SEARCH_SYNTAX,
)

from .conftest import json_of
from .fake_api import PRODUCT_ISBN, PRODUCT_UUID, PUBLISHER_ID

pytestmark = pytest.mark.anyio

_HEX32 = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
_DIGITS = re.compile(r"^\d{8,14}$")


def _walk(items):
    for item in items:
        if "item" in item:
            yield from _walk(item["item"])
        elif "request" in item:
            yield item


def _pattern(segments: list[str]) -> str:
    """Reduz um path concreto a um padrão comparável ('/product/{id}')."""
    out = []
    for seg in segments:
        if _HEX32.match(seg) or _DIGITS.match(seg):
            out.append("{id}")
        elif seg.startswith("BR") and seg[2:].isdigit():
            out.append("{mvbid}")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def collection_endpoints(collection: dict) -> set[tuple[str, str]]:
    found = set()
    for item in _walk(collection["item"]):
        request = item["request"]
        found.add((request["method"], _pattern(request["url"]["path"])))
    return found


# O que cada endpoint documentado corresponde no MCP. Endpoint documentado sem
# entrada aqui faz o teste de cobertura falhar — é o alarme para "a MVB
# documenta algo que não implementamos".
COVERAGE = {
    ("POST", "/api/v2/login"): "client._do_login",
    ("GET", "/api/v2/logout"): "client.logout",
    ("GET", "/api/v2/products"): "metabooks_search_products",
    ("POST", "/api/v2/products"): "metabooks_batch_search_isbns",
    ("POST", "/api/v2/product/multipleProducts"): "metabooks_get_multiple_products",
    ("GET", "/api/v2/product/{id}"): "metabooks_get_product",
    ("GET", "/api/v2/product/{id}/isbn13"): "metabooks_get_product (id_type=isbn13)",
    ("GET", "/api/v2/publisher/{mvbid}"): "metabooks_get_publisher",
    ("GET", "/api/v2/asset/mmo/{id}"): "metabooks_get_media_assets",
}


def test_todo_endpoint_documentado_tem_implementacao(postman_collection):
    documentados = collection_endpoints(postman_collection)
    faltando = documentados - set(COVERAGE)
    assert not faltando, f"endpoints documentados sem tool correspondente: {faltando}"


def test_a_collection_nao_ganhou_endpoints_novos(postman_collection):
    """Se a MVB atualizar a collection, este teste avisa em vez de passar batido."""
    documentados = collection_endpoints(postman_collection)
    assert documentados == set(COVERAGE)


def test_limite_de_size_bate_com_a_collection(postman_collection):
    tamanhos = {
        int(q["value"])
        for item in _walk(postman_collection["item"])
        for q in item["request"]["url"].get("query", [])
        if q["key"] == "size"
    }
    assert max(tamanhos) == MAX_PAGE_SIZE


def test_page_e_base_1_na_collection(postman_collection):
    paginas = {
        int(q["value"])
        for item in _walk(postman_collection["item"])
        for q in item["request"]["url"].get("query", [])
        if q["key"] == "page"
    }
    assert paginas == {1}, "a collection sempre usa page=1 para a primeira página"


def test_qualificadores_documentados_estao_na_sintaxe_exposta(postman_collection):
    """Todo qualificador CHAVE= visto na collection deve constar do help das tools."""
    vistos: set[str] = set()
    for item in _walk(postman_collection["item"]):
        for q in item["request"]["url"].get("query", []):
            if q["key"] != "search":
                continue
            for chave in re.findall(r"\b([A-Z]{2})=", unquote(q["value"])):
                vistos.add(chave)
    assert vistos, "nenhum qualificador encontrado na collection"
    faltando = {q for q in vistos if f"{q}=" not in SEARCH_SYNTAX}
    assert not faltando, f"qualificadores usados pela API e não documentados: {faltando}"


def test_limites_de_lote_sao_coerentes():
    assert MAX_BULK_IDS <= MAX_BULK_ISBNS
    assert MAX_BULK_IDS == MAX_PAGE_SIZE


# --- comportamento em execução, contra as regras da collection --------------

async def test_multiple_products_so_aceita_json(client):
    """"only in json format (no json-short or ONIX response available)"."""
    import httpx

    with pytest.raises(httpx.HTTPStatusError) as exc:
        await client.post(
            "product/multipleProducts",
            json={"ids": [PRODUCT_UUID]},
            accept="application/json-short",
        )
    assert exc.value.response.status_code == 406


async def test_corpo_do_lote_segue_o_formato_da_collection(session, api):
    import json as _json

    await session.call_tool("metabooks_batch_search_isbns", {"isbns": [PRODUCT_ISBN]})
    body = _json.loads(api.calls[-1]["body"])
    assert body == {"content": [{"isbn": PRODUCT_ISBN}]}


async def test_corpo_de_multiple_products_segue_a_collection(session, api):
    import json as _json

    await session.call_tool("metabooks_get_multiple_products", {"ids": [PRODUCT_UUID]})
    body = _json.loads(api.calls[-1]["body"])
    assert body == {"ids": [PRODUCT_UUID]}


async def test_busca_com_acentos_e_encodada(session, api):
    """A collection observa: 'Pão de Açúcar' vira P%C3%A3o%20de%20A%C3%A7%C3%BAcar."""
    await session.call_tool("metabooks_search_products", {"search": "Pão de Açúcar"})
    assert api.calls[-1]["query"]["search"] == "Pão de Açúcar"  # httpx codifica no fio


@pytest.mark.parametrize(
    "search",
    [
        "Linux",
        "ST=Janeiro",
        "VL=Editora Contexto and AD=20190301^20190815",
        "VL=Artmed and PF=not EA",
        "VL=Contexto and PR=14^15",
        "ST=linux and PF=E*",
        "RH=AAABX01",
    ],
)
async def test_expressoes_de_busca_da_collection_passam_intactas(session, api, search):
    await session.call_tool("metabooks_search_products", {"search": search})
    assert api.calls[-1]["query"]["search"] == search


async def test_login_logout_conforme_a_collection(client, api):
    await client.get("products", params={"page": 1, "size": 50})
    login = next(c for c in api.calls if c["path"].endswith("/login"))
    assert login["method"] == "POST"
    import json as _json

    assert set(_json.loads(login["body"])) == {"username", "password"}
    await client.logout()
    logout = next(c for c in api.calls if c["path"].endswith("/logout"))
    assert logout["method"] == "GET" and logout["token"]


async def test_publisher_devolve_os_campos_cadastrais(session):
    out = json_of(await session.call_tool(
        "metabooks_get_publisher", {"mvb_id": PUBLISHER_ID}
    ))
    assert {"mvbId", "name", "cnpj", "isbnPrefixes"} <= set(out)
