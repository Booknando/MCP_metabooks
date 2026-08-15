# Metabooks MCP Server — Guia do Desenvolvedor

Informações técnicas para quem vai modificar ou contribuir com o projeto.

## Estrutura do projeto

```
metabooks-mcp/
├── src/metabooks_mcp/
│   ├── server.py           # FastMCP: lifespan (login/logout), registro de módulos, entry point
│   ├── client.py           # MetabooksClient: HTTP, autenticação, lock de login, retry de 401, guardas de URL
│   ├── tools/
│   │   ├── produtos.py     # search_products, batch_search_isbns, get_product, get_multiple_products
│   │   ├── capas.py        # view_cover / download_cover / get_cover_url (+ recurso ui:// experimental)
│   │   ├── midia.py        # get_media_assets / view_media_asset / download_media_asset (MMO)
│   │   ├── indice.py       # index_search
│   │   ├── editora.py      # get_publisher
│   │   ├── _compact.py     # projeção compacta (anti-alucinação)
│   │   └── _files.py       # confinamento do destino de gravação dos downloads
│   └── ui/
│       └── cover_app.html  # App HTML (MCP Apps) p/ exibir a capa em destaque (experimental)
├── tests/
│   ├── fake_api.py         # API Metabooks falsa que aplica as regras da collection
│   ├── conftest.py         # fixtures: API falsa, cliente, sessão MCP em memória
│   ├── test_client.py      # autenticação, concorrência, retry de 401, guardas de URL
│   ├── test_tools.py       # as 12 tools via sessão MCP real
│   ├── test_compact.py     # projeção compacta, titulo_exato, envelope
│   ├── test_files.py       # confinamento de destino, sobrescrita, extensão
│   ├── test_api_contract.py# MCP × collection Postman oficial
│   ├── test_server.py      # build_server(): construção, versão no handshake, schema
│   ├── test_live.py        # as 12 tools contra a API REAL (só com METABOOKS_LIVE=1)
│   └── fixtures/           # Metabooks.postman_collection.json (spec executável da MVB)
├── scripts/
│   └── smoke_live.py       # rodada de validação da FORMA das respostas de produção
├── .github/workflows/ci.yml# Testes em 3 SOs × 2 versões + instalação limpa
├── docs/
│   └── instalacao-mac.md   # Guia de instalação para macOS
├── pyproject.toml          # Build system (hatchling), dependências, entry point
├── LICENSE                 # Licença proprietária de uso
├── .env.example            # Referência de variáveis de ambiente
├── DEVELOPERS.md           # Este arquivo
└── README.md               # Guia de instalação para usuários finais (Windows)
```

## Teto obrigatório na dependência do SDK

`pyproject.toml` fixa `mcp[cli]>=1.26.0,<2`. O **teto não é opcional**: o SDK 2.x
removeu `mcp.server.fastmcp` (a classe virou `mcp.server.mcpserver.MCPServer`), e
sem ele um `pip install` limpo resolve para 2.x e o servidor falha na importação
com `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` — o entry point
nem chega a subir. O job `resolucao-de-dependencias` do CI reproduz o caminho do
README (`pip install .` + construção do servidor) exatamente para pegar essa
regressão. Migrar para o SDK 2.x é uma tarefa separada, não uma consequência de
soltar o teto.

O teto sozinho não basta: **a assinatura do `FastMCP.__init__` também muda dentro
do 1.x**. Até a 2.6.0 o servidor era construído com `FastMCP(version=...)`, que
versões antigas do SDK engoliam via `**settings` e as atuais recusam — o
resultado era `TypeError: FastMCP.__init__() got an unexpected keyword argument
'version'` na instalação de quem baixava o ZIP, com a suíte e o CI verdes. Por
isso o job de instalação limpa roda em matriz nas **duas pontas** do teto
(`1.26.0` e a resolvida) e **constrói o servidor de verdade**, em vez de só
chamar `--help`. Ao mexer no construtor, confira as duas pontas.

