"""Fixtures compartilhadas: API falsa, cliente e sessão MCP em memória."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from metabooks_mcp.client import MetabooksClient
from metabooks_mcp.tools import _files

from .fake_api import (
    COVER_TOKEN,
    LOGIN_PASSWORD,
    LOGIN_USERNAME,
    MMO_TOKEN,
    FakeMetabooksAPI,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def anyio_backend() -> str:
    """Roda a suíte assíncrona no plugin do anyio.

    O anyio executa fixture e teste na MESMA task, o que é necessário porque a
    sessão MCP em memória usa task groups (com o pytest-asyncio o setup e o corpo
    do teste caem em tasks diferentes e o cancel scope estoura).
    """
    return "asyncio"


@pytest.fixture
def api() -> FakeMetabooksAPI:
    return FakeMetabooksAPI()


@pytest.fixture
def make_client(api):
    """Fábrica de MetabooksClient já ligado à API falsa."""

    created: list[MetabooksClient] = []

    def factory(**kwargs) -> MetabooksClient:
        kwargs.setdefault("username", LOGIN_USERNAME)
        kwargs.setdefault("password", LOGIN_PASSWORD)
        c = MetabooksClient(**kwargs)
        c._http = httpx.AsyncClient(
            timeout=5.0, transport=httpx.MockTransport(api)
        )
        created.append(c)
        return c

    yield factory


@pytest.fixture
def client(make_client) -> MetabooksClient:
    return make_client(cover_token=COVER_TOKEN, mmo_token=MMO_TOKEN)


@pytest.fixture
def downloads(tmp_path, monkeypatch) -> Path:
    """Confina os downloads numa pasta temporária durante os testes."""
    target = tmp_path / "downloads"
    target.mkdir()
    monkeypatch.setenv(_files.ENV_DOWNLOAD_DIR, str(target))
    return target


@asynccontextmanager
async def _mcp_session(api, monkeypatch, *, media_tokens: bool):
    """Monta o servidor como o ``main()`` monta e conecta um cliente em memória.

    Exercita o caminho real: lifespan, registro das tools no FastMCP, validação
    de schema dos argumentos pelo SDK e serialização do resultado.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    monkeypatch.setenv("METABOOKS_USERNAME", LOGIN_USERNAME)
    monkeypatch.setenv("METABOOKS_PASSWORD", LOGIN_PASSWORD)
    monkeypatch.delenv("METABOOKS_METADATA_TOKEN", raising=False)
    monkeypatch.delenv("METABOOKS_BASE_URL", raising=False)
    if media_tokens:
        monkeypatch.setenv("METABOOKS_COVER_TOKEN", COVER_TOKEN)
        monkeypatch.setenv("METABOOKS_MMO_TOKEN", MMO_TOKEN)
    else:
        monkeypatch.delenv("METABOOKS_COVER_TOKEN", raising=False)
        monkeypatch.delenv("METABOOKS_MMO_TOKEN", raising=False)

    original_init = MetabooksClient.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._http = httpx.AsyncClient(timeout=5.0, transport=httpx.MockTransport(api))

    monkeypatch.setattr(MetabooksClient, "__init__", patched_init)

    from metabooks_mcp.server import lifespan
    from metabooks_mcp.tools import capas, editora, indice, midia, produtos

    mcp = FastMCP(name="metabooks-mcp-test", instructions="teste", lifespan=lifespan)
    for module in (produtos, capas, midia, indice, editora):
        module.register(mcp)

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        yield s


@pytest.fixture
async def session(api, monkeypatch, downloads):
    """Sessão MCP com todos os tokens configurados."""
    async with _mcp_session(api, monkeypatch, media_tokens=True) as s:
        yield s


@pytest.fixture
async def session_sem_tokens(api, monkeypatch, downloads):
    """Sessão MCP só com credenciais de metadados (sem capa nem MMO)."""
    async with _mcp_session(api, monkeypatch, media_tokens=False) as s:
        yield s


@pytest.fixture(scope="session")
def postman_collection() -> dict:
    path = FIXTURES / "Metabooks.postman_collection.json"
    return json.loads(path.read_text(encoding="utf-8"))


def text_of(result) -> str:
    """Concatena os blocos de texto de um resultado de tool."""
    return "\n".join(c.text for c in result.content if c.type == "text")


def json_of(result):
    """Decodifica o resultado JSON de uma tool."""
    return json.loads(text_of(result))


def images_of(result) -> list[bytes]:
    import base64

    return [
        base64.b64decode(c.data) for c in result.content if c.type == "image"
    ]
