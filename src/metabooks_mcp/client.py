"""Cliente HTTP para a API REST v2 da Metabooks."""

import asyncio
import posixpath
import time
import httpx
from typing import Any, Literal
from urllib.parse import quote, urlparse

DEFAULT_BASE_URL = "https://api.metabooks.com/api/v2"
TOKEN_TTL = 50 * 60  # 50 minutos (API expira em 60 min — seção 5.5.1.2)

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

    # --- Autenticação ----------------------------------------------------------

    def _token_is_fresh(self) -> bool:
        return bool(self._login_token) and self._token_expires_at > time.time()

    async def _get_metadata_token(self) -> str:
        if self.metadata_token:
            return self.metadata_token
        if self._token_is_fresh():
            return self._login_token  # type: ignore[return-value]
        async with self._login_lock:
            # Outra corrotina pode ter logado enquanto esperávamos o lock.
            if self._token_is_fresh():
                return self._login_token  # type: ignore[return-value]
            token = await self._do_login()
            self._login_token = token
            # TTL contado APÓS o round-trip do login, não antes.
            self._token_expires_at = time.time() + TOKEN_TTL
            return token

    async def _relogin(self, stale_token: str) -> str:
        """Renova o token depois de um 401, sem disparar logins concorrentes."""
        async with self._login_lock:
            if self._login_token != stale_token and self._token_is_fresh():
                return self._login_token  # type: ignore[return-value]
            self._login_token = None
            self._token_expires_at = 0.0
            token = await self._do_login()
            self._login_token = token
            self._token_expires_at = time.time() + TOKEN_TTL
            return token

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
        else:
            token = data.get("accessToken") or data.get("access_token") or data.get("token", "")
        if not token:
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
        async with self._login_lock:
            token = self._login_token
            if not token:
                return
            try:
                await self._http.get(
                    f"{self.base_url}/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )
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

    async def _send(
        self,
        method: str,
        url: str,
        *,
        scope: Scope,
        accept: str,
        params: dict | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """Envia a requisição autenticada, renovando o token de login em 401.

        O retry vale para qualquer verbo (GET, POST, download binário) e só para
        o escopo de metadados obtido por login — tokens estáticos não têm o que
        renovar.
        """
        token = await self._token_for(scope)
        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        if json is not None:
            headers["Content-Type"] = "application/json"
        can_retry = scope == "metadata" and not self.metadata_token
        try:
            response = await self._http.request(
                method, url, headers=headers, params=params, json=json
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401 or not can_retry:
                raise
        headers["Authorization"] = f"Bearer {await self._relogin(token)}"
        response = await self._http.request(
            method, url, headers=headers, params=params, json=json
        )
        response.raise_for_status()
        return response

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
            "GET", self._build_url(path), scope=scope, accept=accept, params=params
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
        response = await self._send("GET", url, scope=scope, accept=accept, params=params)
        return response.content

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