## `build_server()` é o único construtor

`server.py` expõe `build_server() -> FastMCP`; `main()` só faz o argparse e chama
`build_server().run(...)`. Testes (`conftest.py`, `test_live.py`) e CI importam
essa função.

**Não remonte um `FastMCP` na mão em teste nenhum.** Foi exatamente isso que
escondeu o defeito acima: a suíte montava o seu próprio servidor (sem o
`version=`), então 142 testes passavam sobre um objeto que não era o objeto
distribuído. Toda prova de inicialização tem de partir de `build_server()`.

A versão do projeto é publicada em `mcp._mcp_server.version` logo após a
construção — o `FastMCP` não repassa versão ao servidor de baixo nível, e sem
isso o `initialize` devolveria a versão do pacote `mcp`.

### Descrições de parâmetro: sempre via `Field`

Use `Annotated[X, Field(description="...")]`, nunca `Annotated[X, "texto"]`. O
pydantic trata a string pura como metadado desconhecido e a **descarta** ao gerar
o JSON Schema: a descrição não chega ao modelo e nada quebra. Até a 2.6.0 apenas
4 dos 41 parâmetros chegavam documentados — inclusive a `SEARCH_SYNTAX`, que
sumia do parâmetro `search`. `test_server.py` tranca isso exigindo `description`
em todos os parâmetros de todas as tools.

### Ruído conhecido no stderr

Ao construir o servidor, o SDK emite um `IncompleteFieldDefinitionWarning` do
`pydantic_settings` sobre o campo `lifespan`. É interno do SDK (aparece até num
`FastMCP(name='x')` puro), vai para o log do Claude Desktop e não indica falha.

## Cobertura da API REST v2

Todos os endpoints da especificação (seção 6.1) estão implementados. Os que a
collection Postman oficial exemplifica são verificados automaticamente em
`tests/test_api_contract.py` — se a MVB publicar uma collection com um endpoint
novo, o teste falha em vez de a lacuna passar batida:

| Função | Método | Endpoint | Implementação |
|---|---|---|---|
| Login | POST | `/login` | `client._do_login` (token cru ou JSON) |
| Logout | GET | `/logout` | `client.logout` (no encerramento; libera slot) |
| Busca (quick/boolean) | GET | `/products` | `metabooks_search_products` |
| Busca em lote | POST | `/products` | `metabooks_batch_search_isbns` |
| Índice | GET | `/index/{field}/{term}` | `metabooks_index_search` |
| Produto | GET | `/product/{id}[/{type}]` | `metabooks_get_product` (json/onix30) |
| Múltiplos produtos | POST | `/product/multipleProducts` | `metabooks_get_multiple_products` (sempre `application/json`) |
| Editora | GET | `/publisher/{mvbid}` | `metabooks_get_publisher` |
| Capa (URL) | GET | `/cover/{id}[/{size}]` | `metabooks_get_cover_url` |
| Capa (imagem) | GET | `/cover/{id}[/{size}]` | `metabooks_view_cover` (JPEG inline) |
| Mídia/MMO (listar) | GET | `/asset/mmo/{productId}` | `metabooks_get_media_assets` (sem URL; expõe `asset_id`) |
| Mídia/MMO (imagem) | GET | `/asset/mmo/file/{id}` | `metabooks_view_media_asset` (JPEG inline, reduzido c/ Pillow) |
| Mídia/MMO (download) | GET | `/asset/mmo/file/{id}` | `metabooks_download_media_asset` (qualquer tipo, p/ disco) |

