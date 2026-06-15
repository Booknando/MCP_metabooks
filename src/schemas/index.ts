/**
 * Schemas Zod de validação de entrada para todas as ferramentas.
 * Todos usam .strict() para rejeitar campos inesperados.
 */

import { z } from "zod";
import { MAX_BATCH_ISBNS, MAX_PAGE_SIZE } from "../constants.js";
import { ResponseFormat } from "../types.js";

const responseFormatField = z
  .nativeEnum(ResponseFormat)
  .default(ResponseFormat.MARKDOWN)
  .describe(
    "Formato de saída: 'markdown' (legível) ou 'json' (estruturado). Padrão: markdown."
  );

const pageField = z
  .number()
  .int()
  .min(1)
  .default(1)
  .describe("Número da página (começa em 1). Padrão: 1.");

const sizeField = z
  .number()
  .int()
  .min(1)
  .max(MAX_PAGE_SIZE)
  .default(50)
  .describe(`Itens por página (1 a ${MAX_PAGE_SIZE}). Padrão: 50.`);

/** Busca de produtos (quick / boolean). */
export const SearchProductsSchema = z
  .object({
    search: z
      .string()
      .min(1, "Informe um termo de busca.")
      .describe(
        "Frase de busca. Sem prefixo de campo faz quick search (título, autor, editora, ISBN etc.). " +
          "Com operadores booleanos da Metabooks: ex. 'ST=Linux and PF=E*', 'VL=Artmed', " +
          "'AU=\"May, Karl\"', 'RH=RC712' (série), 'TI=gymnastik', 'WG=?250' (grupo de produto), " +
          "'AD=20190301^20190815' (intervalo de datas). NÃO faça URL-encoding: o servidor cuida disso."
      ),
    page: pageField,
    size: sizeField,
    sort: z
      .enum([
        "identifier",
        "author",
        "titleAndSubtitle",
        "publisher",
        "publisherMbId",
        "publicationDate",
        "productAvailability",
        "price",
        "creationDate",
        "lastModificationDate",
        "productType",
        "active",
      ])
      .optional()
      .describe("Coluna de ordenação (opcional). Padrão: relevância (score)."),
    direction: z
      .enum(["asc", "desc"])
      .optional()
      .describe("Direção da ordenação: 'asc' ou 'desc'."),
    active: z
      .boolean()
      .optional()
      .describe(
        "Filtra por títulos ativos (true) ou inativos (false). Omitido = ativos e inativos."
      ),
    response_format: responseFormatField,
  })
  .strict();

/** Busca em lote por ISBNs. */
export const BatchSearchSchema = z
  .object({
    isbns: z
      .array(z.string().min(1))
      .min(1, "Informe ao menos um ISBN/GTIN.")
      .max(MAX_BATCH_ISBNS, `Máximo de ${MAX_BATCH_ISBNS} ISBNs por chamada.`)
      .describe(
        `Lista de ISBNs/GTINs (até ${MAX_BATCH_ISBNS}). Curingas com '*' são aceitos (ex.: '9783923*').`
      ),
    search: z
      .string()
      .optional()
      .describe(
        "Filtro booleano adicional aplicado ao lote (opcional), ex.: 'AD=20150319^20150320'. Sem URL-encoding."
      ),
    page: pageField,
    size: sizeField,
    response_format: responseFormatField,
  })
  .strict();

/** Detalhe de um produto por ID. */
export const GetProductSchema = z
  .object({
    id: z
      .string()
      .min(1, "Informe o ID do produto.")
      .describe(
        "Identificador do produto: UUID de 32 caracteres, ou ISBN-13/EAN/GTIN (não hifenizado)."
      ),
    id_type: z
      .enum(["uuid", "isbn13", "ean", "gtin"])
      .default("uuid")
      .describe(
        "Tipo do ID informado. Padrão: 'uuid'. Use 'isbn13', 'ean' ou 'gtin' conforme o caso."
      ),
    format: z
      .enum(["json", "onix30-short", "onix30-ref"])
      .default("json")
      .describe(
        "Formato do detalhe: 'json' (completo, JSON-long), 'onix30-short' ou 'onix30-ref' (XML ONIX 3.0)."
      ),
    response_format: responseFormatField,
  })
  .strict();

/** Detalhe de múltiplos produtos por UUID. */
export const GetMultipleProductsSchema = z
  .object({
    ids: z
      .array(z.string().min(1))
      .min(1, "Informe ao menos um UUID.")
      .max(250, "Máximo de 250 UUIDs por chamada.")
      .describe("Lista de UUIDs de produto (32 caracteres). A ordem é preservada na resposta."),
    response_format: responseFormatField,
  })
  .strict();

/** Listagem de URLs de mídia/capa de um produto. */
export const GetMediaAssetsSchema = z
  .object({
    product_id: z
      .string()
      .min(1, "Informe o UUID do produto.")
      .describe("UUID (32 caracteres) do produto cujas URLs de mídia/capa serão listadas."),
    type_filter: z
      .string()
      .optional()
      .describe(
        "Filtra por um tipo de mídia (ex.: 'FRONTCOVER', 'TABLE_OF_CONTENT', 'TEXT_SAMPLE_CONTENT'). Opcional."
      ),
    response_format: responseFormatField,
  })
  .strict();

/** Monta a URL de uma capa por ISBN/GTIN. */
export const GetCoverUrlSchema = z
  .object({
    id: z
      .string()
      .min(1, "Informe o ISBN/GTIN.")
      .describe("ISBN-13 ou GTIN do título, NÃO hifenizado (ex.: 9783411046508)."),
    size: z
      .enum(["s", "m", "l", "original"])
      .default("m")
      .describe(
        "Tamanho da capa: 's' (90px larg.), 'm' (200px), 'l' (599px alt.) ou 'original'. Padrão: 'm'."
      ),
    response_format: responseFormatField,
  })
  .strict();

/** Busca em índice (autocompletar). */
export const IndexSearchSchema = z
  .object({
    field: z
      .enum([
        "author",
        "publisher",
        "title",
        "keyword",
        "set",
        "collection",
        "identifier",
      ])
      .describe(
        "Campo a indexar: author, publisher, title, keyword, set, collection ou identifier."
      ),
    term: z
      .string()
      .min(1, "Informe o termo de busca do índice.")
      .describe("Termo a buscar no índice (retorna até 100 entradas, sem scroll)."),
    response_format: responseFormatField,
  })
  .strict();

/** Dados de editora por MVB ID. */
export const GetPublisherSchema = z
  .object({
    mvb_id: z
      .string()
      .min(1, "Informe o MVB/MB ID da editora.")
      .describe("ID da editora (MVB/MB ID), ex.: 'BR0090053'."),
    response_format: responseFormatField,
  })
  .strict();

export type SearchProductsInput = z.infer<typeof SearchProductsSchema>;
export type BatchSearchInput = z.infer<typeof BatchSearchSchema>;
export type GetProductInput = z.infer<typeof GetProductSchema>;
export type GetMultipleProductsInput = z.infer<typeof GetMultipleProductsSchema>;
export type GetMediaAssetsInput = z.infer<typeof GetMediaAssetsSchema>;
export type GetCoverUrlInput = z.infer<typeof GetCoverUrlSchema>;
export type IndexSearchInput = z.infer<typeof IndexSearchSchema>;
export type GetPublisherInput = z.infer<typeof GetPublisherSchema>;
