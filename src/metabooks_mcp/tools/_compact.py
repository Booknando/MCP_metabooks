"""Projeção compacta de respostas da API Metabooks para reduzir alucinação.

Motivação
---------
Modelos pequenos (ex.: Haiku) erram quando o JSON é grande. Caso clássico: ao
buscar "O Andar do Bêbado", a API traz também livros cuja *sinopse* contém essas
palavras; com o JSON "long" (sinopses inteiras), os livros errados parecem
relevantes e o modelo escolhe o errado.

Este módulo transforma a resposta da busca numa lista enxuta só com campos de
**identificação** (sem sinopse), com **chaves em português** (que servem de
rótulos amigáveis — atende BL-03), marca **correspondência exata de título** e
sempre expõe o **total** de resultados (evita truncamento silencioso — PS-03).

Robustez
--------
Como o schema exato da API não está documentado no repositório, a extração é
**tolerante**: cada campo é buscado por uma lista de chaves candidatas (inclusive
aninhadas, à moda ONIX). Se a extração ficar pobre demais, uma rede de segurança
(`_shrink`) devolve o registro cru **reduzido** (strings truncadas, listas
limitadas) — nunca vazio. As listas de chaves candidatas ficam concentradas em
CANDIDATES_* logo abaixo, para ajuste rápido quando houver uma amostra real.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# --- Chaves candidatas (AJUSTAR/CONFIRMAR contra amostra real da API) ----------
# Ordem = prioridade. A busca é case-insensitive e também procura em sub-objetos
# comuns (ver _deep_get). ONIX-like usa arrays aninhados, tratados caso a caso.
CANDIDATES = {
    "uuid": ["id", "productId", "uuid", "productUuid"],
    "isbn": ["isbn13", "isbn", "gtin13", "gtin", "ean", "identifier"],
    "titulo": ["title", "titleText", "mainTitle", "distinctiveTitle"],
    "subtitulo": ["subtitle", "subTitle"],
    "editora": ["publisherName", "publisher", "imprintName", "imprint"],
    "data_publicacao": [
        "publicationDate", "publishingDate", "publishedDate", "pubDate",
    ],
    "formato": [
        "productFormText", "productForm", "productFormDetail", "format",
        "editionFormat",
    ],
    "disponibilidade": [
        "productAvailabilityText", "productAvailability", "availabilityText",
        "availability", "availabilityStatus", "availabilityCode",
    ],
    "idioma": ["language", "languageCode", "originalLanguage"],
    "paginas": ["numberOfPages", "pageCount", "pages", "extentValue"],
}

# Blocos de texto longo (sinopse/marketing) — nunca entram na busca compacta e
# são truncados no detalhe.
CANDIDATES_DESC = [
    "mainDescription", "description", "descriptionText", "text", "textContent",
    "blurb", "annotation", "shortDescription", "longDescription", "sinopse",
]

# Chaves de envelope de paginação (respostas de lista).
LIST_KEYS = ["content", "products", "items", "results", "data"]
TOTAL_KEYS = ["totalElements", "totalCount", "total", "numberOfElements", "count"]
PAGE_KEYS = ["number", "page", "pageNumber"]
SIZE_KEYS = ["size", "pageSize"]
TOTAL_PAGES_KEYS = ["totalPages", "pageCount"]

MAX_STR = 300          # truncamento de strings no detalhe / rede de segurança
MAX_DESC = 400         # truncamento da descrição no detalhe compacto
MAX_ITEMS = 15         # limite de itens de array na rede de segurança
MIN_CORE_FIELDS = 1    # se a projeção achar menos que isto, aciona a rede de segurança


# --- Utilidades ----------------------------------------------------------------

def _norm(s: Any) -> str:
    """Normaliza para comparação: sem acento, minúsculo, espaços colapsados."""
    if not isinstance(s, str):
        s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _truncate(s: str, limit: int) -> str:
    s = s.strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _deep_get(obj: Any, candidates: list[str], _depth: int = 0) -> Any:
    """Primeiro valor escalar/simples achado para uma das chaves candidatas.

    Procura no dict atual (case-insensitive) e, recursivamente, em sub-dicts e
    no 1º elemento de sub-listas (padrão ONIX aninhado). Prioriza chaves mais
    rasas. Ignora valores vazios.
    """
    if _depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        lower = {k.lower(): k for k in obj.keys()}
        # 1) chave direta neste nível (respeita a ordem de prioridade)
        for cand in candidates:
            real = lower.get(cand.lower())
            if real is not None:
                val = obj[real]
                if isinstance(val, (str, int, float, bool)) and str(val).strip():
                    return val
                if isinstance(val, (dict, list)):
                    nested = _deep_get(val, candidates, _depth + 1)
                    if nested is not None:
                        return nested
        # 2) desce nos sub-objetos
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found = _deep_get(v, candidates, _depth + 1)
                if found is not None:
                    return found
    elif isinstance(obj, list):
        for item in obj[:5]:
            found = _deep_get(item, candidates, _depth + 1)
            if found is not None:
                return found
    return None


def _extract_authors(p: dict) -> list[str] | None:
    """Extrai autores/contribuidores como 'Nome (papel)' de forma tolerante."""
    for key in ("contributors", "contributor", "authors", "author", "creators"):
        arr = None
        for k in p.keys():
            if k.lower() == key.lower():
                arr = p[k]
                break
        if arr is None:
            continue
        if isinstance(arr, str):
            return [arr]
        if isinstance(arr, dict):
            arr = [arr]
        if isinstance(arr, list):
            out: list[str] = []
            for c in arr:
                if isinstance(c, str):
                    out.append(c)
                    continue
                if not isinstance(c, dict):
                    continue
                name = _deep_get(
                    c,
                    ["name", "personName", "displayName", "nameInverted",
                     "keyNames", "fullName", "corporateName"],
                )
                role = _deep_get(
                    c, ["roleText", "contributorRoleText", "role",
                        "contributorRole"]
                )
                if name:
                    out.append(f"{name} ({role})" if role else str(name))
            if out:
                return out
    return None


def _extract_price(p: dict) -> str | None:
    """Extrai um preço legível 'valor moeda' de forma tolerante."""
    amount = _deep_get(p, ["priceAmount", "amount", "price", "priceValue"])
    currency = _deep_get(p, ["currencyCode", "currency"])
    if amount is None:
        return None
    try:
        amount = f"{float(amount):.2f}"
    except (TypeError, ValueError):
        amount = str(amount)
    return f"{amount} {currency}".strip() if currency else amount


def _shrink(obj: Any, max_str: int = MAX_STR, max_items: int = MAX_ITEMS,
            _depth: int = 0) -> Any:
    """Rede de segurança: copia o objeto truncando strings e limitando listas."""
    if _depth > 6:
        return "…"
    if isinstance(obj, str):
        return _truncate(obj, max_str)
    if isinstance(obj, dict):
        return {k: _shrink(v, max_str, max_items, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        out = [_shrink(v, max_str, max_items, _depth + 1) for v in obj[:max_items]]
        if len(obj) > max_items:
            out.append(f"… (+{len(obj) - max_items} itens omitidos)")
        return out
    return obj


# --- Projeção de um produto ----------------------------------------------------

def compact_product(p: dict) -> dict:
    """Projeta um produto para um dict enxuto de identificação (sem sinopse).

    Se poucos campos forem reconhecidos (schema diferente do esperado), anexa
    ``_dados_brutos_reduzidos`` com o registro cru truncado, para nunca perder a
    informação.
    """
    if not isinstance(p, dict):
        return {"_dados_brutos_reduzidos": _shrink(p)}

    out: dict[str, Any] = {}
    for campo, cands in CANDIDATES.items():
        val = _deep_get(p, cands)
        if val is not None and str(val).strip():
            out[campo] = val

    autores = _extract_authors(p)
    if autores:
        out["autores"] = autores

    preco = _extract_price(p)
    if preco:
        out["preco"] = preco

    # Núcleo mínimo para considerar a projeção bem-sucedida.
    core = sum(1 for k in ("titulo", "isbn", "uuid") if k in out)
    if core < MIN_CORE_FIELDS:
        out["_dados_brutos_reduzidos"] = _shrink(p)

    return out


def compact_detail(p: dict) -> dict:
    """Detalhe compacto: identificação amigável + descrição truncada + cru reduzido.

    Mais rico que a busca (é a chamada de detalhe), mas com textos longos
    truncados e o restante do registro limitado em tamanho — em vez de despejar
    todos os blocos ONIX crus de uma vez.
    """
    if not isinstance(p, dict):
        return {"_dados_brutos_reduzidos": _shrink(p)}
    resumo = compact_product(p)
    desc = _deep_get(p, CANDIDATES_DESC)
    if desc and isinstance(desc, str):
        resumo["descricao"] = _truncate(desc, MAX_DESC)
    return {
        "resumo": resumo,
        "detalhe_reduzido": _shrink(p),
    }


# --- Projeção de listas --------------------------------------------------------

def _find_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in LIST_KEYS:
            for real in data.keys():
                if real.lower() == k.lower() and isinstance(data[real], list):
                    return data[real]
    return []


def _envelope(data: Any, mostrando: int) -> dict:
    env: dict[str, Any] = {}
    if isinstance(data, dict):
        total = _deep_get(data, TOTAL_KEYS)
        env["total"] = total if isinstance(total, (int, float)) else mostrando
        for label, keys in (("pagina", PAGE_KEYS), ("tamanho", SIZE_KEYS),
                            ("total_paginas", TOTAL_PAGES_KEYS)):
            v = _deep_get(data, keys)
            if isinstance(v, (int, float)):
                env[label] = v
    else:
        env["total"] = mostrando
    env["mostrando"] = mostrando
    return env


def compact_list(data: Any) -> dict:
    """Projeta uma resposta de lista em envelope + resultados compactos."""
    items = _find_list(data)
    resultados = [compact_product(it) for it in items if isinstance(it, dict)]
    out = _envelope(data, len(resultados))
    out["resultados"] = resultados
    return out


def compact_search(data: Any, termo: str | None = None,
                   prioritize_exact: bool = True) -> dict:
    """Como compact_list, mas marca correspondência exata de título e orienta.

    - Marca ``titulo_exato`` por item (termo bate com o título, sem acento/caixa).
    - Se ``prioritize_exact`` (sem ordenação explícita), sobe os títulos exatos.
    - Inclui ``aviso`` quando há ambiguidade (0 ou >1 exatos entre vários
      resultados) — orienta a IA a pedir confirmação em vez de chutar (TC-08/09).
    - Inclui ``aviso_paginacao`` quando a página não é o conjunto completo (PS-03).
    """
    out = compact_list(data)
    resultados: list[dict] = out["resultados"]

    exatos = 0
    if termo:
        nt = _norm(termo)
        for c in resultados:
            titulo = _norm(c.get("titulo", ""))
            c["titulo_exato"] = bool(titulo) and (
                titulo == nt or titulo.startswith(nt + " ") or f" {nt} " in f" {titulo} "
            )
            if c.get("titulo_exato"):
                exatos += 1
        if prioritize_exact and exatos:
            resultados.sort(key=lambda c: not c.get("titulo_exato", False))

    total = out.get("total", len(resultados))
    if termo and len(resultados) > 1:
        if exatos == 0:
            out["aviso"] = (
                f"Nenhum título corresponde exatamente a '{termo}'. Confirme com o "
                f"usuário qual dos {total} resultados é o desejado antes de prosseguir."
            )
        elif exatos > 1:
            out["aviso"] = (
                f"{exatos} títulos correspondem exatamente a '{termo}'. Peça "
                f"confirmação (ISBN/edição) antes de prosseguir."
            )
    if isinstance(total, (int, float)) and out.get("mostrando", 0) < total:
        out["aviso_paginacao"] = (
            f"Mostrando {out['mostrando']} de {total} resultados. Use page/size "
            f"para ver mais; não trate esta página como a lista completa."
        )
    return out