Notas de design:
- **Capas** são baixadas via `client.get_bytes` com o token de capa no cabeçalho `Authorization` e devolvidas como imagem — o token nunca é exposto numa URL (seção 5.5.5 / 5.10.1). `get_cover_url` **não** sugere `?access_token=`: token em querystring vaza para logs de servidor, proxies e histórico.
- **Mídias/MMO**: `get_media_assets` **não devolve a URL crua** (auth-gated, não abre no navegador) — expõe um `asset_id` estável. `view_media_asset` e `download_media_asset` resolvem o `asset_id` para a URL do listing e buscam o binário via `client.get_bytes_from_url` (guarda de host anti-SSRF). A capa frontal listada aponta para o endpoint `/cover` (token de capa); os demais arquivos usam o token de MMO — o scope é decidido pela URL. Imagens exibidas inline são reduzidas com Pillow (lado maior ≤ 1024 px) para garantir o render.
- **Login serializado**: `_login_lock` garante um único login para N chamadas simultâneas. Sem isso, cada login concorrente ocupava um slot de sessão paralela da MVB, só liberado após 60 min — o que se manifestava como "bloqueio temporário da API" depois de várias consultas em sequência.
- **Retry de 401 para todos os verbos**: `client._send` centraliza GET, POST e download binário, e renova o token uma vez em 401 (só no escopo de metadados obtido por login; token estático não tem o que renovar).
- **`multipleProducts` só aceita `application/json`** — a collection oficial anota "only in json format (no json-short or ONIX response available)". A redução vem apenas da projeção local.
- **Logout** só é disparado para login status-based (usuário/senha); com token estático é no-op.
- Detalhe de produto suporta `json` (long), `onix30-short` e `onix30-ref`. ONIX 2.1 (legado) não é exposto.
- Buscas e listas usam o formato compacto por padrão (ver seção abaixo).
- `page` é **base 1** na API (confirmado na collection) e o campo `number` da resposta é **base 0**; o envelope compacto normaliza para base 1 em `pagina`.
- `size` vai até **250**; os limites de lote (500 ISBNs, 250 UUIDs) e o intervalo de `page`/`size` são impostos via `pydantic.Field` no schema, de modo que o modelo recebe a restrição antes de gastar uma chamada.

## Segurança

Decisões que valem revisão antes de qualquer mudança nessas áreas:

- **Somente leitura.** Nenhuma tool escreve na Metabooks.
- **Segmentos de path codificados.** Todo valor vindo do modelo passa por `client.path_segment`, que faz `quote(..., safe="")` (barras viram `%2F`) e recusa segmentos `.`/`..`. Sem isso, um `term` como `../../publisher/BR0090012` fazia o httpx normalizar o path e alcançar outro endpoint com o token do operador. `client._build_url` é a rede de segurança: recusa segmentos de ponto e qualquer path que saia do prefixo da base.
- **Guarda de host.** `get_bytes_from_url` só busca URLs com o mesmo esquema, host, porta e prefixo `/api` da base — o `/api/v1` das URLs de arquivo do MMO passa, `http://` (token em texto claro), outra porta e outro host não.
- **Downloads confinados** (`tools/_files.py`). O `dest` é escolhido pelo MODELO e o contexto do modelo é alimentado por conteúdo da API que terceiros editam (título, sinopse). Por isso: gravação restrita às raízes de `METABOOKS_DOWNLOAD_DIR` (padrão `~/Downloads`), com resolução de symlinks do trecho existente do caminho; nome de arquivo higienizado; extensão forçada para o tipo real do conteúdo (um JPEG não vira `claude_desktop_config.json`); e sobrescrita só com `overwrite=true`.
- **Só transporte stdio.** `--transport` aceita apenas `stdio`. Os transportes HTTP do FastMCP abrem uma porta local sem autenticação nenhuma, dando a qualquer processo da máquina uso pleno das credenciais Metabooks configuradas. Se algum dia forem necessários, exigem uma camada de autenticação e validação de `Origin` antes de voltar ao CLI.

## Formato compacto (anti-alucinação)

Modelos pequenos (ex.: Haiku) erram quando o JSON é grande — sobretudo em busca,
onde a sinopse de livros-ruído contém as palavras pesquisadas e faz o modelo
escolher o título errado (caso "O Andar do Bêbado"). Por isso as tools de produto
têm um parâmetro `view`:

