/**
 * Definições de tipos para as respostas da API REST v2 da Metabooks.
 * Baseadas na especificação técnica v2.6 (19.08.2019) e nos exemplos
 * da coleção Postman.
 */

/** Qual token/escopo usar numa chamada. */
export enum TokenScope {
  METADATA = "metadata",
  COVER = "cover",
  MMO = "mmo",
}

/** Formato de saída das ferramentas. */
export enum ResponseFormat {
  MARKDOWN = "markdown",
  JSON = "json",
}

/** Wrapper de paginação retornado pelas buscas (5.6.4.1). */
export interface SearchResultPage<T = ProductSummary> {
  content: T[];
  totalElements: number;
  totalPages: number;
  numberOfElements: number;
  number: number; // página atual, base 0
  size: number;
  first?: boolean;
  last?: boolean;
  firstPage?: boolean;
  lastPage?: boolean;
  sort?: unknown;
}

/** Item resumido de produto numa lista de resultados (JSON-short). */
export interface ProductSummary {
  productId?: string;
  isbn?: string;
  gtin?: string;
  issn?: string;
  title?: string;
  subTitle?: string;
  author?: string;
  publisher?: string;
  publisherMbId?: string;
  publicationDate?: string;
  edition?: string;
  productType?: string;
  productForm?: string;
  productFormDetail?: string[];
  priceBrl?: number;
  priceFixedBrl?: boolean;
  priceProvisionalBrl?: boolean;
  priceCalculatedBrl?: boolean;
  productAvailability?: string;
  active?: boolean;
  creationDate?: string;
  lastModificationDate?: string;
  coverUrl?: string;
  genreCode?: string;
  language?: string;
  [key: string]: unknown; // demais campos da resposta longa
}

/** Item de mídia retornado por /asset/mmo (5.9.3). */
export interface MediaAsset {
  type: string;
  url: string;
  sequenceNumber?: number | string;
}

/** Dados de editora retornados por /publisher (5.12.2). */
export interface PublisherData {
  mbId?: string;
  shortName?: string;
  name?: string;
  street?: string;
  cityStreet?: string;
  zipStreet?: string;
  location?: string;
  country?: string | null;
  postbox?: string;
  zipPostbox?: string;
  phone?: string;
  fax?: string;
  email?: string;
  url?: string;
  isbnPrefixes?: string;
  CNPJ?: string;
  [key: string]: unknown;
}

/** Entrada de índice retornada por /index (5.11.3). */
export interface IndexEntry {
  value: string;
  count: number;
}

/** Estrutura de erro JSON da API (5.4.2). */
export interface ApiErrorBody {
  error?: string;
  error_description?: string;
}
