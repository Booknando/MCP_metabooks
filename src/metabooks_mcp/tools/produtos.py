"""Tools de Produtos — endpoints: /products, /product"""

import re
from typing import Annotated, Literal, Optional
from mcp.server.fastmcp import FastMCP, Context
from pydantic import Field

from ..client import path_segment
from ._compact import compact_search, compact_list, compact_detail

# Limites da API confirmados na collection Postman oficial: `page` é base 1 e
# `size` vai até 250 (os exemplos usam size=250 como máximo).
MAX_PAGE_SIZE = 250
# Itens por requisição em lote. A busca por ISBN aceita uma lista maior que uma
# página (o resultado vem paginado); multipleProducts trabalha por UUID.
MAX_BULK_ISBNS = 500
MAX_BULK_IDS = 250


def _title_term(search: str) -> Optional[str]:
    """Termo de título para casar ``titulo_exato``/``aviso``.

    Sem operadores (``=``): devolve a expressão inteira (quick search).
    Com operadores: devolve o valor de ``TI=`` (preferido) ou, na falta, ``ST=``,
    para que buscas precisas ainda marquem título exato e emitam aviso de
    ambiguidade. Qualificadores que não são título (``AU=``, ``VL=``, ``IS=``…)
    resultam em None — não faz sentido casar título com eles.
    """
    if "=" not in search:
        return search.strip() or None
    for qual in ("TI", "ST"):
        m = re.search(
            rf'\b{qual}\s*=\s*("[^"]*"|\'[^\']*\'|[^()]+?)'
            r'(?=\s+(?:and|or|not)\b|\s*\)|$)',
            search, re.IGNORECASE,
        )
        if m:
            val = m.group(1).strip().strip('"').strip("'").strip()
            if val:
                return val
    return None

# Descrição reutilizada do parâmetro view nas buscas (listas).
_VIEW_LIST = (
    "compact (padrão): lista enxuta só com campos de identificação (título, "
    "subtítulo, autor, ISBN, editora, data, formato, páginas, idioma, preço, "
    "disponibilidade), SEM sinopse, com total de resultados e marca de título "
    "exato — ideal para identificar/desambiguar sem alucinar. full: JSON "
    "completo e cru da API (todos os metadados)."
)

