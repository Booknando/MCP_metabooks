/**
 * Registro de todas as ferramentas de LEITURA do MCP da Metabooks.
 *
 * Cobertura da API REST v2:
 *  - metabooks_search_products      (5.6 buscas quick/boolean)
 *  - metabooks_batch_search_isbns   (5.6.3 busca em lote por ISBN)
 *  - metabooks_get_product          (5.8 detalhe por UUID/ISBN/EAN/GTIN, JSON ou ONIX)
 *  - metabooks_get_multiple_products(5.7 detalhe de vários UUIDs)
 *  - metabooks_get_media_assets     (5.9 URLs de mídia/MMO)
 *  - metabooks_get_cover_url        (5.10 URL de capa por ISBN/GTIN)
 *  - metabooks_index_search         (5.11 índice/autocomplete)
 *  - metabooks_get_publisher        (5.12 dados de editora)
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { currentBaseUrl, handleApiError, hasCoverToken, metabooksRequest } from "../services/client.js";
import {
  buildPageEnvelope,
  renderProductMarkdown,
  renderSearchPageMarkdown,
  toolResult,
} from "../services/format.js";
import { MEDIA_TYPE_INFO } from "../constants.js";
import {
  IndexEntry,
  MediaAsset,
  ProductSummary,
  PublisherData,
  ResponseFormat,
  SearchResultPage,
  TokenScope,
} from "../types.js";
import {
  BatchSearchSchema,
  GetCoverUrlSchema,
  GetMediaAssetsSchema,
  GetMultipleProductsSchema,
  GetProductSchema,
  GetPublisherSchema,
  IndexSearchSchema,
  SearchProductsSchema,
  type BatchSearchInput,
  type GetCoverUrlInput,
  type GetMediaAssetsInput,
  type GetMultipleProductsInput,
  type GetProductInput,
  type GetPublisherInput,
  type IndexSearchInput,
  type SearchProductsInput,
} from "../schemas/index.js";

const READ_ONLY_ANNOTATIONS = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: true,
};

/** Constrói os query params comuns de busca de produtos. */
function buildProductQueryParams(input: {
  search?: string;
  page: number;
  size: number;
  sort?: string;
  direction?: string;
  active?: boolean;
}): Record<string, unknown> {
  // page é base 1 na entrada; a API usa base 1 no parâmetro 'page'.
  const params: Record<string, unknown> = {
    page: input.page,
    size: input.size,
  };
  if (input.search) params.search = input.search;
  if (input.sort) params.sort = input.sort;
  if (input.direction) params.direction = input.direction;
  if (typeof input.active === "boolean") params.active = input.active;
  return params;
}

