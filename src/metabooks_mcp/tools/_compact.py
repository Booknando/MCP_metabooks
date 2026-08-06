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
Os campos foram conferidos contra respostas REAIS da API (2026-07), que expõe três
formas distintas — busca/lista "long", `json-short` (mesmos nomes planos) e detalhe
"long" estilo ONIX aninhado. A extração é **tolerante**: cada campo é buscado por
uma lista de chaves candidatas (inclusive aninhadas) ou por um extrator dedicado
(`_extract_*`) quando exige lógica (chave-irmã, array, código→texto). Se a extração
ficar pobre demais, uma rede de segurança (`_shrink`) devolve o registro cru
**reduzido** (strings truncadas, listas limitadas) — nunca vazio. As listas de
candidatas e os mapas código→texto ficam concentrados logo abaixo.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# --- Chaves candidatas (conferidas contra respostas reais da API) --------------
# Ordem = prioridade. A busca é case-insensitive e também procura em sub-objetos
# comuns (ver _deep_get). A API expõe TRÊS formas distintas, todas cobertas aqui:
#   1) busca/lista "long" e json-short — campos planos: id, isbn, title, subTitle,
#      publisher, publicationDate, productFormId, productType, priceBrl, author,
#      state, availabilityStatePublisher, language.
#   2) detalhe "long" (/product/{id}) — estilo ONIX aninhado: titles[].title,
#      identifiers[].idValue, contributors[].firstName/lastName, prices[].priceAmount,
#      form.productForm, extent.mainContentPageCount, languages[].languageCode,
#      publishers[].publisherName, productAvailability, active.
# Campos que exigem lógica (código→texto, chave-irmã, array) têm extrator próprio
# abaixo (_extract_*); estes CANDIDATES cobrem só os campos de passagem direta.
CANDIDATES = {
    "uuid": ["id", "productId", "uuid", "productUuid"],
    "titulo": ["title", "titleText", "mainTitle", "distinctiveTitle"],
    "subtitulo": ["subTitle", "subtitle"],
    "editora": ["publisher", "publisherName", "imprintName", "imprint"],
    "data_publicacao": [
        "publicationDate", "publishingDate", "publishedDate", "pubDate",
    ],
}

# Listas de candidatos usadas pelos extratores dedicados.
ISBN_FLAT_CANDS = ["isbn13", "isbn", "gtin13"]
ISBN_FALLBACK_CANDS = ["gtin", "ean", "identifier"]
LANG_CANDS = ["language", "languageCode", "originalLanguage"]
FORM_CODE_CANDS = ["productFormId", "productForm", "productFormText", "productFormDetail", "format"]
PAGES_CANDS = ["mainContentPageCount", "numberOfPagesMain", "numberOfPages", "pageCount", "pages"]