- `view="compact"` (**padrão**): resposta enxuta, própria para o modelo raciocinar.
- `view="full"`: JSON completo e cru da API (comportamento antigo).

Dois níveis, complementares (`tools/produtos.py` + `tools/_compact.py`):

1. **`application/json-short` nativo da API.** `client.get`/`client.post` aceitam o
   parâmetro `accept`; as buscas/listas pedem `application/json-short` (formato
   compacto da própria Metabooks — ver a collection Postman). O corpo do POST
   segue como `application/json`; só o `Accept` muda o formato de saída.
2. **Projeção própria** (`_compact.py`) por cima: só campos de identificação, com
   **chaves em português** (que servem de rótulos amigáveis), **sem sinopse**,
   com `total` de resultados, flags `titulo_exato`/`titulo_contem` e `aviso` de
   ambiguidade. O detalhe (`compact_detail`) trunca textos longos em vez de
   despejar todos os blocos ONIX.

`titulo_exato` marca **igualdade** do título com o termo (sem acento/caixa);
`titulo_contem` marca o termo contido num título mais longo. A distinção importa:
tratar "Análise de Dom Casmurro para o Enem" como correspondência exata de
"Dom Casmurro" promovia ruído ao topo da lista e destruía a desambiguação que o
módulo existe para dar. A ordenação usa exato primeiro, contém depois.

A extração é **tolerante a schema**: cada campo é buscado por chaves candidatas
(constantes `CANDIDATES*`/`*_CANDS` e extratores `_extract_*` no topo de
`_compact.py`); se reconhecer pouco, uma rede de segurança (`_shrink`) devolve o
registro cru **reduzido** — nunca vazio.

Os candidatos foram **conferidos contra respostas reais da API (v2.5.0, 2026-07)**,
que expõe TRÊS formas distintas, todas cobertas:

1. **Busca/lista "long"** (`GET /products`, `Accept: application/json`) — campos
   planos: `id`, `isbn`, `title`, `subTitle`, `publisher`, `publicationDate`,
   `productFormId`/`productType`, `priceBrl`, `author`/`contributors[].fullName`,
   `state`, `language`.
2. **json-short** (`Accept: application/json-short`) — subconjunto enxuto com os
   MESMOS nomes planos da forma 1.
3. **Detalhe "long"** (`GET /product/{id}`) — estilo ONIX aninhado:
   `titles[].title`, `identifiers[].idValue` (por `productIdentifierType` 15/03),
   `contributors[].firstName/lastName` + `contributorRole`, `prices[].priceAmount`
   + `currencyCode`, `form.productForm`, `extent.mainContentPageCount`,
   `languages[].languageCode`, `publishers[].publisherName`, `productAvailability`,
   `active`.

