"""Tools de Produtos — endpoints: /products, /product"""

from typing import Annotated, Literal, Optional
from mcp.server.fastmcp import FastMCP, Context

from ._compact import compact_search, compact_list, compact_detail

# Descrição reutilizada do parâmetro view nas buscas (listas).
_VIEW_LIST = (
    "compact (padrão): lista enxuta só com campos de identificação (título, "
    "autor, ISBN, editora, data, formato, disponibilidade), SEM sinopse, com "
    "total de resultados e marca de título exato — ideal para identificar/"
    "desambiguar sem alucinar. full: JSON completo da API (todos os metadados)."
)


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_search_products(
        ctx: Context,
        search: Annotated[str, "Termo ou expressão booleana Metabooks. "
                              "Sem prefixo: quick search (título, autor, editora, ISBN). "
                              "Com operadores: ST=termo, AU=autor, TI=título, VL=editora, "
                              "IS=isbn, PF=formato, EJ=ano, WG=grupo, RH=série, "
                              "AD=data_de^data_ate. Ex: 'ST=Linux and PF=E*', 'VL=Artmed'"],
        page: Annotated[int, "Página, base 1 (padrão 1)"] = 1,
        size: Annotated[int, "Itens por página, 1-250 (padrão 50)"] = 50,
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
        # Só faz sentido casar título exato em quick search (sem operadores '=').
        termo = search if "=" not in search else None
        return compact_search(data, termo=termo, prioritize_exact=(sort is None))

    @mcp.tool()
    async def metabooks_batch_search_isbns(
        ctx: Context,
        isbns: Annotated[list[str], "Lista de ISBNs/GTINs (até 500). Curingas '*' aceitos (ex: '9783923*')"],
        search: Annotated[Optional[str], "Filtro booleano adicional (opcional, ex: 'AD=20150319^20150320')"] = None,
        page: Annotated[int, "Página, base 1 (padrão 1)"] = 1,
        size: Annotated[int, "Itens por página, 1-250 (padrão 50)"] = 50,
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
        path = f"product/{id}"
        if id_type != "uuid":
            path += f"/{id_type}"
        if format.startswith("onix"):
            return await client.get(path, accept=f"application/{format}")
        data = await client.get(path)
        if view == "full":
            return data
        return compact_detail(data)

    @mcp.tool()
    async def metabooks_get_multiple_products(
        ctx: Context,
        ids: Annotated[list[str], "Lista de UUIDs de produto (32 chars, até 250). Ordem preservada."],
        view: Annotated[Literal["compact", "full"], _VIEW_LIST] = "compact",
    ) -> dict:
        """Recupera os dados de vários produtos de uma vez a partir de UUIDs."""
        client = ctx.request_context.lifespan_context["metabooks"]
        if view == "full":
            return await client.post("product/multipleProducts", json={"ids": ids})
        data = await client.post(
            "product/multipleProducts", json={"ids": ids},
            accept="application/json-short",
        )
        return compact_list(data)
