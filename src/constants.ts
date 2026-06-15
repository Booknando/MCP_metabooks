/**
 * Constantes compartilhadas para o servidor MCP da Metabooks.
 *
 * A URL base é configurável porque o ambiente de teste varia entre
 * staging e rc (ver "API de Teste Metabooks"), enquanto produção é fixa.
 */

// URL base da API. Pode ser sobrescrita via METABOOKS_BASE_URL.
// Produção: https://api.metabooks.com/api/v2
// Staging:  https://staging.kubernetes.br.metabooks.com/api/v2
// RC:       https://rc.kubernetes.br.metabooks.com/api/v2
export const DEFAULT_BASE_URL = "https://api.metabooks.com/api/v2";

// Limite máximo de caracteres em uma resposta antes de truncar,
// para não estourar o contexto do modelo.
export const CHARACTER_LIMIT = 25000;

// Tamanho máximo de página aceito pela API (5.6.4).
export const MAX_PAGE_SIZE = 250;

// Timeout das requisições HTTP em milissegundos.
export const REQUEST_TIMEOUT = 30000;

// Limite de ISBNs por busca em lote (5.6.3).
export const MAX_BATCH_ISBNS = 500;

/**
 * Tipos de mídia (JSON types pós-changeover) retornados pelo endpoint
 * /asset/mmo. Mapeamento Nome -> {tipoDeArquivo, descrição} extraído da
 * seção 5.9.1 da especificação. Usado para enriquecer a leitura de mídia.
 */
export const MEDIA_TYPE_INFO: Record<string, { fileType: string; label: string }> = {
  FRONTCOVER: { fileType: "jpg", label: "Capa (frente)" },
  BACKCOVER: { fileType: "jpg", label: "Quarta capa" },
  COVER_PACK: { fileType: "jpg", label: "Outras imagens de capa / orelha interna" },
  FULL_COVER: { fileType: "jpg", label: "Capa completa" },
  IMAGE_SAMPLE_CONTENT: { fileType: "jpg", label: "Imagem de amostra do miolo" },
  TABLE_OF_CONTENT: { fileType: "pdf", label: "Sumário" },
  DESCRIPTION: { fileType: "pdf", label: "Descrição / sinopse / orelha" },
  AUTHOR_IMAGE: { fileType: "jpg", label: "Foto do autor" },
  AUDIO_SAMPLE_CONTENT: { fileType: "mp3/wav", label: "Amostra de áudio" },
  TEXT_SAMPLE_CONTENT: { fileType: "pdf/epub", label: "Amostra de texto / primeiro capítulo" },
  REVIEW: { fileType: "pdf", label: "Resenha / citação de resenha" },
  INTRODUCTION: { fileType: "pdf", label: "Prefácio / introdução" },
  PRODUCT_INDEX: { fileType: "pdf", label: "Índice remissivo" },
  PUBLISHER_LOGO: { fileType: "jpg", label: "Logo da editora" },
  IMPRINT_LOGO: { fileType: "jpg", label: "Logo do selo" },
  AUTHOR_PRESENTATION_TEXT: { fileType: "pdf", label: "Apresentação do autor (texto)" },
  AUTHOR_PRESENTATION_AUDIO: { fileType: "mp3/wav", label: "Apresentação do autor (áudio)" },
  AUTHOR_INTERVIEW_TEXT: { fileType: "pdf", label: "Entrevista com o autor (texto)" },
  AUTHOR_INTERVIEW_AUDIO: { fileType: "mp3/wav", label: "Entrevista com o autor (áudio)" },
  AUTHOR_READING: { fileType: "mp3/wav", label: "Autor lendo a obra" },
  STAGE_IMAGE: { fileType: "jpg", label: "Imagem de hierarquia" },
  FEATURE_ARTICLE: { fileType: "pdf", label: "Artigo / matéria" },
  PRESS_RELEASE: { fileType: "pdf", label: "Release de imprensa" },
  PROMOTIONAL_EVENT_MATERIAL_TEXT: { fileType: "pdf", label: "Material promocional (texto)" },
  PROMOTIONAL_EVENT_MATERIAL_AUDIO: { fileType: "mp3/wav", label: "Material promocional (áudio)" },
  PROMOTIONAL_EVENT_MATERIAL_IMAGE: { fileType: "jpg", label: "Material promocional (imagem)" },
  INSTRUCTIONAL_MATERIAL_TEXT: { fileType: "pdf", label: "Material instrucional (texto)" },
  INSTRUCTIONAL_MATERIAL_AUDIO: { fileType: "mp3/wav", label: "Material instrucional (áudio)" },
  INSTRUCTIONAL_MATERIAL_IMAGE: { fileType: "jpg", label: "Material instrucional (imagem)" },
  ERRATA: { fileType: "pdf", label: "Errata" },
  COLLECTION_DESCRIPTION: { fileType: "pdf", label: "Descrição da série" },
  SERIES_IMAGE: { fileType: "jpg", label: "Imagem da série" },
  SERIES_LOGO: { fileType: "jpg", label: "Logo da série" },
  BIBLIOGRAPHIC: { fileType: "pdf", label: "Bibliografia" },
  PUBLISHERS_CATALOGUE: { fileType: "pdf", label: "Catálogo / preview da editora" },
  PRODUCT_ARTWORK: { fileType: "jpg", label: "Imagem do produto" },
  PRODUCT_LOGO: { fileType: "jpg", label: "Logo do produto" },
  WALLPAPER: { fileType: "jpg", label: "Wallpaper" },
  MASTER_BRAND_LOGO: { fileType: "jpg", label: "Logo da marca" },
};

/**
 * Valores possíveis do campo productType (seção 9.3.1).
 */
export const PRODUCT_TYPE_INFO: Record<string, string> = {
  pbook: "Livro impresso",
  ebook: "E-book",
  abook: "Áudio/vídeo",
  calendar: "Calendário",
  map: "Material cartográfico",
  Digital: "Produto digital",
  nonbook: "Não-livro",
  undefined: "Indefinido",
  Series: "Série",
  Hierarchy: "Hierarquia",
};

/**
 * Chaves de chave de imposto (taxKeyBrl), seção 9.4.2.
 */
export const TAX_KEY_INFO: Record<string, string> = {
  "0": "Sem informação de imposto",
  "1": "Alíquota reduzida",
  "2": "Alíquota cheia",
  "6": "Designação de bundle (split de imposto)",
};

/**
 * Tamanhos de capa aceitos pelo endpoint /cover (seção 5.10.2).
 */
export const COVER_SIZES = ["s", "m", "l", "original"] as const;
