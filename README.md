# Metabooks MCP Server

Servidor [MCP](https://modelcontextprotocol.io) **somente leitura** para a API REST v2 da [Metabooks](https://www.metabooks.com) (MVB). Permite que o Claude consulte metadados bibliográficos, capas, arquivos de mídia (MMO) e dados de editoras do catálogo Metabooks/VLB.

> **Roda no seu próprio computador.** O servidor é executado localmente pelo Claude Desktop (via `stdio`) usando as **suas** credenciais Metabooks. As credenciais ficam apenas na sua máquina, dentro da configuração do Claude Desktop — **nunca** trafegam para a internet nem para terceiros. Não há login na nuvem, não há servidor exposto.

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

## Autenticação na Metabooks

Você se autentica de **uma** destas formas (escolha a que a MVB liberou para você):

- **Usuário e senha** (produção): o servidor faz `POST /login` e renova o token automaticamente. Use `METABOOKS_USERNAME` + `METABOOKS_PASSWORD`.
- **Token estático de metadados** (staging/rc): use `METABOOKS_METADATA_TOKEN`.

Opcionalmente, para **capas** e **mídia/MMO** (seção 5.5.5 da spec — login/metadados **não** acessa esses recursos):

- `METABOOKS_COVER_TOKEN` — capas.
- `METABOOKS_MMO_TOKEN` — arquivos de mídia (sumário, amostras, foto do autor...).

As outras 6 ferramentas funcionam só com login OU token de metadados.

## Pré-requisitos

1. **Node.js 18 ou superior** (recomendado 20+). Baixe em [nodejs.org](https://nodejs.org).
2. **Claude Desktop** instalado ([claude.ai/download](https://claude.ai/download)).
3. Suas **credenciais Metabooks** (usuário/senha **ou** token de metadados).

## Instalação

Baixe este projeto (clone ou ZIP) e, na pasta dele, rode:

```bash
npm install
npm run build
```

Isso gera a pasta `dist/` com o servidor compilado (`dist/index.js`). Anote o **caminho completo** dessa pasta — você vai usá-lo na configuração do Claude Desktop. Exemplos:

- Windows: `C:\Users\voce\MCP_metabooks\dist\index.js`
- macOS: `/Users/voce/MCP_metabooks/dist/index.js`

## Configurar no Claude Desktop

O Claude Desktop é quem **inicia** o servidor automaticamente, passando as suas credenciais por variáveis de ambiente. Basta editar um arquivo de configuração.

### 1. Abra o arquivo de configuração

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

> Atalho: no Claude Desktop, vá em **Settings → Developer → Edit Config**. Se o arquivo não existir, crie-o.

### 2. Adicione o servidor

**Opção A — usuário e senha (produção):**

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "node",
      "args": ["C:\\Users\\voce\\MCP_metabooks\\dist\\index.js"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_USERNAME": "seu_usuario",
        "METABOOKS_PASSWORD": "sua_senha"
      }
    }
  }
}
```

**Opção B — token de metadados (staging/rc):**

```json
{
  "mcpServers": {
    "metabooks": {
      "command": "node",
      "args": ["C:\\Users\\voce\\MCP_metabooks\\dist\\index.js"],
      "env": {
        "TRANSPORT": "stdio",
        "METABOOKS_METADATA_TOKEN": "seu_token_de_metadados"
      }
    }
  }
}
```

Pontos importantes:

- **`TRANSPORT` deve ser `stdio`** — é o que faz o servidor funcionar dentro do Claude Desktop.
- No **Windows**, as barras invertidas do caminho precisam ser duplicadas no JSON (`\\`). No **macOS/Linux**, use barras normais (`/Users/voce/MCP_metabooks/dist/index.js`).
- Para usar **capas/mídia**, acrescente no bloco `env`:
  ```json
  "METABOOKS_COVER_TOKEN": "seu_token_de_cover",
  "METABOOKS_MMO_TOKEN": "seu_token_de_mmo"
  ```
- Para apontar para outro ambiente (staging/rc), acrescente `"METABOOKS_BASE_URL": "https://staging.kubernetes.br.metabooks.com/api/v2"`. O padrão é produção.
- Se o Claude Desktop não encontrar o `node`, troque `"command": "node"` pelo caminho completo do executável (ex.: `"C:\\Program Files\\nodejs\\node.exe"`).

### 3. Reinicie o Claude Desktop

Feche **totalmente** e abra de novo. O servidor `metabooks` deve aparecer na lista de ferramentas (ícone de conector/martelo). A partir daí é só pedir, por exemplo: *"busque na Metabooks os e-books com ST=Linux"*.

## Variáveis de ambiente

Definidas no bloco `env` da configuração do Claude Desktop (acima). Referência em `.env.example`.

| Variável | Quando usar | Descrição |
|---|---|---|
| `TRANSPORT` | Sempre | Use `stdio` para o Claude Desktop |
| `METABOOKS_USERNAME` | Login (produção) | Usuário Metabooks |
| `METABOOKS_PASSWORD` | Login (produção) | Senha Metabooks |
| `METABOOKS_METADATA_TOKEN` | Alternativa ao login | Token de metadados (staging/rc) |
| `METABOOKS_COVER_TOKEN` | Para capas | Token de capas (opcional) |
| `METABOOKS_MMO_TOKEN` | Para mídias | Token de mídia/MMO (opcional) |
| `METABOOKS_BASE_URL` | Não (opcional) | URL base. Padrão: produção |

> É preciso configurar **login OU token de metadados**. Os tokens de cover/mmo são opcionais.

### URLs de ambiente

- Produção (padrão): `https://api.metabooks.com/api/v2`
- Staging: `https://staging.kubernetes.br.metabooks.com/api/v2`
- RC: `https://rc.kubernetes.br.metabooks.com/api/v2`

## Atualizando

Se você mudar de credencial, edite o bloco `env` no `claude_desktop_config.json` e reinicie o Claude Desktop. Se baixar uma nova versão do código, rode `npm install && npm run build` de novo na pasta do projeto.

## Testando fora do Claude (opcional)

Para inspecionar as ferramentas sem o Claude Desktop, use o MCP Inspector:

```bash
npx @modelcontextprotocol/inspector node dist/index.js
```

No Inspector, defina as variáveis de ambiente (`TRANSPORT=stdio`, `METABOOKS_USERNAME`/`METABOOKS_PASSWORD` ou `METABOOKS_METADATA_TOKEN`) e conecte.

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
│   ├── index.ts            # Entrada: transporte stdio/HTTP, healthcheck, auth
│   ├── constants.ts        # URLs, limites, tabelas de referência (mídia, productType, tax)
│   ├── types.ts            # Tipos das respostas da API
│   ├── schemas/index.ts    # Schemas Zod de entrada
│   ├── services/
│   │   ├── client.ts       # Cliente HTTP, seleção de token, tratamento de erro
│   │   └── credentials.ts  # Credenciais do ambiente (e por requisição no modo HTTP)
│   │   └── format.ts       # Formatação markdown/JSON, paginação, truncamento
│   └── tools/index.ts      # As 8 ferramentas de leitura
├── .env.example
└── README.md
```

## Segurança

- As credenciais ficam **só na sua máquina**, no `claude_desktop_config.json`. Não compartilhe esse arquivo.
- Os tokens da Metabooks nunca saem do seu computador: o servidor roda localmente e fala direto com a API da Metabooks.

## Licença

Uso interno Booknando. A API Metabooks pertence à MVB.
