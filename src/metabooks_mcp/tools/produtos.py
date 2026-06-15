"""Tools de Produtos — endpoints: /products, /product"""

from typing import Annotated, Literal, Optional
from mcp.server.fastmcp import FastMCP, Context


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
    ) -> dict:
        """Busca títulos no catálogo Metabooks por palavra-chave ou expressão booleana."""
        client = ctx.request_context.lifespan_context["metabooks"]
        params: dict = {"page": page, "size": size, "search": search}
        if sort:
            params["sort"] = sort
        if direction:
            params["direction"] = direction
        if active is not None:
            params["active"] = str(active).lower()
        return await client.get("products", params=params)

    @mcp.tool()
    async def metabooks_batch_search_isbns(
        ctx: Context,
        isbns: Annotated[list[str], "Lista de ISBNs/GTINs (até 500). Curingas '*' aceitos (ex: '9783923*')"],
        search: Annotated[Optional[str], "Filtro booleano adicional (opcional, ex: 'AD=20150319^20150320')"] = None,
        page: Annotated[int, "Página, base 1 (padrão 1)"] = 1,
        size: Annotated[int, "Itens por página, 1-250 (padrão 50)"] = 50,
    ) -> dict:
        """Consulta vários ISBNs/GTINs de uma vez (até 500). ISBNs sem correspondência não aparecem."""
        client = ctx.request_context.lifespan_context["metabooks"]
        params: dict = {"page": page, "size": size}
        if search:
            params["search"] = search
        body = {"content": [{"isbn": isbn} for isbn in isbns]}
        return await client.post("products", json=body, params=params)

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
    ) -> dict | str:
        """Recupera os dados completos de um único título (todos os blocos de metadados)."""
        client = ctx.request_context.lifespan_context["metabooks"]
        path = f"product/{id}"
        if id_type != "uuid":
            path += f"/{id_type}"
        if format.startswith("onix"):
            return await client.get(path, accept=f"application/{format}")
        return await client.get(path)

    @mcp.tool()
    async def metabooks_get_multiple_products(
        ctx: Context,
        ids: Annotated[list[str], "Lista de UUIDs de produto (32 chars, até 250). Ordem preservada."],
    ) -> dict:
        """Recupera os dados completos de vários produtos de uma vez a partir de UUIDs."""
        client = ctx.request_context.lifespan_context["metabooks"]
        return await client.post("product/multipleProducts", json={"ids": ids})
