# Metabooks MCP Server — Guia do Desenvolvedor

Informações técnicas para quem vai modificar ou contribuir com o projeto.

## Estrutura do projeto

```
metabooks-mcp/
├── src/metabooks_mcp/
│   ├── server.py           # FastMCP: lifespan, registro de módulos, entry point
│   ├── client.py           # MetabooksClient: HTTP, autenticação, cache de token
│   └── tools/
│       ├── produtos.py     # search_products, batch_search_isbns, get_product, get_multiple_products
│       ├── capas.py        # get_cover_url
│       ├── midia.py        # get_media_assets (MMO)
│       ├── indice.py       # index_search
│       └── editora.py      # get_publisher
├── pyproject.toml          # Build system (hatchling), dependências, entry point
├── .env.example            # Referência de variáveis de ambiente
├── DEVELOPERS.md           # Este arquivo
└── README.md               # Guia de instalação para usuários finais
```

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
