"""API Metabooks falsa para os testes.

Não é um mock permissivo: reproduz as regras que a API real impõe e que estão
documentadas na collection Postman oficial
(``tests/fixtures/Metabooks.postman_collection.json``), de modo que um teste que
passa aqui exercitou o contrato, não só o código.

Regras aplicadas
----------------
* ``Authorization: Bearer <token>`` obrigatório fora do ``/login``; token errado
  para o escopo do endpoint devolve 403 (valida o roteamento de escopo
  metadata/cover/mmo).
* ``/product/multipleProducts`` responde 406 a ``Accept: application/json-short``
  ou ONIX — a collection anota "only in json format".
* ``/cover/...`` responde 406 a ``Accept: image/jpeg`` e 403 a ``image/*``; só
  ``*/*`` devolve o binário.
* Paths desconhecidos devolvem 404, de forma que uma travessia de caminho bem
  ou malsucedida fique visível no teste.
"""

from __future__ import annotations

import json
import re
from io import BytesIO

import httpx
from PIL import Image as PILImage

METADATA_TOKEN_PREFIX = "TOKEN-METADATA-"
# Token emitido pelo primeiro login (a API real devolve um token novo por login).
METADATA_TOKEN = METADATA_TOKEN_PREFIX + "1"
COVER_TOKEN = "TOKEN-COVER"
MMO_TOKEN = "TOKEN-MMO"
LOGIN_USERNAME = "usuario"
LOGIN_PASSWORD = "senha"


def is_metadata_token(token: str | None) -> bool:
    return bool(token) and token.startswith(METADATA_TOKEN_PREFIX)


def _jpeg(width: int = 1400, height: int = 2100) -> bytes:
    buf = BytesIO()
    PILImage.new("RGB", (width, height), (17, 34, 51)).save(buf, "JPEG")
    return buf.getvalue()


JPEG_BYTES = _jpeg()
PDF_BYTES = b"%PDF-1.7\n" + b"0" * 400 + b"\n%%EOF"
MP3_BYTES = b"ID3\x03\x00\x00\x00" + b"\x00" * 200

PRODUCT_UUID = "747b3a57d4154dd9b00fbe3bcd9d077e"
PRODUCT_ISBN = "9788087062272"
PUBLISHER_ID = "BR0090012"

# Forma "long"/"json-short" da busca: campos planos (conferidos em 2026-07).
FLAT_MAIN = {
    "id": PRODUCT_UUID,
    "isbn": PRODUCT_ISBN,
    "title": "Dom Casmurro",
    "subTitle": "edição comentada",
    "publisher": "Editora Contexto",
    "publicationDate": "2020-05-01",
    "productType": "pbook",
    "productFormId": "BC",
    "priceBrl": 59.9,
    "author": "Machado de Assis",
    "state": "active",
    "language": "por",
    "mainDescription": "Sinopse longa. " * 60,
}
# Ruído: o termo buscado aparece na sinopse e dentro de um título mais longo.
FLAT_NOISE_TITLE = dict(
    FLAT_MAIN,
    id="a1b2c3d4e5f60718293a4b5c6d7e8f90",
    isbn="9780000000001",
    title="Análise de Dom Casmurro para o Enem",
    subTitle=None,
)
FLAT_NOISE_DESC = dict(
    FLAT_MAIN,
    id="b1b2c3d4e5f60718293a4b5c6d7e8f90",
    isbn="9780000000002",
    title="Memórias Póstumas de Brás Cubas",
    subTitle=None,
)