# Mapas código→texto PT. Só entram códigos VERIFICÁVEIS (ISO 639, listas ONIX
# 5/17/150 e o campo 'state' da própria API). Códigos numéricos de disponibilidade
# (availabilityStatePublisher/productAvailability) NÃO são mapeados: seu significado
# não é confiável aqui (ex.: um título 'archived' vem com código '40'), então
# preferimos o campo 'state'/'active' e nunca inventamos um rótulo.
LANG_MAP = {
    "por": "Português", "eng": "Inglês", "spa": "Espanhol", "esp": "Espanhol",
    "fre": "Francês", "fra": "Francês", "ger": "Alemão", "deu": "Alemão",
    "ita": "Italiano", "lat": "Latim", "jpn": "Japonês", "mul": "Multilíngue",
}
PRODUCT_TYPE_MAP = {
    "ebook": "E-book", "pbook": "Livro impresso", "audiobook": "Audiolivro",
}
PRODUCT_FORM_MAP = {  # ONIX lista 150 (subconjunto comum)
    "BC": "Livro (brochura)", "BB": "Livro (capa dura)", "BA": "Livro",
    "DG": "E-book", "EA": "Digital (download)", "ED": "Digital (online)",
    "AC": "Audiolivro (CD)", "AJ": "Audiolivro (download)",
}
STATE_MAP = {
    "active": "ativo", "archived": "arquivado", "inactive": "inativo",
    "deleted": "removido", "new": "novo",
}
CONTRIB_ROLE_MAP = {  # ONIX lista 17 (subconjunto comum)
    "A01": "Autor", "A08": "Fotógrafo", "A12": "Ilustrador", "A15": "Prefácio",
    "A24": "Introdução", "B01": "Editor/organizador", "B06": "Tradutor",
    "B25": "Arranjo", "E07": "Narrador",
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


def _get_ci(obj: Any, key: str) -> Any:
    """Valor de uma chave (case-insensitive) só no nível atual do dict."""
    if isinstance(obj, dict):
        for k in obj:
            if k.lower() == key.lower():
                return obj[k]
    return None


def _extract_isbn(p: dict) -> str | None:
    """ISBN-13/GTIN-13, tolerante às três formas da API.

    Planos (busca/json-short): isbn/isbn13/gtin13. Detalhe ONIX:
    identifiers[].idValue filtrado por productIdentifierType (15=ISBN-13,
    03=GTIN-13, 02=ISBN-10) — sem esse filtro, _deep_get pegaria qualquer idValue.
    """
    flat = _deep_get(p, ISBN_FLAT_CANDS)
    if flat and str(flat).strip():
        return str(flat).strip()
    for key in ("identifiers", "productIdentifiers"):
        arr = _get_ci(p, key)
        if isinstance(arr, list):
            by_type: dict[str, str] = {}
            for it in arr:
                if isinstance(it, dict):
                    t = str(_get_ci(it, "productIdentifierType")
                            or _get_ci(it, "idType") or "").strip()
                    val = _get_ci(it, "idValue") or _get_ci(it, "value")
                    if t and val:
                        by_type.setdefault(t, str(val).strip())
            for t in ("15", "03", "02"):
                if by_type.get(t):
                    return by_type[t]
    fallback = _deep_get(p, ISBN_FALLBACK_CANDS)
    return str(fallback).strip() if fallback and str(fallback).strip() else None


def _extract_authors(p: dict) -> list[str] | None:
    """Extrai autores/contribuidores como 'Nome (papel)' de forma tolerante.

    Cobre o campo plano `author` (string), `contributors[].fullName` (busca) e
    `contributors[].firstName/lastName` + `contributorRole` (detalhe ONIX).
    Traduz o papel via CONTRIB_ROLE_MAP quando reconhecido.
    """
    for key in ("contributors", "contributor", "authors", "author", "creators"):
        arr = _get_ci(p, key)
        if arr is None:
            continue
        if isinstance(arr, str):
            return [arr] if arr.strip() else None
        if isinstance(arr, dict):
            arr = [arr]
        if isinstance(arr, list):
            out: list[str] = []
            for c in arr:
                if isinstance(c, str):
                    if c.strip():
                        out.append(c.strip())
                    continue
                if not isinstance(c, dict):
                    continue
                name = _deep_get(
                    c, ["fullName", "name", "personName", "displayName",
                        "corporateName", "groupName"],
                )
                if not name:
                    fn = _get_ci(c, "firstName")
                    ln = _get_ci(c, "lastName")
                    parts = [str(x).strip() for x in (fn, ln) if x and str(x).strip()]
                    if parts:
                        name = " ".join(parts)
                if not name:
                    name = _deep_get(c, ["nameInverted", "keyNames"])
                role_raw = (
                    _get_ci(c, "roleText") or _get_ci(c, "contributorRoleText")
                    or _get_ci(c, "contributorRole") or _get_ci(c, "role")
                    or _get_ci(c, "type")
                )
                role = None
                if role_raw:
                    role = CONTRIB_ROLE_MAP.get(
                        str(role_raw).strip().upper(), str(role_raw)
                    )
                if name:
                    out.append(f"{name} ({role})" if role else str(name))
            if out:
                return out
    return None


def _extract_price(p: dict) -> str | None:
    """Preço legível 'valor moeda' das três formas da API.

    Busca/json-short usa o campo plano `priceBrl` (moeda BRL implícita); o detalhe
    ONIX usa prices[].priceAmount + currencyCode.
    """
    brl = _deep_get(p, ["priceBrl"])
    if brl is not None and str(brl).strip():
        try:
            return f"{float(brl):.2f} BRL"
        except (TypeError, ValueError):
            pass
    amount = _deep_get(p, ["priceAmount", "priceValue"])
    currency = _deep_get(p, ["currencyCode", "currency"])
    if amount is None:
        return None
    try:
        amount = f"{float(amount):.2f}"
    except (TypeError, ValueError):
        amount = str(amount)
    return f"{amount} {currency}".strip() if currency else amount


def _extract_format(p: dict) -> str | None:
    """Formato legível: prefere productType (ebook/pbook), depois código ONIX 150."""
    pt = _deep_get(p, ["productType"])
    if pt and str(pt).strip().lower() in PRODUCT_TYPE_MAP:
        return PRODUCT_TYPE_MAP[str(pt).strip().lower()]
    code = _deep_get(p, FORM_CODE_CANDS)
    if code:
        return PRODUCT_FORM_MAP.get(str(code).strip().upper(), str(code))
    return str(pt) if pt else None


def _extract_availability(p: dict) -> str | None:
    """Disponibilidade CONFIÁVEL: usa 'state'/'active', nunca o código numérico.

    availabilityStatePublisher/productAvailability são códigos cujo significado
    não é confiável aqui, então não viram texto (ficam no detalhe reduzido).
    """
    st = _deep_get(p, ["state"])
    if st and str(st).strip():
        return STATE_MAP.get(str(st).strip().lower(), str(st).strip())
    act = _get_ci(p, "active")
    if isinstance(act, bool):
        return "ativo" if act else "inativo"
    txt = _deep_get(p, ["productAvailabilityText", "availabilityText"])
    return str(txt).strip() if txt and str(txt).strip() else None


def _extract_language(p: dict) -> str | None:
    code = _deep_get(p, LANG_CANDS)
    if not code:
        return None
    return LANG_MAP.get(str(code).strip().lower()[:3], str(code).strip())


def _extract_pages(p: dict) -> Any:
    return _deep_get(p, PAGES_CANDS)


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

    def put(campo: str, val: Any) -> None:
        if val is not None and str(val).strip():
            out[campo] = val

    # Ordem deliberada de leitura (identificação → bibliográfico → comercial).
    put("uuid", _deep_get(p, CANDIDATES["uuid"]))
    put("isbn", _extract_isbn(p))
    put("titulo", _deep_get(p, CANDIDATES["titulo"]))
    put("subtitulo", _deep_get(p, CANDIDATES["subtitulo"]))
    autores = _extract_authors(p)
    if autores:
        out["autores"] = autores
    put("editora", _deep_get(p, CANDIDATES["editora"]))
    put("data_publicacao", _deep_get(p, CANDIDATES["data_publicacao"]))
    put("formato", _extract_format(p))
    put("paginas", _extract_pages(p))
    put("idioma", _extract_language(p))
    put("preco", _extract_price(p))
    put("disponibilidade", _extract_availability(p))

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
                # A API é paginada no estilo Spring: o parâmetro `page` é base 1
                # (ver collection Postman) e o campo `number` da resposta é base 0.
                # Reportar o número cru faria 'pagina: 0' para a página 1 pedida.
                env[label] = int(v) + 1 if label == "pagina" else v
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
    """Como compact_list, mas marca correspondência de título e orienta.

    - ``titulo_exato``: o título é IGUAL ao termo (sem acento/caixa/espaço extra).
    - ``titulo_contem``: o termo aparece no título, mas o título é mais longo
      (ex.: "Análise de Dom Casmurro para o Enem" para o termo "Dom Casmurro").
      Marcar isso como exato — o que a versão anterior fazia — promovia ruído ao
      topo e destruía justamente a desambiguação que este módulo existe para dar.
    - Se ``prioritize_exact`` (sem ordenação explícita), sobe os exatos e, depois,
      os que contêm o termo.
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
            exato = bool(titulo) and bool(nt) and titulo == nt
            contem = bool(titulo) and bool(nt) and not exato and (
                titulo.startswith(nt + " ") or f" {nt} " in f" {titulo} "
                or titulo.endswith(" " + nt)
            )
            c["titulo_exato"] = exato
            c["titulo_contem"] = contem
            if exato:
                exatos += 1
        if prioritize_exact:
            resultados.sort(
                key=lambda c: (
                    not c.get("titulo_exato", False),
                    not c.get("titulo_contem", False),
                )
            )

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
