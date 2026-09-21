"""Cliente HTTP para a API REST v2 da Metabooks."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import posixpath
import math
import tempfile
import time
import anyio
import httpx
from typing import Any, BinaryIO, Literal
from urllib.parse import quote, urlparse

DEFAULT_BASE_URL = "https://api.metabooks.com/api/v2"
TOKEN_TTL = 50 * 60  # 50 minutos (API expira em 60 min — seção 5.5.1.2)
MAX_INLINE_BYTES = 10 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_RETRIES = 2
MAX_RETRY_WAIT = 10.0

Scope = Literal["metadata", "cover", "mmo"]


class MetabooksError(Exception):
    pass


def path_segment(value: Any) -> str:
    """Codifica um valor para uso como UM único segmento de path.

    ``quote(..., safe="")`` transforma ``/`` em ``%2F``, impedindo que um valor
    vindo do modelo (ISBN, termo de índice, MVB ID, UUID) crie segmentos extras
    e alcance outro endpoint. Segmentos compostos só de pontos (``.``, ``..``)
    são recusados: ``quote`` os deixa intactos e o httpx normalizaria o path,
    escapando da base da API.
    """
    s = str(value if value is not None else "").strip()
    if not s:
        raise MetabooksError("Valor vazio onde a API exige um identificador.")
    if set(s) == {"."}:
        raise MetabooksError(f"Identificador inválido: {s!r}")
    return quote(s, safe="")


class MetabooksClient:
    """Cliente para chamadas à API REST v2 da Metabooks."""

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        metadata_token: str | None = None,
        cover_token: str | None = None,
        mmo_token: str | None = None,
        base_url: str | None = None,
    ):
        self.username = username
        self.password = password
        self.metadata_token = metadata_token
        self.cover_token = cover_token
        self.mmo_token = mmo_token
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)
        self._login_token: str | None = None
        self._token_expires_at: float = 0.0
        # Serializa o login: sem isto, N chamadas simultâneas disparam N logins e
        # cada um ocupa um slot de sessão paralela da MVB, liberado só após 60 min.
        self._login_lock = asyncio.Lock()
        self._login_idle = asyncio.Condition(self._login_lock)
        self._active_metadata = 0

    # --- Autenticação ----------------------------------------------------------

    def _token_is_fresh(self) -> bool:
        return bool(self._login_token) and self._token_expires_at > time.monotonic()

    async def _get_metadata_token(self) -> str:
        if self.metadata_token:
            return self.metadata_token
        async with self._login_idle:
            return await self._ensure_token_locked()

    async def _ensure_token_locked(self) -> str:
        # O lock protege tanto a renovação como a reserva de uso do token.
        # Nenhuma sessão é encerrada enquanto uma requisição ainda a utiliza.
        while not self._token_is_fresh():
            if self._active_metadata:
                await self._login_idle.wait()
                continue
            if self._login_token:
                await self._logout_token(self._login_token)
                self._login_token = None
            self._login_token = await self._do_login()
            self._token_expires_at = time.monotonic() + TOKEN_TTL
        return self._login_token  # type: ignore[return-value]

    @asynccontextmanager
    async def _token_lease(self, scope: Scope):
        if scope != "metadata" or self.metadata_token:
            yield await self._token_for(scope)
            return
        async with self._login_idle:
            token = await self._ensure_token_locked()
            self._active_metadata += 1
        try:
            yield token
        finally:
            with anyio.CancelScope(shield=True):
                async with self._login_idle:
                    self._active_metadata -= 1
                    self._login_idle.notify_all()

    async def _logout_token(self, token: str) -> None:
        response = await self._http.get(
            f"{self.base_url}/logout", headers={"Authorization": f"Bearer {token}"}
        )
        # Um 401 já significa que esta sessão não é mais utilizável.
        if response.status_code != 401:
            response.raise_for_status()

    async def _do_login(self) -> str:
        if not self.username or not self.password:
            raise MetabooksError(
                "Sem credenciais de metadados. Configure METABOOKS_USERNAME/METABOOKS_PASSWORD "
                "ou METABOOKS_METADATA_TOKEN."
            )
        response = await self._http.post(
            f"{self.base_url}/login",
            json={"username": self.username, "password": self.password},
        )
        if response.status_code == 401:
            raise MetabooksError(
                "Login falhou: credenciais inválidas. Verifique METABOOKS_USERNAME/METABOOKS_PASSWORD."
            )
        response.raise_for_status()
        # A API de produção retorna o token como string crua (sem content-type JSON),
        # então response.json() estoura. Tenta JSON e cai para o corpo bruto.
        try:
            data = response.json()
        except ValueError:
            data = response.text
        if isinstance(data, str):
            token = data.strip().strip('"')
        elif isinstance(data, dict):
            token = data.get("accessToken") or data.get("access_token") or data.get("token", "")
        else:
            token = None
        if not isinstance(token, str) or not token.strip():
            raise MetabooksError(
                "Login bem-sucedido, mas não foi possível extrair o accessToken da resposta."
            )
        return str(token).strip()

    async def logout(self) -> None:
        """Libera o token de login no servidor (seção 5.5.3.2).

        Só faz sentido para login status-based (usuário/senha): cada login ocupa
        um slot paralelo limitado pela MVB, que de outra forma só é liberado após
        o timeout de 60 min. Tokens estáticos (metadata_token) não fazem login,
        então não há nada a deslogar. Best-effort: erros são ignorados.
        """
        if self.metadata_token:
            return
        async with self._login_idle:
            while self._active_metadata:
                await self._login_idle.wait()
            token = self._login_token
            if not token:
                return
            try:
                await self._logout_token(token)
            except Exception:
                pass
            finally:
                self._login_token = None
                self._token_expires_at = 0.0

    async def _token_for(self, scope: Scope) -> str:
        if scope == "metadata":
            return await self._get_metadata_token()
        if scope == "cover":
            if not self.cover_token:
                raise MetabooksError(
                    "Token de capa não configurado. Defina METABOOKS_COVER_TOKEN."
                )
            return self.cover_token
        if scope == "mmo":
            if not self.mmo_token:
                raise MetabooksError(
                    "Token de MMO não configurado. Defina METABOOKS_MMO_TOKEN."
                )
            return self.mmo_token
        raise MetabooksError(f"Escopo desconhecido: {scope}")

    # --- Montagem de URL -------------------------------------------------------

    def _build_url(self, path: str) -> str:
        """Junta ``path`` à base e recusa qualquer coisa que escape dela.

        Rede de segurança para o caso de um caminho chegar sem passar por
        ``path_segment``: o httpx normaliza segmentos ``..`` na hora de enviar,
        de modo que ``product/../../../v1/x`` sairia como ``/v1/x``. Aqui
        qualquer segmento ``.``/``..`` é recusado de saída — nenhum endpoint da
        API os usa — e o resultado ainda tem de ficar dentro do prefixo da base
        (ex.: ``/api/v2``), o que também barra alcançar um endpoint irmão.
        """
        if any(seg in (".", "..") for seg in path.split("/")):
            raise MetabooksError(f"Caminho fora da base da API: {path}")
        url = f"{self.base_url}/{path.lstrip('/')}"
        parsed = urlparse(url)
        base = urlparse(self.base_url)
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raise MetabooksError(f"URL fora do host da API: {url}")
        normalized = posixpath.normpath(parsed.path)
        base_path = posixpath.normpath(base.path) if base.path else "/"
        if normalized != base_path and not normalized.startswith(base_path.rstrip("/") + "/"):
            raise MetabooksError(
                f"Caminho fora da base da API ({base_path}): {parsed.path}"
            )
        return url

    def _same_api_host(self, url: str) -> bool:
        """Verifica se uma URL ABSOLUTA pertence à mesma API que ``base_url``.

        Exige esquema, host e porta idênticos e um path sob o prefixo comum da
        API (o pai de ``base_url``, ex.: ``/api``) — as URLs de arquivo do MMO
        apontam para ``/api/v1/...`` enquanto a base é ``/api/v2``.
        """
        target = urlparse(url)
        base = urlparse(self.base_url)
        if target.scheme != base.scheme:
            return False
        if (target.hostname or "").lower() != (base.hostname or "").lower():
            return False
        if (target.port or (443 if target.scheme == "https" else 80)) != (
            base.port or (443 if base.scheme == "https" else 80)
        ):
            return False
        api_root = posixpath.dirname(posixpath.normpath(base.path or "/")) or "/"
        normalized = posixpath.normpath(target.path or "/")
        return normalized == api_root or normalized.startswith(api_root.rstrip("/") + "/")

    # --- Requisições -----------------------------------------------------------

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float | None:
        value = response.headers.get("Retry-After") if response is not None else None
        if value:
            try:
                delay = float(value)
            except ValueError:
                try:
                    date = parsedate_to_datetime(value)
                    delay = (date - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = 0.5 * 2 ** attempt
            # Não adiantar uma repetição que o servidor pediu para fazer mais tarde.
            if not math.isfinite(delay) or delay > MAX_RETRY_WAIT:
                return None
            return max(0.0, delay)
        return 0.5 * 2 ** attempt

    async def _request(self, method: str, url: str, *, sink: BinaryIO | None = None,
                       max_bytes: int | None = None, **kwargs) -> httpx.Response:
        safe_post = url in {
            self._build_url("products"), self._build_url("product/multipleProducts")
        }
        retryable = method == "GET" or (method == "POST" and safe_post)
        for attempt in range(MAX_RETRIES + 1):
            response = None
            try:
                if sink is not None:
                    await anyio.to_thread.run_sync(sink.seek, 0)
                    await anyio.to_thread.run_sync(sink.truncate, 0)
                async with self._http.stream(method, url, **kwargs) as response:
                    response.raise_for_status()
                    length = response.headers.get("Content-Length", "")
                    if max_bytes is not None and length.isdigit() and int(length) > max_bytes:
                        raise MetabooksError("Arquivo excede o limite de download permitido.")
                    body = bytearray()
                    count = 0
                    async for chunk in response.aiter_bytes(64 * 1024):
                        count += len(chunk)
                        if max_bytes is not None and count > max_bytes:
                            raise MetabooksError("Arquivo excede o limite de download permitido.")
                        if sink is None:
                            body.extend(chunk)
                        else:
                            await anyio.to_thread.run_sync(sink.write, chunk)
                    headers = {key: value for key, value in response.headers.items()
                               if key.lower() not in {"content-encoding", "content-length"}}
                    return httpx.Response(response.status_code, headers=headers,
                                          content=bytes(body), request=response.request)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                transient = isinstance(exc, httpx.TransportError) or (
                    exc.response.status_code in (429, 500, 502, 503, 504)
                )
                delay = self._retry_delay(response, attempt)
                if not retryable or not transient or attempt == MAX_RETRIES or delay is None:
                    raise
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _send(
        self,
        method: str,
        url: str,
        *,
        scope: Scope,
        accept: str,
        params: dict | None = None,
        json: Any = None,
        sink: BinaryIO | None = None,
        max_bytes: int | None = None,
    ) -> httpx.Response:
        """Envia a requisição autenticada, renovando o token de login em 401.

        O retry vale para qualquer verbo (GET, POST, download binário) e só para
        o escopo de metadados obtido por login — tokens estáticos não têm o que
        renovar.
        """
        can_retry = scope == "metadata" and not self.metadata_token
        for auth_attempt in range(2):
            try:
                async with self._token_lease(scope) as token:
                    headers = {"Authorization": f"Bearer {token}", "Accept": accept}
                    if json is not None:
                        headers["Content-Type"] = "application/json"
                    return await self._request(
                        method, url, headers=headers, params=params, json=json,
                        sink=sink, max_bytes=max_bytes,
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 401 or not can_retry or auth_attempt:
                    raise
                async with self._login_idle:
                    if self._login_token == token:
                        self._token_expires_at = 0.0
        raise AssertionError("unreachable")

    async def get(
        self,
        path: str,
        scope: Scope = "metadata",
        params: dict | None = None,
        accept: str = "application/json",
    ) -> Any:
        """GET autenticado. Renova token de login automaticamente em caso de 401."""
        response = await self._send(
            "GET", self._build_url(path), scope=scope, accept=accept, params=params
        )
        # json e json-short são ambos JSON; ONIX (onix30-*) volta como texto/XML.
        return response.json() if accept.startswith("application/json") else response.text

    async def get_bytes(
        self,
        path: str,
        scope: Scope = "metadata",
        params: dict | None = None,
        accept: str = "*/*",
    ) -> bytes:
        """GET autenticado que retorna o corpo binário (capas, mídias).

        Usado para baixar a imagem da capa (image/jpeg) e devolvê-la diretamente,
        sem expor o token numa URL — a seção 5.5.5/5.10.1 da especificação pede
        que o token não seja legível a partir da URL da capa.
        """
        response = await self._send(
            "GET", self._build_url(path), scope=scope, accept=accept, params=params, max_bytes=MAX_INLINE_BYTES
        )
        return response.content

    async def get_bytes_from_url(
        self,
        url: str,
        scope: Scope = "mmo",
        accept: str = "*/*",
        params: dict | None = None,
    ) -> bytes:
        """GET binário de uma URL ABSOLUTA autenticada (ex.: links de mídia/MMO).

        O endpoint de mídia (`/asset/mmo/{productId}`) devolve URLs de arquivo já
        prontas (apontando para `/api/v1/asset/mmo/file/{id}`), enquanto a base é
        `/api/v2`. Buscar a URL exata do listing evita reconstruir o path e é
        robusto a v1/v2. Guarda anti-SSRF: esquema, host, porta e prefixo de path
        têm de bater com base_url — assim o token nunca vaza para outro destino
        nem viaja em texto claro.
        """
        if not self._same_api_host(url):
            raise MetabooksError(f"URL fora da API permitida ({self.base_url}): {url}")
        response = await self._send("GET", url, scope=scope, accept=accept, params=params,
                                    max_bytes=MAX_INLINE_BYTES)
        return response.content

    @asynccontextmanager
    async def download(self, path: str, *, scope: Scope, absolute: bool = False):
        """Baixa em streaming para temporário, limitado a 50 MiB e fechado mesmo em erro."""
        url = path if absolute else self._build_url(path)
        if absolute and not self._same_api_host(url):
            raise MetabooksError("URL fora da API permitida.")
        file = await anyio.to_thread.run_sync(tempfile.TemporaryFile)
        try:
            response = await self._send("GET", url, scope=scope, accept="*/*",
                                        sink=file, max_bytes=MAX_DOWNLOAD_BYTES)
            await anyio.to_thread.run_sync(file.seek, 0)
            yield file, response.headers.get("Content-Type", "")
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(file.close)

    async def post(
        self,
        path: str,
        scope: Scope = "metadata",
        json: Any = None,
        params: dict | None = None,
        accept: str = "application/json",
    ) -> Any:
        """POST autenticado com corpo JSON.

        ``accept`` controla o formato da resposta: ``application/json`` (long,
        padrão) ou ``application/json-short`` (representação compacta nativa da
        API, bem menor). O corpo enviado é sempre JSON normal — só o cabeçalho
        Accept muda o formato de saída.
        """
        response = await self._send(
            "POST",
            self._build_url(path),
            scope=scope,
            accept=accept,
            params=params,
            json=json if json is not None else {},
        )
        return response.json()

    async def aclose(self) -> None:
        await self._http.aclose()