# Forma "long" do detalhe: estilo ONIX aninhado.
DETAIL_ONIX = {
    "id": PRODUCT_UUID,
    "titles": [{"title": "Dom Casmurro", "subTitle": "edição comentada"}],
    "identifiers": [
        {"productIdentifierType": "02", "idValue": "8087062272"},
        {"productIdentifierType": "15", "idValue": PRODUCT_ISBN},
    ],
    "contributors": [
        {"firstName": "Machado", "lastName": "de Assis", "contributorRole": "A01"},
        {"firstName": "Ana", "lastName": "Trad", "contributorRole": "B06"},
    ],
    "prices": [{"priceAmount": 59.9, "currencyCode": "BRL"}],
    "form": {"productForm": "BC"},
    "extent": {"mainContentPageCount": 256},
    "languages": [{"languageCode": "por", "languageRole": "01"}],
    "publishers": [{"publisherName": "Editora Contexto"}],
    "publicationDate": "2020-05-01",
    "productAvailability": "40",
    "active": True,
    "description": "Descrição longa do detalhe. " * 40,
}

ONIX_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<ONIXMessage release=\"3.0\"><Product><RecordReference>"
    f"{PRODUCT_UUID}</RecordReference></Product></ONIXMessage>"
)

MMO_ASSETS = [
    {
        "type": "FRONTCOVER",
        "sequenceNumber": 1,
        "url": f"https://api.metabooks.com/api/v2/cover/{PRODUCT_ISBN}",
    },
    {
        "type": "BACKCOVER",
        "sequenceNumber": 1,
        "url": "https://api.metabooks.com/api/v1/asset/mmo/file/back0001",
    },
    {
        "type": "TABLE_OF_CONTENT",
        "sequenceNumber": 1,
        "url": "https://api.metabooks.com/api/v1/asset/mmo/file/toc00001",
    },
    {
        "type": "IMAGE_SAMPLE_CONTENT",
        "sequenceNumber": 2,
        "url": "https://api.metabooks.com/api/v1/asset/mmo/file/sample02",
    },
    {
        "type": "IMAGE_SAMPLE_CONTENT",
        "sequenceNumber": 1,
        "url": "https://api.metabooks.com/api/v1/asset/mmo/file/sample01",
    },
    {
        "type": "AUDIO_SAMPLE_CONTENT",
        "sequenceNumber": 1,
        "url": "https://api.metabooks.com/api/v1/asset/mmo/file/audio001",
    },
]

MMO_FILES = {
    "back0001": JPEG_BYTES,
    "toc00001": PDF_BYTES,
    "sample01": JPEG_BYTES,
    "sample02": JPEG_BYTES,
    "audio001": MP3_BYTES,
}

_ID_TYPES = {"isbn13", "ean", "gtin"}


