# Metabooks MCP Server — Guia do Desenvolvedor

Informações técnicas para quem vai modificar ou contribuir com o projeto.

## Estrutura do projeto

```
metabooks-mcp/
├── src/metabooks_mcp/
│   ├── server.py           # FastMCP: lifespan (login/logout), registro de módulos, entry point
│   ├── client.py           # MetabooksClient: HTTP, autenticação, cache de token, logout, get_bytes
│   ├── tools/
│   │   ├── produtos.py     # search_products, batch_search_isbns, get_product, get_multiple_products
│   │   ├── capas.py        # view_cover / download_cover / get_cover_url (+ recurso ui:// experimental)
│   │   ├── midia.py        # get_media_assets / view_media_asset / download_media_asset (MMO)
│   │   ├── indice.py       # index_search
│   │   └── editora.py      # get_publisher
│   └── ui/
│       └── cover_app.html  # App HTML (MCP Apps) p/ exibir a capa em destaque (experimental)
├── docs/
│   └── instalacao-mac.md   # Guia de instalação para macOS
├── pyproject.toml          # Build system (hatchling), dependências, entry point
├── .env.example            # Referência de variáveis de ambiente
├── DEVELOPERS.md           # Este arquivo
└── README.md               # Guia de instalação para usuários finais (Windows)
```

## Cobertura da API REST v2

Todos os endpoints da especificação (seção 6.1) estão implementados:

| Função | Método | Endpoint | Implementação |
|---|---|---|---|
| Login | POST | `/login` | `client._do_login` (token cru ou JSON) |
| Logout | GET | `/logout` | `client.logout` (no encerramento; libera slot) |
| Busca (quick/boolean) | GET | `/products` | `metabooks_search_products` |
| Busca em lote | POST | `/products` | `metabooks_batch_search_isbns` |
| Índice | GET | `/index/{field}/{term}` | `metabooks_index_search` |
| Produto | GET | `/product/{id}[/{type}]` | `metabooks_get_product` (json/onix30) |
| Múltiplos produtos | POST | `/product/multipleProducts` | `metabooks_get_multiple_products` |
| Editora | GET | `/publisher/{mvbid}` | `metabooks_get_publisher` |
| Capa (URL) | GET | `/cover/{id}[/{size}]` | `metabooks_get_cover_url` |
| Capa (imagem) | GET | `/cover/{id}[/{size}]` | `metabooks_view_cover` (JPEG inline) |
| Mídia/MMO (listar) | GET | `/asset/mmo/{productId}` | `metabooks_get_media_assets` (sem URL; expõe `asset_id`) |
| Mídia/MMO (imagem) | GET | `/asset/mmo/file/{id}` | `metabooks_view_media_asset` (JPEG inline, reduzido c/ Pillow) |
| Mídia/MMO (download) | GET | `/asset/mmo/file/{id}` | `metabooks_download_media_asset` (qualquer tipo, p/ disco) |

Notas de design:
- **Capas** são baixadas via `client.get_bytes` com o token de capa no cabeçalho `Authorization` e devolvidas como imagem — o token nunca é exposto numa URL (seção 5.5.5 / 5.10.1).
- **Mídias/MMO**: `get_media_assets` **não devolve a URL crua** (auth-gated, não abre no navegador) — expõe um `asset_id` estável. `view_media_asset` e `download_media_asset` resolvem o `asset_id` para a URL do listing e buscam o binário via `client.get_bytes_from_url` (guarda de host anti-SSRF). A capa frontal listada aponta para o endpoint `/cover` (token de capa); os demais arquivos usam o token de MMO — o scope é decidido pela URL. Imagens exibidas inline são reduzidas com Pillow (lado maior ≤ 1024 px) para garantir o render.
- **Logout** só é disparado para login status-based (usuário/senha); com token estático é no-op.
- Detalhe de produto suporta `json` (long), `onix30-short` e `onix30-ref`. ONIX 2.1 (legado) não é exposto.
- Listas (`/products`, `/product/multipleProducts`) são sempre `application/json` (long).

## Diagnóstico: o que é do cliente e o que é do MCP

- **A capa aparece dentro do cartão recolhido "Usou uma ferramenta".** É renderização do
  **cliente** (Claude Desktop/Cowork): imagens devolvidas por uma tool MCP (bloco `ImageContent`)
  são sempre mostradas dentro do cartão de resultado, recolhido por padrão. O modelo recebe a
  imagem como entrada mas não pode reemiti-la na própria bolha. **Não há API no MCP** para mudar
  esse posicionamento — só o host decide. Mitigação experimental: MCP Apps (abaixo).
- **"VM service not running. The service failed to start"** é falha da **VM do Cowork** (serviço
  de VM Windows embutido do Claude Desktop), **não** do MCP. O servidor roda como subprocesso
  stdio no host e nem toca nessa VM. Evidência: `cowork_vm_node.log` →
  `[VM:start] Startup failed`, enquanto `mcp-server-metabooks.log` mostra o MCP saudável
  (`isError:false`, login `200 OK`). Passos de mitigação ficam no README (FAQ).
