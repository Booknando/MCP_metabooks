"""Cliente HTTP: autenticação, concorrência, retry de 401 e guardas de URL."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from metabooks_mcp.client import MetabooksClient, MetabooksError, path_segment

from .fake_api import COVER_TOKEN, METADATA_TOKEN, MMO_TOKEN, PRODUCT_ISBN

pytestmark = pytest.mark.anyio


# --- login / token ----------------------------------------------------------

async def test_login_aceita_token_como_texto_cru(client, api):
    await client.get("products", params={"page": 1, "size": 50, "search": "Linux"})
    assert api.logins == 1
    assert api.calls[-1]["token"] == METADATA_TOKEN


async def test_token_reaproveitado_entre_chamadas(client, api):
    for _ in range(3):
        await client.get("products", params={"page": 1, "size": 50})
    assert api.logins == 1


async def test_token_estatico_nao_faz_login(make_client, api):
    c = make_client(username=None, password=None, metadata_token=METADATA_TOKEN)
    await c.get("products", params={"page": 1, "size": 50})
    assert api.logins == 0


async def test_sem_credenciais_erro_explicativo(make_client):
    c = make_client(username=None, password=None)
    with pytest.raises(MetabooksError, match="Sem credenciais de metadados"):
        await c.get("products")


async def test_credencial_invalida_mensagem_amigavel(make_client):
    c = make_client(username="errado", password="errado")
    with pytest.raises(MetabooksError, match="credenciais inválidas"):
        await c.get("products")


async def test_login_concorrente_usa_um_unico_slot(client, api):
    """Cada login ocupa um slot de sessão paralela da MVB por até 60 min."""
    api.login_delay = 0.02
    await asyncio.gather(
        *[client.get("products", params={"page": 1, "size": 50}) for _ in range(8)]
    )
    assert api.logins == 1


async def test_logout_libera_o_token(client, api):
    await client.get("products", params={"page": 1, "size": 50})
    await client.logout()
    assert api.logouts == 1
    assert client._login_token is None


async def test_logout_e_noop_com_token_estatico(make_client, api):
    c = make_client(username=None, password=None, metadata_token=METADATA_TOKEN)
    await c.get("products", params={"page": 1, "size": 50})
    await c.logout()
    assert api.logouts == 0


# --- retry de 401 -----------------------------------------------------------

async def test_get_renova_token_em_401(client, api):
    await client.get("products", params={"page": 1, "size": 50})
    api.revoke_all_issued()
    await client.get("products", params={"page": 1, "size": 50})
    assert api.logins == 2


async def test_post_renova_token_em_401(client, api):
    """Busca em lote e multipleProducts são POST — precisam do mesmo retry."""
    await client.get("products", params={"page": 1, "size": 50})
    api.revoke_all_issued()
    data = await client.post("products", json={"content": [{"isbn": PRODUCT_ISBN}]})
    assert api.logins == 2
    assert data["content"]


async def test_get_bytes_renova_token_em_401(client, api):
    """O retry vale também para downloads binários no escopo de metadados."""
    await client.get("products", params={"page": 1, "size": 50})
    api.revoke_all_issued()
    data = await client.get_bytes(
        "products", params={"page": 1, "size": 50}, accept="application/json"
    )
    assert api.logins == 2 and data


async def test_401_concorrente_faz_um_unico_relogin(client, api):
    await client.get("products", params={"page": 1, "size": 50})
    api.login_delay = 0.02
    api.revoke_all_issued()
    await asyncio.gather(
        *[client.get("products", params={"page": 1, "size": 50}) for _ in range(4)]
    )
    assert api.logins == 2  # o inicial + um único relogin compartilhado


async def test_escopo_de_capa_nao_tenta_relogin(client, api):
    """Capa/MMO usam token estático: não há o que renovar, o erro sobe."""
    await client.get("products", params={"page": 1, "size": 50})
    api.force_401 = 1
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_bytes(f"cover/{PRODUCT_ISBN}/m", scope="cover")
    assert api.logins == 1


async def test_token_estatico_nao_tenta_relogin(make_client, api):
    c = make_client(username=None, password=None, metadata_token=METADATA_TOKEN)
    api.revoked.add(METADATA_TOKEN)
    with pytest.raises(httpx.HTTPStatusError):
        await c.get("products", params={"page": 1, "size": 50})
    assert api.logins == 0


# --- escopos ----------------------------------------------------------------

@pytest.mark.parametrize(
    "scope,env,mensagem",
    [("cover", "METABOOKS_COVER_TOKEN", "Token de capa"),
     ("mmo", "METABOOKS_MMO_TOKEN", "Token de MMO")],
)
async def test_escopo_sem_token_erro_explicativo(make_client, scope, env, mensagem):
    c = make_client()
    with pytest.raises(MetabooksError, match=mensagem):
        await c.get_bytes("cover/x", scope=scope)


async def test_escopos_usam_tokens_distintos(client, api):
    await client.get_bytes(f"cover/{PRODUCT_ISBN}/m", scope="cover")
    assert api.calls[-1]["token"] == COVER_TOKEN
    await client.get("asset/mmo/747b3a57d4154dd9b00fbe3bcd9d077e", scope="mmo")
    assert api.calls[-1]["token"] == MMO_TOKEN


# --- path_segment -----------------------------------------------------------

def test_path_segment_codifica_barras():
    assert path_segment("a/b") == "a%2Fb"


def test_path_segment_recusa_pontos():
    for valor in ("..", ".", "..."):
        with pytest.raises(MetabooksError):
            path_segment(valor)


def test_path_segment_recusa_vazio():
    with pytest.raises(MetabooksError):
        path_segment("   ")


def test_path_segment_preserva_acentos_codificados():
    assert path_segment("Pão") == "P%C3%A3o"


# --- guarda de path (_build_url) -------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "index/author/../../publisher/BR0090012",
        "product/../../../v1/asset/mmo/file/back0001",
        "../login",
        "publisher/../../../../etc/passwd",
    ],
)
async def test_build_url_recusa_escapar_da_base(client, path):
    with pytest.raises(MetabooksError, match="fora da base da API"):
        await client.get(path)


async def test_build_url_aceita_caminho_normal(client, api):
    await client.get("publisher/BR0090012")
    assert api.calls[-1]["path"] == "/api/v2/publisher/BR0090012"


# --- guarda de host (get_bytes_from_url) -----------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/api/v1/asset/mmo/file/back0001",
        "https://api.metabooks.com.evil.com/api/v1/x",
        "http://api.metabooks.com/api/v1/asset/mmo/file/back0001",   # esquema
        "https://api.metabooks.com:8443/api/v1/asset/mmo/file/x",    # porta
        "https://api.metabooks.com/internal/admin",                  # fora de /api
    ],
)
async def test_guarda_de_host_bloqueia(client, url):
    with pytest.raises(MetabooksError, match="fora da API permitida"):
        await client.get_bytes_from_url(url, scope="mmo")


async def test_guarda_de_host_permite_v1_da_mesma_api(client):
    data = await client.get_bytes_from_url(
        "https://api.metabooks.com/api/v1/asset/mmo/file/back0001", scope="mmo"
    )
    assert data[:3] == b"\xff\xd8\xff"


async def test_nenhum_token_viaja_em_querystring(client, api):
    await client.get_bytes(f"cover/{PRODUCT_ISBN}/m", scope="cover")
    await client.get("products", params={"page": 1, "size": 50, "search": "Linux"})
    for call in api.calls:
        assert "access_token" not in call["query"]
        assert not any("token" in k.lower() for k in call["query"])


# --- formatos ---------------------------------------------------------------

async def test_onix_volta_como_texto(client):
    data = await client.get(
        f"product/{PRODUCT_ISBN}/isbn13", accept="application/onix30-short"
    )
    assert isinstance(data, str) and data.startswith("<?xml")


async def test_json_short_volta_decodificado(client):
    data = await client.get(
        "products", params={"page": 1, "size": 50}, accept="application/json-short"
    )
    assert isinstance(data, dict) and "content" in data