Códigos são traduzidos para PT quando **verificáveis** (ISO 639, listas ONIX
5/17/150, campo `state`). Os códigos numéricos de disponibilidade
(`availabilityStatePublisher`/`productAvailability`) **não** são mapeados — seu
significado não é confiável aqui (um título `archived` vem com código `40`), então
a disponibilidade legível usa `state`/`active`, e o código cru fica só no detalhe
reduzido.

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
- **`serverInfo.version` no handshake é a versão do projeto (desde a 2.7.0).** O `FastMCP`
  **não** aceita `version=` — passar esse argumento derruba o servidor no construtor, e era
  esse o defeito da 2.6.0. `build_server()` publica a versão depois de construir, em
  `mcp._mcp_server.version` (lida do metadado do pacote instalado via `importlib.metadata`),
  que é o que o `initialize` devolve. Rodando da árvore de código sem instalar, a versão
  aparece como `0.0.0+local`. Para saber qual cópia foi iniciada, a linha
  `Using MCP server command:` em `mcp-server-metabooks.log` continua sendo a fonte.

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
pip install -e ".[dev]"
```

A flag `-e` instala em modo editável: alterações em `src/` refletem imediatamente sem reinstalar.
O extra `[dev]` traz `pytest` e `anyio` (a suíte).

## Testes

```bash
pytest -q                  # suíte completa (150 testes, sem rede)
pytest tests/test_tools.py  # só as 12 tools via sessão MCP
```

Nada de rede: `tests/fake_api.py` é uma API Metabooks falsa servida por
`httpx.MockTransport`, que **aplica as regras do contrato** em vez de responder
qualquer coisa — token obrigatório e 403 para token de escopo errado, 406 para
`Accept` indevido em `/cover` e em `multipleProducts`, 404 para path
desconhecido, e roteamento sobre o path **ainda percent-encoded** (é assim que um
servidor HTTP real enxerga `%2F`, e é o que torna o teste de travessia honesto).

Detalhes da suíte que importam ao mexer nela:

- A sessão MCP em memória usa task groups do anyio, então a suíte roda no
  **plugin do anyio** (`pytest.mark.anyio` + fixture `anyio_backend`), não no
  pytest-asyncio: este último executa fixture e teste em tasks diferentes e o
  cancel scope estoura no teardown.
- Os testes de expiração de token usam `api.revoke_all_issued()` em vez de um
  contador de 401 — é determinístico sob concorrência.
- Cada login da API falsa emite um token **novo**, como a real; é isso que
  permite distinguir "token velho" de "token recém-renovado" no teste de relogin
  concorrente.
- Downloads são confinados a uma `tmp_path` pela fixture `downloads`, que define
  `METABOOKS_DOWNLOAD_DIR` — nenhum teste escreve em `~/Downloads`.

`tests/test_api_contract.py` compara o servidor com a collection Postman da MVB
guardada em `tests/fixtures/`: cobertura de endpoints, `page` base 1, `size`
máximo 250, formato dos corpos de POST, qualificadores de busca documentados e a
restrição de `Accept` do `multipleProducts`. Ao receber uma collection atualizada
da MVB, substitua o arquivo e rode a suíte: as divergências aparecem como falhas.

## CI

`.github/workflows/ci.yml` roda a suíte em Ubuntu/Windows/macOS × Python
3.12/3.13, e tem um job separado (`resolucao-de-dependencias`) que faz
`pip install .` numa árvore limpa, em matriz nas duas pontas do teto do SDK
(`1.26.0` e a resolvida) — é a guarda contra as regressões de dependência
descritas acima.

Os dois jobs constroem o servidor de verdade:

```yaml
run: python -c "from metabooks_mcp.server import build_server; build_server()"
```

Essa linha é a que importa. `metabooks-mcp --help` continua no CI, mas **não
prova inicialização**: o argparse trata o `--help` e sai antes da construção do
servidor. Quando o CI só tinha o `--help`, um construtor inválido passou por ele
sem arranhão.

A rodada ao vivo (abaixo) **não** entra no CI: exige credenciais de produção e
consome um slot de sessão paralela da MVB a cada execução.

## Como cortar uma versão

A versão mora num lugar só: `version` no `pyproject.toml`.
`metabooks_mcp/__init__.py` a lê da metadata do pacote instalado, e `build_server()`
a publica em `mcp._mcp_server.version`, que é o `serverInfo.version` do handshake.
Não há número de versão escrito à mão em outro arquivo — não saia procurando.

1. Bumpe `version` no `pyproject.toml`.
2. **Reinstale** (`pip install -e .`) e rode a suíte. O reinstall não é opcional: a
   metadata do pacote instalado é congelada no momento da instalação, inclusive em
   modo editável. Sem ele, `__version__` continua devolvendo o número antigo e o
   servidor anuncia a versão velha no handshake.
   Note que `test_handshake_reporta_a_versao_do_projeto` **não pega isso** — ele
   compara o handshake com a metadata instalada, que é a mesma fonte dos dois lados;
   passa com o `pyproject.toml` em qualquer número. O que ele guarda é o servidor
   deixar de publicar a versão, não você esquecer o bump. Em instalação limpa
   (`pip install .`, o que o CI e o usuário final fazem) a metadata sai do
   `pyproject.toml`, então a divergência só existe no ambiente de desenvolvimento.
3. Atualize a nota de versão nos guias, se o release corrigir algo que o usuário
   final precise saber para decidir se atualiza (foi o caso da 2.7.0, que corrigiu
   um servidor que não iniciava).
4. Tag anotada na `main`: `git tag -a vX.Y.Z -m "..."` e `git push origin vX.Y.Z`.

O canal de distribuição é o ZIP da `main` pelo botão **Code** do GitHub, que é o que
o README e o guia do macOS mandam baixar — a tag serve de marco histórico, não de
artefato de instalação. Se um dia a instrução passar a apontar para uma release, os
dois guias mudam junto (Passo 2 e a seção de atualização de cada um).

## Rodada de validação contra a API real

A suíte offline valida o comportamento do servidor; ela não pode confirmar que
produção responde com as formas que simulamos. Duas ferramentas cobrem isso,
ambas somente leitura e para rodar **na máquina de quem tem as credenciais** —
nunca em CI compartilhado, e sem colar credenciais em chat ou issue.

### 1. `scripts/smoke_live.py` — valida a FORMA das respostas

```bash
export METABOOKS_USERNAME=...        # ou METABOOKS_METADATA_TOKEN=...
export METABOOKS_PASSWORD=...
export METABOOKS_COVER_TOKEN=...     # opcional
export METABOOKS_MMO_TOKEN=...       # opcional
python scripts/smoke_live.py         # gera smoke-report.md
```

Faz **um** login, desloga no fim e sonda ~55 pontos: nomes de campo esperados por
`_compact.py` nas três formas da API, chaves do envelope, base da paginação
(`number` 0 vs 1), limites de `size`, `Accept` de ONIX e de `/cover`, os sete
índices, os onze qualificadores de busca, `multipleProducts` em json e
json-short, e o host das URLs de mídia.

Garantias de sigilo, porque o relatório é feito para circular:

- credenciais e tokens são substituídos por `***` em toda a saída, inclusive em
  mensagens de erro que ecoem cabeçalhos ou querystrings;
- por padrão o relatório traz só a **estrutura** das respostas (nomes de chaves e
  tipos), não títulos, sinopses, preços ou ISBNs de clientes. `--incluir-amostras`
  liga os valores reais e só deve ser usado para revisão interna;
- `smoke-report.*` está no `.gitignore`.

Código de saída 1 se houve FALHA; avisos não reprovam. As checagens mais
importantes de ler no relatório:

| Checagem | Por que importa |
|---|---|
| `base da paginação` | `_compact._envelope` faz `pagina = number + 1`. Se produção não for base 0, a normalização está errada. |
| `busca json-short` / `detalhe (json)` | Lista os campos esperados que estiverem AUSENTES. Campo renomeado = projeção compacta empobrecendo em silêncio. |
| `tipos de identificador` | Sem `productIdentifierType=15`, o ISBN-13 do detalhe compacto sai errado. |
| `URL de mídia (…)` | Chama `client._same_api_host` na URL real. **FALHA aqui significa que a guarda anti-SSRF está bloqueando mídia legítima** — foi endurecida na v2.6.0 e é a checagem mais provável de quebrar se a MVB mudar o host dos arquivos. |
| `size=251` / `size=0` | Confirma que os limites do schema (1–250) coincidem com os da API. |
| `POST /products (json)` | O MCP envia `Content-Type: application/json`; a collection sugere `json-short`. Um 415 aqui indica que `client.post` precisa espelhar o `Accept`. |
| `qualificador …` | 0 resultados pode ser catálogo sem correspondência **ou** qualificador inexistente. Confira à mão os que aparecerem com aviso antes de mantê-los no help. |
| `index/…` | Um índice que responda 4xx deve sair do `Literal` de `metabooks_index_search`. |

### 2. `tests/test_live.py` — valida o RESULTADO das tools

```bash
export METABOOKS_LIVE=1
export METABOOKS_USERNAME=... METABOOKS_PASSWORD=...
pytest tests/test_live.py -v
```

Roda as 12 tools através de uma sessão MCP real contra produção e verifica o que
o Claude efetivamente recebe: projeção compacta preenchida (falha explicitamente
se cair na rede de segurança do `_shrink`, o sinal de que os nomes de campo
mudaram), `titulo_exato` casando com dado real, paginação sem repetir registros,
ONIX voltando XML, capa renderizável dentro do limite inline, imagem de mídia
reduzida a ≤ 1024 px, e o confinamento de download valendo também em produção.

Sem `METABOOKS_LIVE=1` a suíte é pulada; os downloads vão para a `tmp_path` do
pytest, nunca para `~/Downloads`. Testes sem dado aplicável (título sem capa, sem
mídia cadastrada) aparecem como `skip` com o motivo, não como falha.

Personalização: `METABOOKS_LIVE_BUSCA`, `METABOOKS_LIVE_ISBN`,
`METABOOKS_LIVE_EDITORA`.

### Ordem sugerida

1. `python scripts/smoke_live.py` e leia a seção **Falhas** do relatório.
2. `METABOOKS_LIVE=1 pytest tests/test_live.py -v`.
3. Havendo divergência, o ajuste é quase sempre em `tools/_compact.py` (nomes de
   campo), `client._same_api_host` (host de mídia) ou nos limites em
   `tools/produtos.py`. Depois de corrigir, `pytest -q` para garantir que a suíte
   offline continua verde e atualize a API falsa em `tests/fake_api.py` para
   refletir o comportamento real observado — é o que impede a divergência de
   voltar.

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

Valores vindos do modelo que entram no path **precisam** passar por
`path_segment` (ver seção de Segurança):

```python
from ..client import path_segment
# ...
return await client.get(f"publisher/{path_segment(mvb_id)}")
```

Para devolver uma imagem (como em `capas.py`), retorne um `Image` do FastMCP
(`Accept` tem de ser `*/*`: o servidor de capas responde 406 a `image/jpeg`):

```python
from mcp.server.fastmcp import Image
# ...
data = await client.get_bytes("cover/9788530951382/m", scope="cover", accept="*/*")
return Image(data=data, format="jpeg")
```

Para gravar arquivo, use `_files.resolve_target` e trate `DestinationError` —
nunca chame `open()` num caminho vindo do modelo sem passar por ele:

```python
from ._files import DestinationError, allowed_roots, resolve_target
# ...
try:
    target = resolve_target(dest, filename, expected_ext="pdf", overwrite=overwrite)
except DestinationError as exc:
    return {"error": str(exc), "pastas_permitidas": allowed_roots()}
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
| `METABOOKS_DOWNLOAD_DIR` | Pastas onde os downloads podem gravar, separadas por `os.pathsep` (padrão: `~/Downloads`) |
| `METABOOKS_ENABLE_UI_APP` | (Experimental) `1`/`true` liga o app HTML (MCP Apps) da capa via recurso `ui://` |

## Tecnologias

- [Python 3.12+](https://www.python.org/)
- [FastMCP](https://github.com/jlowin/fastmcp) — framework MCP de alto nível
- [httpx](https://www.python-httpx.org/) — cliente HTTP assíncrono
- [python-dotenv](https://github.com/theskumar/python-dotenv) — leitura de `.env`
- [Pillow](https://python-pillow.org/) — redução de imagens de mídia para exibição inline
- [hatchling](https://hatch.pypa.io/) — build system
