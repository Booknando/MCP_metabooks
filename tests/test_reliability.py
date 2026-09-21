"""Regressões da revisão 2.8: protocolo, sessões, arquivos e rede."""

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
import gzip
import json
import os
from zipfile import ZipFile

import httpx
import pytest

from metabooks_mcp import client as client_module
from metabooks_mcp.client import MetabooksClient, MetabooksError
from metabooks_mcp.server import load_configuration, diagnostics
from metabooks_mcp.tools._compact import compact_product
from metabooks_mcp.tools._files import save_download, DestinationError
from metabooks_mcp.tools._media import media_extension, downscale_to_jpeg

from .fake_api import PRODUCT_ISBN, PRODUCT_UUID, MMO_FILES, JPEG_BYTES, PDF_BYTES
from .conftest import json_of


@pytest.mark.anyio
async def test_expiracao_local_libera_slot_antes_de_novo_login(client, api):
    await client.get("products")
    old = api.issued_tokens[0]
    client._token_expires_at = 0
    await asyncio.gather(*(client.get("products") for _ in range(8)))
    assert api.logins == 2 and api.logouts == 1
    assert old in api.revoked
    await client.logout()
    assert api.logouts == 2


@pytest.mark.anyio
async def test_renovacao_aguarda_requisicao_em_andamento(client, api):
    await client.get("products")
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        if request.url.params.get("search") == "slow":
            entered.set()
            await release.wait()
            assert api.issued_tokens[0] not in api.revoked
        return await api(request)

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with asyncio.TaskGroup() as group:
        group.create_task(client.get("products", params={"search": "slow"}))
        await entered.wait()
        client._token_expires_at = 0
        waiting = group.create_task(client.get("products"))
        await asyncio.sleep(0)
        assert not waiting.done() and api.logouts == 0
        release.set()
    assert api.logouts == 1 and api.logins == 2