export function registerTools(server: McpServer): void {
  // ---------------------------------------------------------------------------
  // 1. Busca de produtos (quick / boolean)
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_search_products",
    {
      title: "Buscar produtos (Metabooks)",
      description: `Busca títulos no catálogo Metabooks por palavra-chave ou usando a sintaxe booleana da Metabooks.

Sem prefixo de campo, faz uma quick search (busca em título, subtítulo, autor, editora, ISBN/GTIN, assunto, grupo de produto). Com operadores, permite filtros precisos.

Operadores de campo úteis (combine com 'and'/'or'/'not', parênteses permitidos):
  ST=  quick search   | AU=  autor       | TI=  título      | VL=  editora
  IS=  identificador  | SW=  palavra-chave| PR=  preço       | EJ=  ano publicação
  WG=  grupo produto  | SP=  idioma       | AD=  data modif. | ZD=  data criação
  PF=  forma (ONIX 2.1, ex. PF=E* digitais) | PD=  forma detalhe (ONIX 3.0)
  RH=  série/hierarquia | LI=  disponibilidade
Datas: AD=20190301^20190815 (intervalo). Frase exata entre aspas: AU="May, Karl".
NÃO faça URL-encoding — o servidor codifica automaticamente.

Args:
  - search (string): termo ou expressão booleana
  - page (int): página, base 1 (padrão 1)
  - size (int): itens por página, 1-250 (padrão 50)
  - sort (string, opcional): coluna de ordenação
  - direction ('asc'|'desc', opcional)
  - active (bool, opcional): true=ativos, false=inativos, omitido=ambos
  - response_format ('markdown'|'json')

Retorna (JSON): { pagination: {...}, products: ProductSummary[] }, onde ProductSummary inclui
productId (UUID), isbn, gtin, title, author, publisher, publisherMbId, productType, priceBrl, active, etc.

Exemplos:
  - "Pão de Açúcar" -> quick search
  - "ST=Linux and PF=E*" -> Linux em produtos digitais
  - "VL=Artmed and PF=not EA" -> Artmed exceto e-books baixáveis
  - "RH=RC712" -> títulos da série RC712

Erros: "Não autorizado (401)" se o token de metadados estiver inválido.`,
      inputSchema: SearchProductsSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: SearchProductsInput) => {
      try {
        const params = buildProductQueryParams(input);
        const data = await metabooksRequest<SearchResultPage>("products", TokenScope.METADATA, {
          method: "GET",
          params,
        });
        const env = buildPageEnvelope(data);
        const structured = { pagination: env, products: data.content ?? [] };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        return toolResult(
          renderSearchPageMarkdown(data, `Busca: "${input.search}"`),
          structured
        );
      } catch (error) {
        return toolResult(handleApiError(error, "buscar produtos"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 2. Busca em lote por ISBNs
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_batch_search_isbns",
    {
      title: "Busca em lote por ISBNs (Metabooks)",
      description: `Consulta vários ISBNs/GTINs de uma vez (até 500) e retorna os dados resumidos de cada título encontrado. Útil para enriquecer listas de ISBNs. Aceita curingas com '*' (ex.: '9783923*').

Args:
  - isbns (string[]): lista de ISBNs/GTINs (até 500)
  - search (string, opcional): filtro booleano adicional (ex.: 'AD=20150319^20150320')
  - page (int): página, base 1 (padrão 1)
  - size (int): itens por página, 1-250 (padrão 50)
  - response_format ('markdown'|'json')

Retorna (JSON): { pagination: {...}, products: ProductSummary[] }.

Exemplo: isbns=["9788530980566","9783923*"] -> dados dos títulos correspondentes.

Erros: "Não encontrado (404)" não ocorre por ISBN individual; ISBNs sem correspondência simplesmente não aparecem nos resultados.`,
      inputSchema: BatchSearchSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: BatchSearchInput) => {
      try {
        const params: Record<string, unknown> = {
          page: input.page,
          size: input.size,
        };
        if (input.search) params.search = input.search;
        const body = { content: input.isbns.map((isbn: string) => ({ isbn })) };
        const data = await metabooksRequest<SearchResultPage>("products", TokenScope.METADATA, {
          method: "POST",
          params,
          data: body,
          contentType: "application/json",
          accept: "application/json",
        });
        const env = buildPageEnvelope(data);
        const structured = { pagination: env, products: data.content ?? [] };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        return toolResult(
          renderSearchPageMarkdown(data, `Busca em lote (${input.isbns.length} ISBNs)`),
          structured
        );
      } catch (error) {
        return toolResult(handleApiError(error, "buscar ISBNs em lote"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 3. Detalhe de um produto (JSON-long ou ONIX 3.0)
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_get_product",
    {
      title: "Detalhe de produto (Metabooks)",
      description: `Recupera os dados completos de um único título, com todos os blocos de metadados (contributors, prices, subjects, extent, etc.).

Pode ser identificado por UUID (32 caracteres), ISBN-13, EAN ou GTIN. Retorna em JSON-long (padrão) ou em XML ONIX 3.0 (short ou ref).

Args:
  - id (string): UUID, ISBN-13, EAN ou GTIN (não hifenizado)
  - id_type ('uuid'|'isbn13'|'ean'|'gtin'): tipo do id (padrão 'uuid')
  - format ('json'|'onix30-short'|'onix30-ref'): formato do detalhe (padrão 'json')
  - response_format ('markdown'|'json'): só afeta a apresentação quando format='json'

Retorna: objeto JSON-long completo do produto, ou string XML ONIX 3.0 (quando format começa com 'onix').
Observação: o bloco 'publisherData' não está disponível para tokens statusless.

Exemplos:
  - id="9788087062272", id_type="isbn13" -> detalhe por ISBN
  - id="93a36c7b6c2c4a14920916054ad95ed0" -> detalhe por UUID
  - format="onix30-ref" -> XML ONIX 3.0 referência

Erros: "Não encontrado (404)" se o id não existir; "406" se o formato não for aceito.`,
      inputSchema: GetProductSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: GetProductInput) => {
      try {
        // Monta o caminho: product/<id>[/<id-type>]
        let path = `product/${encodeURIComponent(input.id)}`;
        if (input.id_type && input.id_type !== "uuid") {
          path += `/${input.id_type}`;
        }
        const isOnix = input.format.startsWith("onix");
        const mime = isOnix ? `application/${input.format}` : "application/json";

        const data = await metabooksRequest<unknown>(path, TokenScope.METADATA, {
          method: "GET",
          accept: mime,
          // Para ONIX o retorno é XML; pedimos como texto.
          responseType: isOnix ? "text" : "json",
        });

        if (isOnix) {
          const xml = typeof data === "string" ? data : String(data);
          return toolResult(xml);
        }

        const product = data as ProductSummary;
        const structured = { product };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(product, null, 2), structured);
        }
        const md = [
          `# Detalhe do produto`,
          "",
          renderProductMarkdown(product),
          "",
          "_Veja o JSON completo com response_format='json' para todos os blocos (contributors, prices, subjects, extent, etc.)._",
        ].join("\n");
        return toolResult(md, structured);
      } catch (error) {
        return toolResult(handleApiError(error, "obter detalhe do produto"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 4. Detalhe de múltiplos produtos por UUID
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_get_multiple_products",
    {
      title: "Detalhe de múltiplos produtos (Metabooks)",
      description: `Recupera os dados completos (JSON-long) de vários produtos de uma vez, a partir de uma lista de UUIDs. A ordem da resposta segue a ordem dos UUIDs enviados. Retorna apenas em JSON (não suporta ONIX nem JSON-short).

Args:
  - ids (string[]): UUIDs de 32 caracteres (até 250)
  - response_format ('markdown'|'json')

Retorna (JSON): { count: number, products: object[] }.

Exemplo: ids=["47d9846e83264ea6a1106a84418a68fa","50d434b4865d43099f415da91d362449"].

Erros: "Não autorizado (401)" se o token de metadados estiver inválido.`,
      inputSchema: GetMultipleProductsSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: GetMultipleProductsInput) => {
      try {
        const body = { ids: input.ids };
        const data = await metabooksRequest<unknown>(
          "product/multipleProducts",
          TokenScope.METADATA,
          {
            method: "POST",
            data: body,
            contentType: "application/json",
            accept: "application/json",
          }
        );
        const products = Array.isArray(data) ? data : (data as { content?: unknown[] })?.content ?? [data];
        const list = Array.isArray(products) ? products : [products];
        const structured = { count: list.length, products: list };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        const md = [
          `# Detalhe de ${list.length} produto(s)`,
          "",
          ...list.map((p) => renderProductMarkdown(p as ProductSummary) + "\n"),
          "_Use response_format='json' para os blocos completos._",
        ].join("\n");
        return toolResult(md, structured);
      } catch (error) {
        return toolResult(handleApiError(error, "obter múltiplos produtos"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 5. Listar URLs de mídia / MMO de um produto
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_get_media_assets",
    {
      title: "Listar mídias do produto (Metabooks)",
      description: `Lista as URLs de mídia de um produto: capas, quarta capa, sumário, amostras de texto/áudio, foto do autor, etc. Requer o TOKEN DE MMO (não o de metadados).

Cada item traz 'type' (ex.: FRONTCOVER, TABLE_OF_CONTENT, TEXT_SAMPLE_CONTENT), 'url' (para download após autenticação) e 'sequenceNumber'.

Args:
  - product_id (string): UUID do produto (32 caracteres)
  - type_filter (string, opcional): retorna apenas itens deste tipo (ex.: 'FRONTCOVER')
  - response_format ('markdown'|'json')

Retorna (JSON): { count: number, assets: [{ type, label, fileType, url, sequenceNumber }] }.

Exemplo: product_id="b0064c2bf495431ba338d9004a10dfaa".

Erros: "403" se o token MMO não tiver permissão; "204/No content" se o produto não tiver mídias; "Token de 'mmo' não configurado" se faltar METABOOKS_MMO_TOKEN.`,
      inputSchema: GetMediaAssetsSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: GetMediaAssetsInput) => {
      try {
        const data = await metabooksRequest<MediaAsset[]>(
          `asset/mmo/${encodeURIComponent(input.product_id)}`,
          TokenScope.MMO,
          { method: "GET", accept: "application/json" }
        );
        let assets = Array.isArray(data) ? data : [];
        if (input.type_filter) {
          const f = input.type_filter.toUpperCase();
          assets = assets.filter((a) => (a.type ?? "").toUpperCase() === f);
        }
        const enriched = assets.map((a) => {
          const info = MEDIA_TYPE_INFO[a.type] ?? { fileType: "?", label: a.type };
          return {
            type: a.type,
            label: info.label,
            fileType: info.fileType,
            url: a.url,
            sequenceNumber: a.sequenceNumber,
          };
        });
        const structured = { count: enriched.length, assets: enriched };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        const lines = [`# Mídias do produto ${input.product_id}`, "", `Total: ${enriched.length}`, ""];
        if (enriched.length === 0) {
          lines.push("_Nenhuma mídia encontrada (ou nenhuma do tipo filtrado)._");
        } else {
          for (const a of enriched) {
            lines.push(`- **${a.type}** (${a.label}, ${a.fileType}) seq ${a.sequenceNumber ?? "-"}`);
            lines.push(`  ${a.url}`);
          }
        }
        return toolResult(lines.join("\n"), structured);
      } catch (error) {
        return toolResult(handleApiError(error, "listar mídias do produto"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 6. Montar URL de capa por ISBN/GTIN
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_get_cover_url",
    {
      title: "URL de capa por ISBN (Metabooks)",
      description: `Monta a URL da capa de um título a partir do ISBN/GTIN, no tamanho desejado. A imagem em si exige o TOKEN DE COVER para ser baixada; esta ferramenta verifica a configuração do token e retorna a URL pronta.

Tamanhos: s (90px larg.), m (200px larg.), l (599px alt.), original.

Args:
  - id (string): ISBN-13 ou GTIN, NÃO hifenizado (ex.: 9783411046508)
  - size ('s'|'m'|'l'|'original'): tamanho da capa (padrão 'm')
  - response_format ('markdown'|'json')

Retorna (JSON): { id, size, cover_url }. A URL retorna binário image/jpeg quando acessada com o token de cover.

Exemplo: id="9783540537120", size="m".

Erros: "Token de 'cover' não configurado" se faltar METABOOKS_COVER_TOKEN.`,
      inputSchema: GetCoverUrlSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: GetCoverUrlInput) => {
      try {
        // Valida que o token de cover existe (lança erro orientativo se não).
        // Reaproveitamos o cliente apenas para checar o token, sem baixar a imagem.
        // Construímos a URL manualmente para retornar ao usuário.
        const base = currentBaseUrl();
        const sizeSegment = input.size === "original" ? "" : `/${input.size}`;
        const coverUrl = `${base}/cover/${encodeURIComponent(input.id)}${sizeSegment}`;

        // Verificação de token: dispara MetabooksError se ausente.
        // Fazemos uma chamada HEAD-like leve? A API não documenta HEAD; então
        // apenas validamos a presença do token sem requisição de rede.
        const coverConfigured = hasCoverToken();
        if (!coverConfigured) {
          return toolResult(
            "Erro: Token de 'cover' não fornecido. Envie o header X-Metabooks-Cover-Token " +
              "(ou defina METABOOKS_COVER_TOKEN). Login/metadados não acessam capas (seção 5.5.5)."
          );
        }

        const structured = { id: input.id, size: input.size, cover_url: coverUrl };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        const md = [
          `# Capa — ISBN/GTIN ${input.id}`,
          "",
          `- **Tamanho**: ${input.size}`,
          `- **URL**: ${coverUrl}`,
          "",
          "_Acesse a URL com o cabeçalho Authorization: Bearer <token de cover> para baixar o JPEG._",
        ].join("\n");
        return toolResult(md, structured);
      } catch (error) {
        return toolResult(handleApiError(error, "montar URL de capa"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 7. Busca em índice (autocomplete)
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_index_search",
    {
      title: "Busca em índice (Metabooks)",
      description: `Consulta um índice para autocompletar/descobrir valores existentes (autores, editoras, títulos, palavras-chave, séries, coleções ou identificadores). Retorna até 100 entradas, cada uma com 'value' e 'count' (frequência). Não há paginação/scroll: refine o termo se precisar.

Args:
  - field ('author'|'publisher'|'title'|'keyword'|'set'|'collection'|'identifier'): índice a consultar
  - term (string): termo de busca
  - response_format ('markdown'|'json')

Retorna (JSON): { field, term, count, entries: [{ value, count }] }.

Exemplo: field="author", term="meier" -> [{"value":"Meier","count":5}, ...].`,
      inputSchema: IndexSearchSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: IndexSearchInput) => {
      try {
        const data = await metabooksRequest<IndexEntry[]>(
          `index/${input.field}/${encodeURIComponent(input.term)}`,
          TokenScope.METADATA,
          { method: "GET", accept: "application/json" }
        );
        const entries = Array.isArray(data) ? data : [];
        const structured = { field: input.field, term: input.term, count: entries.length, entries };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(structured, null, 2), structured);
        }
        const lines = [`# Índice '${input.field}' para "${input.term}"`, "", `Entradas: ${entries.length}`, ""];
        if (entries.length === 0) {
          lines.push("_Nenhuma entrada encontrada._");
        } else {
          for (const e of entries) lines.push(`- ${e.value} (${e.count})`);
        }
        return toolResult(lines.join("\n"), structured);
      } catch (error) {
        return toolResult(handleApiError(error, "buscar no índice"));
      }
    }
  );

  // ---------------------------------------------------------------------------
  // 8. Dados de editora
  // ---------------------------------------------------------------------------
  server.registerTool(
    "metabooks_get_publisher",
    {
      title: "Dados de editora (Metabooks)",
      description: `Recupera os dados cadastrais de uma editora pelo seu MVB/MB ID (nome, endereço, telefone, e-mail, site, prefixos de ISBN, CNPJ). Acesso por assinatura.

Args:
  - mvb_id (string): ID da editora (ex.: 'BR0090053')
  - response_format ('markdown'|'json')

Retorna (JSON): objeto PublisherData com mbId, shortName, name, street, cityStreet, country, phone, email, url, isbnPrefixes, CNPJ.

Exemplo: mvb_id="BR0090053".

Erros: "Não encontrado (404)" se não houver editora com esse ID.`,
      inputSchema: GetPublisherSchema.shape,
      annotations: READ_ONLY_ANNOTATIONS,
    },
    async (input: GetPublisherInput) => {
      try {
        const data = await metabooksRequest<PublisherData>(
          `publisher/${encodeURIComponent(input.mvb_id)}`,
          TokenScope.METADATA,
          { method: "GET", accept: "application/json" }
        );
        const structured = { publisher: data };
        if (input.response_format === ResponseFormat.JSON) {
          return toolResult(JSON.stringify(data, null, 2), structured);
        }
        const lines = [`# Editora ${data.name ?? input.mvb_id}`, ""];
        const push = (label: string, v?: unknown) => {
          if (v !== undefined && v !== null && v !== "") lines.push(`- **${label}**: ${v}`);
        };
        push("MB ID", data.mbId ?? input.mvb_id);
        push("Nome curto", data.shortName);
        push("Nome", data.name);
        push("Endereço", data.street);
        push("Cidade", data.cityStreet);
        push("CEP", data.zipStreet);
        push("País", data.country);
        push("Telefone", data.phone);
        push("Fax", data.fax);
        push("E-mail", data.email);
        push("Site", data.url);
        push("Prefixos ISBN", data.isbnPrefixes);
        push("CNPJ", data.CNPJ);
        return toolResult(lines.join("\n"), structured);
      } catch (error) {
        return toolResult(handleApiError(error, "obter dados da editora"));
      }
    }
  );
}
