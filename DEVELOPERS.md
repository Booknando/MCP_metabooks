# Metabooks MCP Server — Guia do Desenvolvedor

Informações técnicas para quem vai modificar ou contribuir com o projeto.

## Estrutura do projeto

```
metabooks-mcp/
├── src/metabooks_mcp/
│   ├── server.py           # FastMCP: lifespan (login/logout), registro de módulos, entry point
│   ├── client.py           # MetabooksClient: HTTP, autenticação, cache de token, logout, get_bytes
│   └── tools/
│       ├── produtos.py     # search_products, batch_search_isbns, get_product, get_multiple_products
│       ├── capas.py        # view_cover (imagem inline), get_cover_url
│       ├── midia.py        # get_media_assets (MMO)
│       ├── indice.py       # index_search
│       └── editora.py      # get_publisher
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
| Mídia/MMO | GET | `/asset/mmo/{productId}` | `metabooks_get_media_assets` |

Notas de design:
- **Capas** são baixadas via `client.get_bytes` com o token de capa no cabeçalho `Authorization` e devolvidas como imagem — o token nunca é exposto numa URL (seção 5.5.5 / 5.10.1).
- **Logout** só é disparado para login status-based (usuário/senha); com token estático é no-op.
- Detalhe de produto suporta `json` (long), `onix30-short` e `onix30-ref`. ONIX 2.1 (legado) não é exposto.
- Listas (`/products`, `/product/multipleProducts`) são sempre `application/json` (long).

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

## Tecnologias

- [Python 3.12+](https://www.python.org/)
- [FastMCP](https://github.com/jlowin/fastmcp) — framework MCP de alto nível
- [httpx](https://www.python-httpx.org/) — cliente HTTP assíncrono
- [python-dotenv](https://github.com/theskumar/python-dotenv) — leitura de `.env`
- [hatchling](https://hatch.pypa.io/) — build system
