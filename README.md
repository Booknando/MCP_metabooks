# Metabooks MCP Server

Servidor [MCP](https://modelcontextprotocol.io) **somente leitura** para a API REST v2 da [Metabooks](https://www.metabooks.com) (MVB). Permite que o Claude consulte metadados bibliográficos, capas, arquivos de mídia (MMO) e dados de editoras do catálogo Metabooks/VLB.

Construído em TypeScript com transporte **Streamable HTTP** (stateless), pronto para rodar online em qualquer provedor (Render, Railway, Fly.io, VPS, Kubernetes, etc.).

> Este servidor implementa **apenas operações de leitura** (GET e POST de consulta). A API da Metabooks não suporta inserção de dados.

## Ferramentas disponíveis

| Ferramenta | Endpoint | O que faz | Token |
|---|---|---|---|
| `metabooks_search_products` | `GET /products` | Busca por palavra-chave ou sintaxe booleana (AU, TI, VL, IS, ST, PF, RH, datas...) | login/metadata |
| `metabooks_batch_search_isbns` | `POST /products` | Consulta até 500 ISBNs/GTINs de uma vez (aceita curingas `*`) | login/metadata |
| `metabooks_get_product` | `GET /product/<id>` | Detalhe completo por UUID/ISBN/EAN/GTIN, em JSON-long ou ONIX 3.0 | login/metadata |
| `metabooks_get_multiple_products` | `POST /product/multipleProducts` | Detalhe de vários UUIDs (JSON) | login/metadata |
| `metabooks_get_media_assets` | `GET /asset/mmo/<uuid>` | Lista URLs de capas, sumário, amostras, foto do autor, etc. | mmo |
| `metabooks_get_cover_url` | `GET /cover/<isbn>/<size>` | Monta a URL da capa por ISBN/GTIN (s/m/l/original) | cover |
| `metabooks_index_search` | `GET /index/<field>/<term>` | Autocomplete em autor, editora, título, palavra-chave, série, etc. | login/metadata |
| `metabooks_get_publisher` | `GET /publisher/<mvbid>` | Dados cadastrais da editora (nome, endereço, CNPJ, prefixos ISBN) | login/metadata |

## Modos de operação

Este servidor tem dois modos, controlados por `REQUIRE_TENANT_CREDENTIALS`:

### Multi-tenant (recomendado para a MVB com várias editoras)

`REQUIRE_TENANT_CREDENTIALS=true`. Uma única instância atende todas as editoras. **Cada editora configura, no seu conector MCP, headers HTTP com as próprias credenciais Metabooks.** O servidor usa as credenciais de cada requisição de forma isolada (via `AsyncLocalStorage`), com cache de token de login separado por credencial. Nada de credencial de editora fica gravado no servidor.

Headers enviados pelo conector de cada editora:

| Header | Para quê |
|---|---|
| `X-Metabooks-Username` + `X-Metabooks-Password` | Login (produção) |
| `X-Metabooks-Metadata-Token` | Token estático de metadados (staging/rc) |
| `X-Metabooks-Cover-Token` | Capas (opcional) |
| `X-Metabooks-Mmo-Token` | Mídia/MMO (opcional) |
| `X-Metabooks-Base-Url` | Sobrescreve a URL base (opcional) |

A editora envia **login OU token de metadados**. Os de cover/mmo são opcionais.

### Single-tenant (uma instância = um acesso fixo)

`REQUIRE_TENANT_CREDENTIALS` vazio/false. As credenciais vêm das variáveis de ambiente (`METABOOKS_USERNAME`/`METABOOKS_PASSWORD` ou `METABOOKS_METADATA_TOKEN`). Útil para testes ou para uma editora rodar a própria instância. Headers de requisição, se enviados, sobrescrevem o ambiente.

## Autenticação na Metabooks (resumo)

- **Metadados** (buscas, detalhe, índice, editora): login por usuário/senha (produção, `POST /login` com renovação automática de token) **ou** token estático de metadados (staging/rc).
- **Capas e mídia**: exigem tokens dedicados da MVB. Login/metadados **não** os acessa (seção 5.5.5 da spec). Opcionais — as outras 6 ferramentas funcionam sem eles.

## Variáveis de ambiente

Veja `.env.example`. As principais:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `REQUIRE_TENANT_CREDENTIALS` | Não | `true` ativa o modo multi-tenant (credenciais por header) |
| `METABOOKS_USERNAME` | Single-tenant | Usuário Metabooks (produção) |
| `METABOOKS_PASSWORD` | Para login | Senha Metabooks (produção) |
| `METABOOKS_METADATA_TOKEN` | Alternativa ao login | Token de metadados (staging/rc) |
| `METABOOKS_COVER_TOKEN` | Para capas | Token de capas (opcional) |
| `METABOOKS_MMO_TOKEN` | Para mídias | Token de mídia/MMO (opcional) |
| `METABOOKS_BASE_URL` | Não | URL base. Padrão: produção. Use staging/rc para testes |
| `PORT` | Não | Porta HTTP (padrão 3000) |
| `TRANSPORT` | Não | `http` (padrão) ou `stdio` |
| `MCP_AUTH_TOKEN` | Não (recomendado online) | Se definido, exige `Authorization: Bearer <token>` nas chamadas a `/mcp` |

> É preciso configurar **login OU token de metadados**. Os tokens de cover/mmo são opcionais.

### URL do ambiente de teste

O ambiente de teste varia conforme o deploy da semana:

- Staging: `https://staging.kubernetes.br.metabooks.com/api/v2`
- RC: `https://rc.kubernetes.br.metabooks.com/api/v2`
- Produção: `https://api.metabooks.com/api/v2`

## Rodando localmente

```bash
npm install
npm run build
cp .env.example .env   # preencha os tokens
# Carregue o .env e rode:
export $(grep -v '^#' .env | xargs) && npm start
```

O servidor sobe em `http://localhost:3000/mcp` (endpoint MCP) e `http://localhost:3000/health` (healthcheck).

Para uso local via stdio (ex.: Claude Desktop):

```bash
TRANSPORT=stdio METABOOKS_METADATA_TOKEN=... node dist/index.js
```

## Rodando online (Docker)

```bash
docker build -t metabooks-mcp-server .
docker run -p 3000:3000 \
  -e METABOOKS_USERNAME=seu_usuario \
  -e METABOOKS_PASSWORD=sua_senha \
  -e MCP_AUTH_TOKEN=um_segredo \
  metabooks-mcp-server
# (capas/mídia: acrescente -e METABOOKS_COVER_TOKEN=... -e METABOOKS_MMO_TOKEN=...)
```

### Deploy em PaaS (Render, Railway, Fly.io)

1. Suba o repositório no Git.
2. Crie um serviço web a partir do Dockerfile (ou Node 20 com build `npm run build` e start `npm start`).
3. Configure as variáveis de ambiente (tokens + `MCP_AUTH_TOKEN`).
4. O healthcheck é `GET /health`.
5. O endpoint MCP público será `https://seu-app/mcp`.

> **Segurança**: ao expor online, defina sempre `MCP_AUTH_TOKEN` para que apenas clientes com o segredo acessem `/mcp`. Os tokens da Metabooks nunca trafegam para o cliente — ficam só no servidor.

## Conectando no Claude (cada editora)

Cada editora adiciona um conector MCP customizado apontando para `https://seu-app/mcp` e configura, nos **headers** do conector:

- `Authorization: Bearer <MCP_AUTH_TOKEN>` (se o gateway estiver protegido)
- As próprias credenciais Metabooks, por exemplo:
  - `X-Metabooks-Username: usuario_da_editora`
  - `X-Metabooks-Password: senha_da_editora`
  - (e, se for usar capas/mídia, `X-Metabooks-Cover-Token` / `X-Metabooks-Mmo-Token`)

Assim, a mesma instância serve todas as editoras, cada uma com o próprio acesso ao catálogo. As credenciais de uma editora nunca são vistas por outra nem ficam gravadas no servidor.

## Testando o protocolo

```bash
# Listar ferramentas
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Buscar um título (modo multi-tenant: credenciais por header)
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Metabooks-Username: usuario" \
  -H "X-Metabooks-Password: senha" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"metabooks_search_products","arguments":{"search":"ST=Linux and PF=E*","size":10}}}'
```

Ou use o MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

## Sintaxe booleana da Metabooks (referência rápida)

Operadores combináveis com `and` / `or` / `not`, parênteses permitidos. **Não** faça URL-encoding — o servidor cuida disso.

| Chave | Campo | Exemplo |
|---|---|---|
| `ST=` | quick search | `ST=Linux` |
| `AU=` | autor | `AU="May, Karl"` |
| `TI=` | título | `TI=gymnastik` |
| `VL=` | editora | `VL=Artmed` |
| `IS=` | identificador | `IS=9783765732324` |
| `SW=` | palavra-chave | `SW=Glück` |
| `WG=` | grupo de produto | `WG=?250` |
| `PF=` | forma (ONIX 2.1) | `PF=E*` (digitais) |
| `PD=` | forma detalhe (ONIX 3.0) | `PD=E101` |
| `RH=` | série/hierarquia | `RH=RC712` |
| `AD=` | data de modificação | `AD=20190301^20190815` |
| `PR=` | preço | `PR=14^15` |

## Estrutura do projeto

```
metabooks-mcp-server/
├── src/
│   ├── index.ts            # Entrada: transportes HTTP/stdio, healthcheck, auth
│   ├── constants.ts        # URLs, limites, tabelas de referência (mídia, productType, tax)
│   ├── types.ts            # Tipos das respostas da API
│   ├── schemas/index.ts    # Schemas Zod de entrada
│   ├── services/
│   │   ├── client.ts       # Cliente HTTP, seleção de token, tratamento de erro
│   │   └── format.ts       # Formatação markdown/JSON, paginação, truncamento
│   └── tools/index.ts      # As 8 ferramentas de leitura
├── Dockerfile
├── .env.example
└── README.md
```

## Licença

Uso interno Booknando. A API Metabooks pertence à MVB.