class FakeMetabooksAPI:
    """Handler para ``httpx.MockTransport`` que registra e valida as chamadas."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.logins = 0
        self.logouts = 0
        self.issued_tokens: list[str] = []
        # Quantos próximos acessos autenticados devem responder 401 (token velho).
        self.force_401 = 0
        self.login_delay: float = 0.0
        self.revoked: set[str] = set()

    # --- utilidades -------------------------------------------------------

    def revoke_all_issued(self) -> None:
        """Invalida todos os tokens já emitidos (simula expiração no servidor).

        Determinístico, ao contrário de ``force_401``: qualquer requisição com um
        token antigo recebe 401, e só um token novo (obtido por novo login) passa.
        """
        self.revoked.update(self.issued_tokens)

    def paths(self, method: str | None = None) -> list[str]:
        return [
            c["path"] for c in self.calls if method is None or c["method"] == method
        ]

    def _bearer(self, request: httpx.Request) -> str | None:
        auth = request.headers.get("authorization") or ""
        return auth[7:].strip() if auth.lower().startswith("bearer ") else None

    @staticmethod
    def wire_path(request: httpx.Request) -> str:
        """Path como ele chega ao servidor, ainda percent-encoded.

        ``request.url.path`` já vem decodificado, o que faria ``%2F`` parecer um
        separador e mascararia justamente o que a codificação de segmento
        previne. Um servidor HTTP real roteia sobre estes bytes.
        """
        return request.url.raw_path.split(b"?", 1)[0].decode("ascii", "replace")

    def _record(self, request: httpx.Request) -> None:
        self.calls.append(
            {
                "method": request.method,
                "path": self.wire_path(request),
                "query": dict(request.url.params),
                "accept": request.headers.get("accept"),
                "content_type": request.headers.get("content-type"),
                "token": self._bearer(request),
                "body": request.content.decode() if request.content else None,
            }
        )

    # --- handler ----------------------------------------------------------

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self._record(request)
        path = self.wire_path(request)
        method = request.method
        accept = request.headers.get("accept") or "*/*"

        if path == "/api/v2/login" and method == "POST":
            return await self._login(request)

        token = self._bearer(request)
        if not token:
            return httpx.Response(401, json={"error": "missing bearer token"})
        if token in self.revoked:
            return httpx.Response(401, json={"error": "token revoked"})
        if self.force_401 > 0:
            self.force_401 -= 1
            return httpx.Response(401, json={"error": "token expired"})

        if path == "/api/v2/logout" and method == "GET":
            if not is_metadata_token(token):
                return httpx.Response(403, json={"error": "wrong scope"})
            self.logouts += 1
            self.revoked.add(token)
            return httpx.Response(200, text="ok")

        if path == "/api/v2/products":
            return self._products(request, token, accept, method)

        if path == "/api/v2/product/multipleProducts" and method == "POST":
            return self._multiple_products(request, token, accept)

        m = re.fullmatch(r"/api/v2/product/([^/]+)(?:/([^/]+))?", path)
        if m and method == "GET":
            return self._product(token, accept, m.group(1), m.group(2))

        m = re.fullmatch(r"/api/v2/publisher/([^/]+)", path)
        if m and method == "GET":
            if not is_metadata_token(token):
                return httpx.Response(403, json={"error": "wrong scope"})
            if m.group(1) != PUBLISHER_ID:
                return httpx.Response(404, json={"error": "publisher not found"})
            return httpx.Response(
                200,
                json={
                    "mvbId": PUBLISHER_ID,
                    "name": "Editora Contexto",
                    "cnpj": "00.000.000/0001-00",
                    "isbnPrefixes": ["978-85-7244"],
                },
            )

        m = re.fullmatch(r"/api/v2/index/([^/]+)/(.+)", path)
        if m and method == "GET":
            if not is_metadata_token(token):
                return httpx.Response(403, json={"error": "wrong scope"})
            return httpx.Response(
                200,
                json=[{"value": "Machado de Assis", "count": 12}],
            )

        m = re.fullmatch(r"/api/v[12]/cover/([^/]+)(?:/(s|m|l))?", path)
        if m and method == "GET":
            if token != COVER_TOKEN:
                return httpx.Response(403, json={"error": "cover token required"})
            if accept == "image/jpeg":
                return httpx.Response(406, text="Not Acceptable")
            if accept == "image/*":
                return httpx.Response(403, text="Forbidden")
            if m.group(1) != PRODUCT_ISBN:
                return httpx.Response(404, json={"error": "cover not found"})
            size = m.group(2)
            if size == "s":
                return httpx.Response(200, content=_jpeg(90, 135))
            if size == "m":
                return httpx.Response(200, content=_jpeg(200, 300))
            if size == "l":
                return httpx.Response(200, content=_jpeg(399, 599))
            return httpx.Response(200, content=JPEG_BYTES)

        m = re.fullmatch(r"/api/v[12]/asset/mmo/file/([^/]+)", path)
        if m and method == "GET":
            if token != MMO_TOKEN:
                return httpx.Response(403, json={"error": "mmo token required"})
            data = MMO_FILES.get(m.group(1))
            if data is None:
                return httpx.Response(404, json={"error": "asset not found"})
            return httpx.Response(200, content=data)

        m = re.fullmatch(r"/api/v2/asset/mmo/([^/]+)", path)
        if m and method == "GET":
            if token != MMO_TOKEN:
                return httpx.Response(403, json={"error": "mmo token required"})
            return httpx.Response(200, json=MMO_ASSETS)

        return httpx.Response(404, json={"error": "unknown endpoint", "path": path})

    # --- endpoints --------------------------------------------------------

    async def _login(self, request: httpx.Request) -> httpx.Response:
        import asyncio

        body = json.loads(request.content or b"{}")
        if self.login_delay:
            await asyncio.sleep(self.login_delay)
        if body.get("username") != LOGIN_USERNAME or body.get("password") != LOGIN_PASSWORD:
            return httpx.Response(401, json={"error": "bad credentials"})
        self.logins += 1
        # Cada login devolve um token NOVO, como a API real — é o que permite
        # distinguir "token velho" de "token recém-renovado".
        token = f"{METADATA_TOKEN_PREFIX}{self.logins}"
        self.issued_tokens.append(token)
        # A produção devolve o token como texto cru, sem content-type JSON.
        return httpx.Response(200, text=token, headers={"content-type": "text/plain"})

    def _page(self, items: list[dict], request: httpx.Request) -> dict:
        size = int(request.url.params.get("size", 50))
        page = int(request.url.params.get("page", 1))
        return {
            "content": items,
            "totalElements": 137,
            "totalPages": 3,
            "number": page - 1,  # resposta estilo Spring: base 0
            "size": size,
        }

    def _products(
        self, request: httpx.Request, token: str, accept: str, method: str
    ) -> httpx.Response:
        if not is_metadata_token(token):
            return httpx.Response(403, json={"error": "wrong scope"})
        if accept not in ("application/json", "application/json-short"):
            return httpx.Response(406, text="Not Acceptable")
        if method == "GET":
            search = request.url.params.get("search", "")
            items = [FLAT_NOISE_TITLE, FLAT_NOISE_DESC, FLAT_MAIN]
            if "naoexiste" in search.lower():
                items = []
            return httpx.Response(200, json=self._page(items, request))
        if method == "POST":
            body = json.loads(request.content or b"{}")
            if not isinstance(body.get("content"), list):
                return httpx.Response(400, json={"error": "expected {'content': [...]}"})
            wanted = {str(e.get("isbn", "")) for e in body["content"] if isinstance(e, dict)}
            items = [p for p in (FLAT_MAIN, FLAT_NOISE_TITLE) if p["isbn"] in wanted]
            return httpx.Response(200, json=self._page(items, request))
        return httpx.Response(405, json={"error": "method not allowed"})

    def _multiple_products(
        self, request: httpx.Request, token: str, accept: str
    ) -> httpx.Response:
        if not is_metadata_token(token):
            return httpx.Response(403, json={"error": "wrong scope"})
        # A collection oficial anota: "only in json format (no json-short or
        # ONIX response available)".
        if accept != "application/json":
            return httpx.Response(406, text="Not Acceptable: only application/json")
        body = json.loads(request.content or b"{}")
        if not isinstance(body.get("ids"), list):
            return httpx.Response(400, json={"error": "expected {'ids': [...]}"})
        by_id = {p["id"]: p for p in (FLAT_MAIN, FLAT_NOISE_TITLE, FLAT_NOISE_DESC)}
        items = [by_id[i] for i in body["ids"] if i in by_id]
        return httpx.Response(
            200, json={"content": items, "totalElements": len(items)}
        )

    def _product(
        self, token: str, accept: str, ident: str, id_type: str | None
    ) -> httpx.Response:
        if not is_metadata_token(token):
            return httpx.Response(403, json={"error": "wrong scope"})
        if id_type is not None and id_type not in _ID_TYPES:
            return httpx.Response(404, json={"error": f"unknown id type {id_type}"})
        known = {PRODUCT_UUID, PRODUCT_ISBN}
        if ident not in known:
            return httpx.Response(404, json={"error": "product not found"})
        if accept in ("application/onix30-short", "application/onix30-ref"):
            return httpx.Response(
                200, text=ONIX_XML, headers={"content-type": "application/xml"}
            )
        if accept not in ("application/json", "application/json-short"):
            return httpx.Response(406, text="Not Acceptable")
        return httpx.Response(200, json=DETAIL_ONIX)