@pytest.mark.anyio
async def test_cancelamento_libera_reserva_de_token(client, api):
    entered = asyncio.Event()

    async def handler(request):
        if request.url.path.endswith("products"):
            entered.set()
            await asyncio.Event().wait()
        return await api(request)

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    task = asyncio.create_task(client.get("products"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(client.logout(), 1)
    assert api.logouts == 1 and client._active_metadata == 0


@pytest.mark.anyio
async def test_falha_de_logout_nao_abre_outro_slot(client, api):
    await client.get("products")
    client._token_expires_at = 0

    async def handler(request):
        if request.url.path.endswith("logout"):
            return httpx.Response(503)
        return await api(request)

    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get("products")
    assert api.logins == 1


@pytest.mark.anyio
@pytest.mark.parametrize("name,args", [
    ("metabooks_view_cover", {"id": PRODUCT_ISBN}),
    ("metabooks_download_cover", {"id": PRODUCT_ISBN}),
    ("metabooks_view_media_asset", {"product_id": PRODUCT_UUID, "media_type": "BACKCOVER"}),
    ("metabooks_download_media_asset", {"product_id": PRODUCT_UUID, "media_type": "BACKCOVER"}),
])
async def test_erros_de_negocio_sao_erros_mcp(session_sem_tokens, name, args):
    result = await session_sem_tokens.call_tool(name, args)
    assert result.isError and result.structuredContent is None
    assert "TOKEN" in json_of(result)["error"]


@pytest.mark.anyio
async def test_http_404_tem_mensagem_consistente(session):
    result = await session.call_tool("metabooks_get_product", {"id": "inexistente"})
    assert result.isError
    assert "HTTP 404" in json_of(result)["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["metabooks_view_media_asset", "metabooks_download_media_asset"])
async def test_indice_negativo_recusado_antes_da_rede(session, api, name):
    before = len(api.calls)
    result = await session.call_tool(name, {"product_id": PRODUCT_UUID, "media_type": "BACKCOVER", "index": -1})
    assert result.isError and len(api.calls) == before


@pytest.mark.anyio
async def test_anotacoes_distinguem_download_de_consulta(session):
    for tool in (await session.list_tools()).tools:
        assert tool.annotations.readOnlyHint == ("download" not in tool.name)
        assert tool.annotations.destructiveHint == ("download" in tool.name)


def test_isbn_nao_vem_de_produto_relacionado():
    data = {"id": "main", "title": "Principal", "identifiers": [
        {"productIdentifierType": "15", "idValue": "9781111111111"}
    ], "relatedProducts": [{"isbn": "9780000000000", "title": "Outro", "priceBrl": 99}]}
    result = compact_product(data)
    assert result["isbn"] == "9781111111111" and "preco" not in result


def test_identidade_e_status_nao_vem_de_editora():
    result = compact_product({"publishers": [{"id": "publisher", "state": "SP", "isbn": "outro", "title": "Editora", "publicationDate": "2020"}]})
    assert not ({"uuid", "isbn", "disponibilidade", "titulo", "data_publicacao"} & result.keys())


def test_preco_e_moeda_vem_do_mesmo_registro():
    result = compact_product({"title": "Livro", "prices": [{"currencyCode": "USD"}, {"priceAmount": 10, "currencyCode": "BRL"}]})
    assert result["preco"] == "10.00 BRL"


def test_wav_e_zip_nao_recebem_extensao_inventada():
    assert media_extension(BytesIO(b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(32))) == "wav"
    plain_zip = BytesIO()
    with ZipFile(plain_zip, "w") as z:
        z.writestr("document.txt", "texto")
    with pytest.raises(MetabooksError):
        media_extension(plain_zip)
    epub = BytesIO()
    with ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    assert media_extension(epub, "application/epub+zip") == "epub"


@pytest.mark.parametrize("data,mime", [(b"<html>erro</html>", "application/pdf"), (PDF_BYTES, "text/html"), (b"%PDF-1.7\nincompleto", "application/pdf")])
def test_rejeita_arquivo_invalido_ou_mime_incompativel(data, mime):
    with pytest.raises(MetabooksError):
        media_extension(BytesIO(data), mime)


@pytest.mark.anyio
async def test_download_wav_e_html_pela_sessao(session, downloads, monkeypatch):
    wav = b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(32)
    monkeypatch.setitem(MMO_FILES, "audio001", wav)
    result = await session.call_tool("metabooks_download_media_asset", {"product_id": PRODUCT_UUID, "media_type": "AUDIO_SAMPLE_CONTENT"})
    path = Path(json_of(result)["path"])
    assert not result.isError and path.suffix == ".wav" and path.read_bytes() == wav
    monkeypatch.setitem(MMO_FILES, "toc00001", b"<html>Erro do proxy</html>")
    result = await session.call_tool("metabooks_download_media_asset", {"product_id": PRODUCT_UUID, "media_type": "TABLE_OF_CONTENT"})
    assert result.isError and not list(downloads.glob("*.pdf"))


def test_limite_de_pixels(monkeypatch):
    from metabooks_mcp.tools import _media
    monkeypatch.setattr(_media, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(MetabooksError, match="pixels"):
        downscale_to_jpeg(JPEG_BYTES)


def test_gravacao_nao_sobrescreve_arquivo_criado_durante_commit(downloads, monkeypatch):
    original = os.link
    target = downloads / "race.pdf"

    def raced_link(source, dest):
        target.write_bytes(b"outro processo")
        original(source, dest)

    monkeypatch.setattr(os, "link", raced_link)
    with pytest.raises(DestinationError):
        save_download(BytesIO(PDF_BYTES), str(target), "race.pdf", "pdf")
    assert target.read_bytes() == b"outro processo"
    assert not list(downloads.glob("*.part"))


def test_falha_na_copia_preserva_original_e_remove_temporario(downloads, monkeypatch):
    from metabooks_mcp.tools import _files
    target = downloads / "original.pdf"
    target.write_bytes(b"original")

    def failed_copy(source, output, **kwargs):
        output.write(b"parcial")
        raise OSError("disco cheio")

    monkeypatch.setattr(_files.shutil, "copyfileobj", failed_copy)
    with pytest.raises(OSError):
        save_download(BytesIO(PDF_BYTES), str(target), "original.pdf", "pdf", True)
    assert target.read_bytes() == b"original"
    assert not list(downloads.glob("*.part"))


def test_env_cwd_e_precedencia(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("METABOOKS_ENV_FILE", raising=False)
    monkeypatch.delenv("METABOOKS_TEST_MARKER", raising=False)
    (tmp_path / ".env").write_text("METABOOKS_TEST_MARKER=arquivo\n", encoding="utf-8")
    load_configuration()
    assert os.environ["METABOOKS_TEST_MARKER"] == "arquivo"
    monkeypatch.setenv("METABOOKS_TEST_MARKER", "ambiente")
    load_configuration()
    assert os.environ["METABOOKS_TEST_MARKER"] == "ambiente"


def test_env_explicito_e_diagnostico_sem_segredos(tmp_path, monkeypatch):
    path = tmp_path / "chosen.env"
    path.write_text("METABOOKS_TEST_SELECTED=sim\n", encoding="utf-8")
    monkeypatch.delenv("METABOOKS_TEST_SELECTED", raising=False)
    assert load_configuration(str(path)) == [str(path)]
    assert os.environ["METABOOKS_TEST_SELECTED"] == "sim"
    monkeypatch.setenv("METABOOKS_PASSWORD", "nao-exibir-123")
    monkeypatch.setenv("METABOOKS_BASE_URL", "https://nao-exibir-123@example.com")
    assert "nao-exibir-123" not in json.dumps(diagnostics())
    with pytest.raises(ValueError):
        load_configuration(str(tmp_path / "missing"))


@pytest.mark.anyio
@pytest.mark.parametrize("method,path", [("GET", "products"), ("POST", "products"), ("POST", "product/multipleProducts")])
async def test_retry_apenas_operacoes_de_consulta(client, monkeypatch, method, path):
    calls, waits = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, json={})

    async def sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.metadata_token = "test"
    await client._send(method, client._build_url(path), scope="metadata", accept="application/json")
    assert len(calls) == 2 and waits == [0]


@pytest.mark.anyio
async def test_nao_repete_post_desconhecido(client):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.metadata_token = "test"
    with pytest.raises(httpx.HTTPStatusError):
        await client.post("unknown")
    assert len(calls) == 1


@pytest.mark.anyio
async def test_retry_limitado_e_retry_after_longo(client, monkeypatch):
    waits = []
    async def sleep(delay):
        waits.append(delay)
    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.metadata_token = "test"
    with pytest.raises(httpx.HTTPStatusError):
        await client.get("products")
    assert len(calls) == 3 and waits == [0.5, 1.0]
    future = format_datetime(datetime.now(timezone.utc) + timedelta(minutes=1))
    assert client._retry_delay(httpx.Response(429, headers={"Retry-After": future}), 0) is None


class Chunks(httpx.AsyncByteStream):
    def __init__(self):
        self.read = 0
        self.closed = False
    async def __aiter__(self):
        for _ in range(5):
            self.read += 1
            yield b"x" * 65536
    async def aclose(self):
        self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize("declared", [False, True])
async def test_download_limitado_com_e_sem_content_length(client, monkeypatch, declared):
    stream = Chunks()
    def handler(request):
        return httpx.Response(200, headers={"Content-Length": "999999"} if declared else {}, stream=stream)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client_module, "MAX_DOWNLOAD_BYTES", 65536)
    client.mmo_token = "test"
    with pytest.raises(MetabooksError, match="limite"):
        async with client.download("asset/mmo/file/test", scope="mmo"):
            pytest.fail("download grande deveria falhar")
    assert stream.closed and stream.read <= 2


@pytest.mark.anyio
async def test_resposta_gzip_nao_e_descompactada_duas_vezes(client):
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=gzip.compress(b'{"ok": true}'), headers={"Content-Encoding": "gzip"}
    )))
    client.metadata_token = "test"
    assert await client.get("products") == {"ok": True}


@pytest.mark.anyio
async def test_retry_de_download_descarta_bytes_da_tentativa_interrompida(client, monkeypatch):
    attempts = []
    class Interrupted(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 65536
            raise httpx.ReadError("interrompido")
    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(200, stream=Interrupted())
        return httpx.Response(200, content=PDF_BYTES)
    async def sleep(delay):
        pass
    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.mmo_token = "test"
    async with client.download("asset/mmo/file/test", scope="mmo") as (file, mime):
        assert file.read() == PDF_BYTES
    assert file.closed and len(attempts) == 2


@pytest.mark.anyio
async def test_login_com_timeout_nao_e_repetido(client):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout")
    await client._http.aclose()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.ReadTimeout):
        await client.get("products")
    assert len(calls) == 1 and calls[0].url.path.endswith("/login")