- **`serverInfo.version` no handshake é a versão do SDK MCP, não a do projeto.** Como
  `FastMCP(...)` em `server.py` não recebe `version=`, o handshake reporta a versão do pacote
  `mcp` (ex.: `1.27.2`) — isso **não** indica build velho. Para saber o build real, veja a linha
  `Using MCP server command:` em `mcp-server-metabooks.log` (caminho do executável iniciado).

## Exibição da capa via MCP Apps (experimental)

Extensão `io.modelcontextprotocol/ui` (MCP Apps). Desligada por padrão; ligue com
`METABOOKS_ENABLE_UI_APP=1` no bloco `env`. Quando ligada (ver `tools/capas.py`):

- `metabooks_view_cover` ganha `_meta = {"ui": {"resourceUri": "ui://metabooks/cover"}}`.
- Registra-se o recurso `ui://metabooks/cover` (mimeType `text/html;profile=mcp-app`) servindo
  `src/metabooks_mcp/ui/cover_app.html`.
- `cover_app.html` implementa, sem dependências, a ponte postMessage (`ui/initialize` →
  `ui/notifications/initialized`; recebe `ui/notifications/tool-result` e renderiza o bloco de
  imagem em `<img>`).

O retorno `Image` permanece intacto e é o **fallback** universal: clientes sem MCP Apps seguem
mostrando a capa no cartão. **Resultado incerto** — o host ainda pode renderizar o app como
widget associado à ferramenta. Validar no Claude Desktop; se não melhorar a proeminência, basta
manter a flag desligada (ou remover a UI).

## Pré-requisitos de desenvolvimento

- Python 3.12+
- pip

## Setup do ambiente de desenvolvimento

```bash
git clone <url-do-repo> C:\Metabooks-mcp
cd C:\Metabooks-mcp
pip install -e .
```

A flag `-e` instala em modo editável: alterações em `src/` refletem imediatamente sem reinstalar.

## Como adicionar uma nova ferramenta

Cada módulo em `src/metabooks_mcp/tools/` segue o mesmo padrão:

```python
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP, Context

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def metabooks_minha_ferramenta(
        ctx: Context,
        parametro: Annotated[str, "Descrição do parâmetro"],
    ) -> dict:
        """Descrição da ferramenta (aparece no Claude)."""
        client = ctx.request_context.lifespan_context["metabooks"]
        return await client.get("endpoint/path")
```

Para devolver uma imagem (como em `capas.py`), retorne um `Image` do FastMCP:

```python
from mcp.server.fastmcp import Image
# ...
data = await client.get_bytes("cover/9788530951382/m", scope="cover", accept="image/jpeg")
return Image(data=data, format="jpeg")
```

Depois, registre o novo módulo em `server.py`:

```python
from .tools import produtos, capas, midia, indice, editora, novo_modulo
# ...
novo_modulo.register(mcp)
```

## Testando com o MCP Inspector

```bash
metabooks-mcp --help
npx @modelcontextprotocol/inspector metabooks-mcp
```

No Inspector, defina as variáveis de ambiente com suas credenciais antes de conectar.

## Testando com o Claude Desktop em desenvolvimento

No `claude_desktop_config.json`, aponte para o módulo Python diretamente:

```json
{
  "mcpServers": {
    "metabooks-dev": {
      "command": "python",
      "args": ["-m", "metabooks_mcp.server"],
      "env": {
        "METABOOKS_USERNAME": "seu_usuario",
        "METABOOKS_PASSWORD": "sua_senha"
      }
    }
  }
}
```

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `METABOOKS_USERNAME` | Usuário Metabooks (modo login, produção) |
| `METABOOKS_PASSWORD` | Senha Metabooks (modo login, produção) |
| `METABOOKS_METADATA_TOKEN` | Token estático de metadados (staging/rc, alternativa ao login) |
| `METABOOKS_COVER_TOKEN` | Token de capas (opcional, exige contrato com MVB) |
| `METABOOKS_MMO_TOKEN` | Token de mídia/MMO (opcional, exige contrato com MVB) |
| `METABOOKS_BASE_URL` | URL base da API (padrão: `https://api.metabooks.com/api/v2`) |
| `METABOOKS_ENABLE_UI_APP` | (Experimental) `1`/`true` liga o app HTML (MCP Apps) da capa via recurso `ui://` |

## Tecnologias

- [Python 3.12+](https://www.python.org/)
- [FastMCP](https://github.com/jlowin/fastmcp) — framework MCP de alto nível
- [httpx](https://www.python-httpx.org/) — cliente HTTP assíncrono
- [python-dotenv](https://github.com/theskumar/python-dotenv) — leitura de `.env`
- [Pillow](https://python-pillow.org/) — redução de imagens de mídia para exibição inline
- [hatchling](https://hatch.pypa.io/) — build system