# Sintaxe de busca — fonte única (espelhada no README e nas instructions do
# server). Qualificadores CONFIRMADOS ao vivo na API (2026-07); WG foi omitido
# por não ter sido confirmado. Um qualificador desconhecido retorna 0 resultados,
# então listar só os que funcionam evita buscas vazias/enganosas.
SEARCH_SYNTAX = (
    "Termo livre (quick search em título, autor, editora, ISBN) OU expressão "
    "booleana com qualificadores 'CHAVE=valor'. Qualificadores: "
    "ST=texto geral, TI=título, AU=autor, VL=editora, IS=ISBN/identificador, "
    "SW=palavra-chave/assunto, PF=formato (código ONIX lista 150), "
    "PR=faixa de preço, EJ=ano de publicação, AD=data de alteração, "
    "RH=ID de série. "
    "Operadores: and, or, not e parênteses. Curinga: * (ex.: PF=E*). "
    "Faixa com ^ (ex.: PR=40^80, AD=20240101^20241231). "
    "Exemplos: 'ST=Linux and PF=E*', 'VL=Nova Fronteira and PF=not EA', "
    "'TI=Dom Casmurro', 'EJ=2020'."
)


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_search_products(
        ctx: Context,
        search: Annotated[str, SEARCH_SYNTAX],
        page: Annotated[int, Field(ge=1, description="Página, base 1 (padrão 1)")] = 1,
        size: Annotated[
            int,
            Field(ge=1, le=MAX_PAGE_SIZE,
                  description=f"Itens por página, 1-{MAX_PAGE_SIZE} (padrão 50)"),
        ] = 50,
        sort: Annotated[Optional[Literal[
            "identifier", "author", "titleAndSubtitle", "publisher",
            "publicationDate", "productAvailability", "price",
            "creationDate", "lastModificationDate", "productType", "active",
        ]], "Coluna de ordenação (opcional)"] = None,
        direction: Annotated[Optional[Literal["asc", "desc"]], "Direção de ordenação"] = None,
        active: Annotated[Optional[bool], "true=ativos, false=inativos; omitido=ambos"] = None,
        view: Annotated[Literal["compact", "full"], _VIEW_LIST] = "compact",
    ) -> dict:
        """Busca títulos no catálogo Metabooks por palavra-chave ou expressão booleana.

        Por padrão devolve uma lista COMPACTA (só identificação, sem sinopse) para
        o modelo escolher o título certo sem se perder no volume; use o UUID/ISBN
        retornado em metabooks_get_product para o detalhe. Passe view='full' só se
        precisar de todos os metadados de cada resultado.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        params: dict = {"page": page, "size": size, "search": search}
        if sort:
            params["sort"] = sort
        if direction:
            params["direction"] = direction
        if active is not None:
            params["active"] = str(active).lower()
        if view == "full":
            return await client.get("products", params=params)
        data = await client.get(
            "products", params=params, accept="application/json-short"
        )
        # Casa título exato em quick search e também no valor de TI=/ST=.
        termo = _title_term(search)
        return compact_search(data, termo=termo, prioritize_exact=(sort is None))

    @mcp.tool()
    async def metabooks_batch_search_isbns(
        ctx: Context,
        isbns: Annotated[
            list[str],
            Field(min_length=1, max_length=MAX_BULK_ISBNS,
                  description=f"Lista de ISBNs/GTINs (até {MAX_BULK_ISBNS}). "
                              "Curingas '*' aceitos (ex: '9783923*')"),
        ],
        search: Annotated[Optional[str], "Filtro booleano adicional opcional — mesma "
                              "sintaxe de metabooks_search_products (ex.: 'AD=20240101^20241231', 'PF=E*')"] = None,
        page: Annotated[int, Field(ge=1, description="Página, base 1 (padrão 1)")] = 1,
        size: Annotated[
            int,
            Field(ge=1, le=MAX_PAGE_SIZE,
                  description=f"Itens por página, 1-{MAX_PAGE_SIZE} (padrão 50)"),
        ] = 50,
        view: Annotated[Literal["compact", "full"], _VIEW_LIST] = "compact",
    ) -> dict:
        """Consulta vários ISBNs/GTINs de uma vez (até 500). ISBNs sem correspondência não aparecem."""
        client = ctx.request_context.lifespan_context["metabooks"]
        params: dict = {"page": page, "size": size}
        if search:
            params["search"] = search
        body = {"content": [{"isbn": isbn} for isbn in isbns]}
        if view == "full":
            return await client.post("products", json=body, params=params)
        data = await client.post(
            "products", json=body, params=params, accept="application/json-short"
        )
        return compact_list(data)

    @mcp.tool()
    async def metabooks_get_product(
        ctx: Context,
        id: Annotated[str, "UUID (32 chars), ISBN-13, EAN ou GTIN (não hifenizado)"],
        id_type: Annotated[
            Literal["uuid", "isbn13", "ean", "gtin"],
            "Tipo do ID: uuid (padrão), isbn13, ean ou gtin",
        ] = "uuid",
        format: Annotated[
            Literal["json", "onix30-short", "onix30-ref"],
            "Formato: json (padrão, completo), onix30-short ou onix30-ref (XML ONIX 3.0)",
        ] = "json",
        view: Annotated[
            Literal["compact", "full"],
            "Só para format=json. compact (padrão): identificação amigável + "
            "descrição truncada + demais campos reduzidos (evita despejar todos "
            "os blocos ONIX). full: JSON completo e cru da API.",
        ] = "compact",
    ) -> dict | str:
        """Recupera os dados de um único título.

        Com format=json e view=compact (padrão), devolve um detalhe enxuto e
        legível; use view='full' para o JSON completo. Formatos ONIX 3.0 sempre
        voltam crus (XML), independentes de view.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        path = f"product/{path_segment(id)}"
        if id_type != "uuid":
            path += f"/{path_segment(id_type)}"
        if format.startswith("onix"):
            return await client.get(path, accept=f"application/{format}")
        data = await client.get(path)
        if view == "full":
            return data
        return compact_detail(data)

    @mcp.tool()
    async def metabooks_get_multiple_products(
        ctx: Context,
        ids: Annotated[
            list[str],
            Field(min_length=1, max_length=MAX_BULK_IDS,
                  description=f"Lista de UUIDs de produto (32 chars, até {MAX_BULK_IDS}). "
                              "Ordem preservada. NÃO aceita ISBN — use "
                              "metabooks_batch_search_isbns para ISBNs."),
        ],
        view: Annotated[Literal["compact", "full"], _VIEW_LIST] = "compact",
    ) -> dict:
        """Recupera os dados de vários produtos de uma vez a partir de UUIDs."""
        client = ctx.request_context.lifespan_context["metabooks"]
        # Este endpoint só responde em JSON longo — a collection oficial anota
        # "only in json format (no json-short or ONIX response available)". Pedir
        # json-short aqui arrisca 406/resposta inesperada; a redução fica só na
        # projeção local.
        data = await client.post("product/multipleProducts", json={"ids": ids})
        if view == "full":
            return data
        return compact_list(data)
