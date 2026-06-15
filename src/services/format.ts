/**
 * Utilitários de formatação compartilhados entre as ferramentas.
 * Centraliza truncamento, montagem do envelope de paginação e
 * renderização em markdown de produtos e páginas de resultados.
 */

import { CHARACTER_LIMIT, PRODUCT_TYPE_INFO } from "../constants.js";
import { ProductSummary, SearchResultPage } from "../types.js";

/**
 * Garante que o texto não estoure o limite de caracteres.
 * Se estourar, anexa um aviso orientando a refinar a busca.
 */
export function enforceCharacterLimit(text: string): string {
  if (text.length <= CHARACTER_LIMIT) return text;
  const head = text.slice(0, CHARACTER_LIMIT);
  return (
    head +
    `\n\n[...resposta truncada em ${CHARACTER_LIMIT} caracteres. ` +
    "Reduza 'size', use 'page' para paginar ou aplique filtros de busca mais específicos.]"
  );
}

/** Monta um envelope de paginação consistente a partir da página da API. */
export function buildPageEnvelope<T>(page: SearchResultPage<T>) {
  const currentPageZeroBased = page.number ?? 0;
  const hasMore =
    page.lastPage === false ||
    page.last === false ||
    currentPageZeroBased + 1 < (page.totalPages ?? 1);
  return {
    total_elements: page.totalElements ?? 0,
    total_pages: page.totalPages ?? 1,
    page: currentPageZeroBased + 1, // converte para base 1 (parâmetro de entrada)
    page_size: page.size,
    count_on_page: page.numberOfElements ?? page.content?.length ?? 0,
    has_more: hasMore,
    next_page: hasMore ? currentPageZeroBased + 2 : undefined,
  };
}

/** Descreve o productType de forma legível. */
function describeProductType(pt?: string): string {
  if (!pt) return "";
  const label = PRODUCT_TYPE_INFO[pt];
  return label ? `${pt} (${label})` : pt;
}

/** Renderiza um único produto resumido em markdown. */
export function renderProductMarkdown(p: ProductSummary): string {
  const idLine = p.isbn || p.gtin || p.identifier || p.productId || "sem identificador";
  const lines: string[] = [`### ${p.title ?? "(sem título)"} — ${idLine}`];
  if (p.subTitle) lines.push(`- **Subtítulo**: ${p.subTitle}`);
  if (p.author) lines.push(`- **Autor(es)**: ${p.author}`);
  if (p.publisher) {
    const mb = p.publisherMbId ? ` (MB ID ${p.publisherMbId})` : "";
    lines.push(`- **Editora**: ${p.publisher}${mb}`);
  }
  if (p.productType) lines.push(`- **Tipo**: ${describeProductType(p.productType)}`);
  if (p.productForm) lines.push(`- **Forma do produto**: ${p.productForm}`);
  if (p.publicationDate) lines.push(`- **Publicação**: ${p.publicationDate}`);
  if (p.edition) lines.push(`- **Edição**: ${p.edition}`);
  if (typeof p.priceBrl === "number") {
    const fixo = p.priceFixedBrl ? " (preço fixo)" : "";
    const prov = p.priceProvisionalBrl ? " (provisório)" : "";
    lines.push(`- **Preço (BRL)**: ${p.priceBrl}${fixo}${prov}`);
  }
  if (p.productAvailability) lines.push(`- **Disponibilidade**: ${p.productAvailability}`);
  if (typeof p.active === "boolean") lines.push(`- **Ativo**: ${p.active ? "sim" : "não"}`);
  if (p.productId) lines.push(`- **UUID**: ${p.productId}`);
  if (p.lastModificationDate) lines.push(`- **Atualizado em**: ${p.lastModificationDate}`);
  return lines.join("\n");
}

/** Renderiza uma página de resultados de busca em markdown. */
export function renderSearchPageMarkdown(
  page: SearchResultPage,
  heading: string
): string {
  const env = buildPageEnvelope(page);
  const lines: string[] = [
    `# ${heading}`,
    "",
    `Total de resultados: ${env.total_elements} | Página ${env.page} de ${env.total_pages} | ` +
      `Nesta página: ${env.count_on_page}`,
    "",
  ];
  const items = page.content ?? [];
  if (items.length === 0) {
    lines.push("_Nenhum resultado nesta página._");
  } else {
    for (const item of items) {
      lines.push(renderProductMarkdown(item));
      lines.push("");
    }
    if (env.has_more) {
      lines.push(
        `_Há mais resultados. Use page=${env.next_page} para continuar._`
      );
    }
  }
  return lines.join("\n");
}

/**
 * Empacota o resultado de uma ferramenta no formato esperado pelo MCP,
 * respeitando o limite de caracteres no conteúdo textual.
 */
export function toolResult(text: string, structured?: Record<string, unknown>) {
  return {
    content: [{ type: "text" as const, text: enforceCharacterLimit(text) }],
    ...(structured ? { structuredContent: structured } : {}),
  };
}
