"""Tools de Capas — endpoint: /cover"""

import os
from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP, Context, Image

from ._files import resolve_target


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_view_cover(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9788530951382)"],
        size: Annotated[
            Literal["s", "m", "l"],
            "Tamanho para exibição: s (90px larg.), m (200px) ou l (599px alt.). "
            "Não há 'original' aqui — para a capa em tamanho original use "
            "metabooks_download_cover (salva em arquivo).",
        ] = "m",
    ):
        """Exibe a capa de um título por ISBN/GTIN inline na conversa (JPEG).

        O tamanho é gerenciado pelo MCP para garantir a renderização: só tamanhos
        leves (s/m/l, no máximo ~44 KB) são servidos inline. A capa 'original'
        (~1.3 MB) não renderiza inline em alguns clientes (ex.: Claude Desktop) —
        para ela, use metabooks_download_cover, que salva o arquivo em disco.

        Autentica com o token dedicado de capa, busca o binário e devolve a
        imagem sem expor o token em nenhuma URL. Exige METABOOKS_COVER_TOKEN.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        if not client.cover_token:
            return {
                "error": (
                    "Token de capa não configurado. Defina METABOOKS_COVER_TOKEN. "
                    "Capas exigem token dedicado — login/metadados não as acessa (seção 5.5.5)."
                )
            }
        try:
            # Accept DEVE ser "*/*": o servidor de capas da Metabooks responde
            # 406 Not Acceptable a "Accept: image/jpeg" (e 403 a "image/*").
            # Só "*/*" retorna o binário (image/jpeg) — vale para v1 e v2.
            data = await client.get_bytes(
                f"cover/{id}/{size}", scope="cover", accept="*/*"
            )
        except Exception as exc:  # noqa: BLE001 — devolve erro amigável ao cliente MCP
            return {
                "error": (
                    f"Não foi possível obter a capa de {id} (tamanho {size}): {exc}. "
                    "Verifique o ISBN/GTIN, se a capa existe e se o token de capa tem permissão."
                )
            }
        return Image(data=data, format="jpeg")

    @mcp.tool()
    async def metabooks_download_cover(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9788530951382)"],
        size: Annotated[
            Literal["s", "m", "l", "original"],
            "Tamanho a baixar. 'original' = pixels originais (web-optimized), "
            "padrão para download; s/m/l reduzem proporcionalmente.",
        ] = "original",
        dest: Annotated[
            str | None,
            "Destino opcional: caminho de um arquivo .jpg OU uma pasta (o nome do "
            "arquivo é gerado). Se omitido, salva em ~/Downloads (ou pasta temporária).",
        ] = None,
    ) -> dict:
        """Baixa a capa e salva em arquivo no disco; retorna o caminho.

        Use para obter a capa em tamanho 'original' (~1.3 MB), que não renderiza
        inline. Para apenas visualizar na conversa, use metabooks_view_cover.
        Exige METABOOKS_COVER_TOKEN.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        if not client.cover_token:
            return {
                "error": (
                    "Token de capa não configurado. Defina METABOOKS_COVER_TOKEN. "
                    "Capas exigem token dedicado — login/metadados não as acessa (seção 5.5.5)."
                )
            }
        size_segment = f"/{size}" if size != "original" else ""
        try:
            data = await client.get_bytes(
                f"cover/{id}{size_segment}", scope="cover", accept="*/*"
            )
        except Exception as exc:  # noqa: BLE001 — devolve erro amigável ao cliente MCP
            return {
                "error": (
                    f"Não foi possível baixar a capa de {id} (tamanho {size}): {exc}. "
                    "Verifique o ISBN/GTIN, se a capa existe e se o token de capa tem permissão."
                )
            }
        if not data.startswith(b"\xff\xd8\xff"):
            return {
                "error": (
                    f"O servidor não devolveu um JPEG válido para {id} (tamanho {size}). "
                    f"Primeiros bytes: {data[:16]!r}."
                )
            }

        filename = f"capa_{id}_{size}.jpg"
        target = resolve_target(dest, filename)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            return {"error": f"Falha ao salvar a capa em {target}: {exc}"}

        return {
            "id": id,
            "size": size,
            "path": target,
            "bytes": len(data),
            "message": f"Capa salva em {target} ({len(data) / 1024:.1f} KB).",
        }

    @mcp.tool()
    async def metabooks_get_cover_url(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9783411046508)"],
        size: Annotated[
            Literal["s", "m", "l", "original"],
            "Tamanho: s (90px larg.), m (200px), l (599px alt.) ou original",
        ] = "m",
    ) -> dict:
        """Monta a URL canônica de capa de um título por ISBN/GTIN.

        ATENÇÃO: esta URL NÃO abre no navegador nem deve ser colada como imagem
        markdown — ela exige o token de capa no cabeçalho Authorization, então
        abri-la diretamente devolve 401/403. Use-a só em pipelines autenticados.
        Para EXIBIR a capa na conversa, use metabooks_view_cover (devolve a imagem
        inline, sem URL). Exige METABOOKS_COVER_TOKEN para o acesso efetivo.
        """
        client = ctx.request_context.lifespan_context["metabooks"]
        size_segment = f"/{size}" if size != "original" else ""
        cover_url = f"{client.base_url}/cover/{id}{size_segment}"
        return {
            "id": id,
            "size": size,
            "cover_url": cover_url,
            "auth": "Requer token de capa (Authorization: Bearer ... ou ?access_token=...).",
            "accept": "Envie 'Accept: */*' — o servidor responde 406 a 'image/jpeg' e 403 a 'image/*'.",
            "browser_openable": False,
            "display_hint": "Para exibir na conversa use metabooks_view_cover (NÃO cole esta URL como imagem).",
        }
