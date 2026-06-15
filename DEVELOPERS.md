# Metabooks MCP Server — Guia do Desenvolvedor

Informações técnicas para quem vai modificar ou contribuir com o projeto.

## Estrutura do projeto

```
metabooks-mcp-server/
├── src/
│   ├── index.ts            # Entrada: transporte stdio/HTTP, healthcheck, auth
│   ├── constants.ts        # URLs, limites, tabelas de referência (mídia, productType, tax)
│   ├── types.ts            # Tipos das respostas da API
│   ├── schemas/index.ts    # Schemas Zod de entrada
│   ├── services/
│   │   ├── client.ts       # Cliente HTTP, seleção de token, tratamento de erro
│   │   ├── credentials.ts  # Credenciais do ambiente (e por requisição no modo HTTP)
│   │   └── format.ts       # Formatação markdown/JSON, paginação, truncamento
│   └── tools/index.ts      # As 8 ferramentas de leitura
├── dist/
│   └── index.cjs           # Bundle pré-compilado (commitar após npm run bundle)
├── .env.example            # Referência de variáveis de ambiente
├── DEVELOPERS.md           # Este arquivo
└── README.md               # Guia de instalação para usuários finais
```

## Pré-requisitos de desenvolvimento

- Node.js 18+
- npm

## Setup do ambiente de desenvolvimento

```bash
git clone <url-do-repo> C:\Metabooks-mcp
cd C:\Metabooks-mcp
npm install
```

## Scripts disponíveis

| Comando | O que faz |
|---|---|
| `npm run dev` | Inicia o servidor em modo desenvolvimento com hot-reload (`tsx watch`) |
| `npm run build` | Compila TypeScript → `dist/` (checagem de tipos, sem bundle) |
| `npm run bundle` | Gera bundle único `dist/index.cjs` via esbuild (para distribuição) |
| `npm start` | Executa `dist/index.cjs` |
| `npm run clean` | Remove a pasta `dist/` |

## Como regenerar o bundle após alterar o código

O arquivo `dist/index.cjs` é o que os usuários finais executam. Ele precisa ser regenerado e commitado sempre que `src/` mudar:

```bash
npm run bundle
git add dist/index.cjs
git commit -m "Atualiza bundle"
git push
```

O bundle é gerado com [esbuild](https://esbuild.github.io) em formato CommonJS, incluindo todas as dependências de runtime. O arquivo resultante tem ~2 MB e é autocontido — não requer `npm install` para execução.

## Modo desenvolvimento local

Para testar com o Claude Desktop em modo desenvolvimento (sem rebuild do bundle):

1. Execute `npm run dev` — isso inicia o servidor via `tsx` com hot-reload
2. No `claude_desktop_config.json`, aponte para o `tsx` em vez do bundle:

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "npx",
      "args": ["tsx", "C:\\Metabooks-mcp\\src\\index.ts"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_USERNAME": "seu_usuario",
        "METABOOKS_PASSWORD": "sua_senha"
      }
    }
  }
}
```

## Testando com o MCP Inspector

Para inspecionar as ferramentas sem o Claude Desktop:

```bash
npx @modelcontextprotocol/inspector node dist/index.cjs
```

No Inspector, defina as variáveis `TRANSPORT=stdio` e suas credenciais Metabooks antes de conectar.

## Modo HTTP (multi-tenant)

Além do modo `stdio` (para Claude Desktop), o servidor suporta HTTP para deployments em nuvem com múltiplos usuários. Nesse modo, as credenciais são passadas por request via headers:

| Header | Variável equivalente |
|---|---|
| `X-Metabooks-Username` | `METABOOKS_USERNAME` |
| `X-Metabooks-Password` | `METABOOKS_PASSWORD` |
| `X-Metabooks-Metadata-Token` | `METABOOKS_METADATA_TOKEN` |
| `X-Metabooks-Cover-Token` | `METABOOKS_COVER_TOKEN` |
| `X-Metabooks-Mmo-Token` | `METABOOKS_MMO_TOKEN` |
| `X-Metabooks-Base-Url` | `METABOOKS_BASE_URL` |

Para subir em modo HTTP:

```bash
TRANSPORT=http node dist/index.cjs
```

O servidor sobe na porta `3000` com dois endpoints:
- `POST /mcp` — endpoint MCP
- `GET /health` — healthcheck

Para proteger o endpoint com autenticação de gateway, defina `MCP_AUTH_TOKEN`.

## Docker

O projeto inclui um `Dockerfile` multi-stage para deployment em contêineres:

```bash
docker build -t metabooks-mcp .
docker run -p 3000:3000 \
  -e TRANSPORT=http \
  -e METABOOKS_USERNAME=usuario \
  -e METABOOKS_PASSWORD=senha \
  metabooks-mcp
```

## Variáveis de ambiente completas

| Variável | Descrição |
|---|---|
| `TRANSPORT` | `stdio` (Claude Desktop) ou `http` (deployment) |
| `METABOOKS_USERNAME` | Usuário Metabooks (modo login) |
| `METABOOKS_PASSWORD` | Senha Metabooks (modo login) |
| `METABOOKS_METADATA_TOKEN` | Token estático de metadados (alternativa ao login) |
| `METABOOKS_COVER_TOKEN` | Token de capas (opcional) |
| `METABOOKS_MMO_TOKEN` | Token de mídia/MMO (opcional) |
| `METABOOKS_BASE_URL` | URL base da API (padrão: produção) |
| `MCP_AUTH_TOKEN` | Token de gateway para modo HTTP (opcional) |
| `REQUIRE_TENANT_CREDENTIALS` | `true` para exigir credenciais por request em modo HTTP |

## Tecnologias

- [TypeScript](https://www.typescriptlang.org/) + Node.js 18+
- [@modelcontextprotocol/sdk](https://github.com/modelcontextprotocol/typescript-sdk) — SDK oficial MCP
- [axios](https://axios-http.com/) — cliente HTTP
- [express](https://expressjs.com/) — servidor HTTP (modo multi-tenant)
- [zod](https://zod.dev/) — validação de schemas
- [esbuild](https://esbuild.github.io/) — bundler para distribuição
