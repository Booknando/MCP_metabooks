"""Cliente HTTP para a API REST v2 da Metabooks."""

import time
import httpx
from typing import Any, Literal

DEFAULT_BASE_URL = "https://api.metabooks.com/api/v2"
TOKEN_TTL = 50 * 60  # 50 minutos (API expira em 60 min — seção 5.5.1.2)

Scope = Literal["metadata", "cover", "mmo"]


class MetabooksError(Exception):
    pass


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

    # --- Autenticação ----------------------------------------------------------

    async def _get_metadata_token(self) -> str:
        if self.metadata_token:
            return self.metadata_token
        now = time.time()
        if self._login_token and self._token_expires_at > now:
            return self._login_token
        token = await self._do_login()
        self._login_token = token
        self._token_expires_at = now + TOKEN_TTL
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
        data = response.json()
        if isinstance(data, str):
            return data.strip()
        token = data.get("accessToken") or data.get("access_token") or data.get("token", "")
        if not token:
            raise MetabooksError(
                "Login bem-sucedido, mas não foi possível extrair o accessToken da resposta."
            )
        return str(token).strip()

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

    # --- Requisições -----------------------------------------------------------

    async def get(
        self,
        path: str,
        scope: Scope = "metadata",
        params: dict | None = None,
        accept: str = "application/json",
    ) -> Any:
        """GET autenticado. Renova token de login automaticamente em caso de 401."""
        token = await self._token_for(scope)
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        try:
            response = await self._http.get(url, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code == 401
                and scope == "metadata"
                and not self.metadata_token
            ):
                self._login_token = None
                token = await self._do_login()
                self._login_token = token
                self._token_expires_at = time.time() + TOKEN_TTL
                headers["Authorization"] = f"Bearer {token}"
                response = await self._http.get(url, headers=headers, params=params)
                response.raise_for_status()
            else:
                raise
        return response.json() if accept == "application/json" else response.text

    async def post(
        self,
        path: str,
        scope: Scope = "metadata",
        json: Any = None,
        params: dict | None = None,
    ) -> Any:
        """POST autenticado com corpo JSON."""
        token = await self._token_for(scope)
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        response = await self._http.post(url, headers=headers, json=json, params=params)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._http.aclose()
