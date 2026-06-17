"""Tools de Capas — endpoint: /cover"""

from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP, Context, Image


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_view_cover(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9788530951382)"],
        size: Annotated[
            Literal["s", "m", "l", "original"],
            "Tamanho: s (90px larg.), m (200px), l (599px alt.) ou original. "
            "Menor = resposta mais rápida.",
        ] = "m",
    ):
        """Baixa e exibe a imagem de capa de um título por ISBN/GTIN (JPEG inline).

        Autentica com o token dedicado de capa, busca o binário e retorna a
        imagem para visualização direta na conversa — sem expor o token em
        nenhuma URL. Exige METABOOKS_COVER_TOKEN.
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
            # Accept DEVE ser "*/*": o servidor de capas da Metabooks responde
            # 406 Not Acceptable a "Accept: image/jpeg" (e 403 a "image/*").
            # Só "*/*" retorna o binário (image/jpeg) — vale para v1 e v2.
            data = await client.get_bytes(
                f"cover/{id}{size_segment}", scope="cover", accept="*/*"
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
    async def metabooks_get_cover_url(
        ctx: Context,
        id: Annotated[str, "ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9783411046508)"],
        size: Annotated[
            Literal["s", "m", "l", "original"],
            "Tamanho: s (90px larg.), m (200px), l (599px alt.) ou original",
        ] = "m",
    ) -> dict:
        """Monta a URL canônica de capa de um título por ISBN/GTIN.

        A URL retornada NÃO contém o token — o acesso continua exigindo o token
        de capa (cabeçalho Authorization Bearer ou parâmetro ?access_token=).
        Para ver a imagem direto na conversa, use metabooks_view_cover.
        Exige METABOOKS_COVER_TOKEN configurado para o acesso efetivo.
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
        }
