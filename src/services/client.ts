/**
 * Cliente HTTP central para a API REST v2 da Metabooks (multi-tenant).
 *
 * As credenciais vêm do contexto da requisição (services/credentials.ts):
 * cada editora envia as próprias credenciais por headers HTTP, com fallback
 * para variáveis de ambiente (modo single-tenant).
 *
 * Autenticação (seções 5.5.2 e 5.5.3):
 *  - METADADOS: login (usuário/senha -> POST /login -> accessToken) OU token
 *    estático de metadados. O token de login é cacheado POR TENANT e renovado
 *    automaticamente em caso de expiração (timeout de 60 min) ou 401/invalid_token.
 *  - CAPAS/MÍDIA: exigem tokens dedicados (seção 5.5.5). Opcionais.
 *
 * Somente leitura: apenas GET e POST de consulta.
 */

import axios, { AxiosError, AxiosRequestConfig } from "axios";
import { createHash } from "node:crypto";
import { REQUEST_TIMEOUT } from "../constants.js";
import { ApiErrorBody, TokenScope } from "../types.js";
import { currentCredentials, MetabooksCredentials } from "./credentials.js";

/** Erro de domínio com mensagem já formatada para o usuário. */
export class MetabooksError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MetabooksError";
  }
}

// --- Cache de token de login, isolado por tenant --------------------------

interface CachedToken {
  token: string;
  expiresAt: number; // epoch ms
}

// Timeout de inatividade da API é 60 min (5.5.1.2). Renovamos com 50 min de margem.
const TOKEN_TTL_MS = 50 * 60 * 1000;

// Map de cache: chave derivada de baseUrl+username -> token cacheado.
const tokenCache = new Map<string, CachedToken>();

/** Chave de cache estável e não reversível para um tenant.
 *  Inclui a senha para que credenciais diferentes nunca compartilhem token. */
function tenantKey(creds: MetabooksCredentials): string {
  return createHash("sha256")
    .update(`${creds.baseUrl}|${creds.username ?? ""}|${creds.password ?? ""}`)
    .digest("hex");
}

/** Faz POST /login e retorna o accessToken (string). */
async function performLogin(creds: MetabooksCredentials): Promise<string> {
  if (!creds.username || !creds.password) {
    throw new MetabooksError("Login requer usuário e senha.");
  }
  try {
    const response = await axios({
      method: "POST",
      url: `${creds.baseUrl}/login`,
      data: { username: creds.username, password: creds.password },
      timeout: REQUEST_TIMEOUT,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      maxRedirects: 5,
    });
    const data = response.data;
    let token: string | undefined;
    if (typeof data === "string") {
      token = data.trim();
    } else if (data && typeof data === "object") {
      token = (data.accessToken || data.access_token || data.token || "").toString().trim();
    }
    if (!token) {
      throw new MetabooksError(
        "Login bem-sucedido, mas não foi possível extrair o accessToken da resposta."
      );
    }
    return token;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      throw new MetabooksError(
        "Falha no login: credenciais inválidas. Verifique usuário/senha (headers " +
          "X-Metabooks-Username / X-Metabooks-Password ou as variáveis de ambiente)."
      );
    }
    if (error instanceof MetabooksError) throw error;
    throw error;
  }
}

/**
 * Obtém um token de metadados válido para o tenant atual. Prioriza:
 *  1. token estático (metadataToken);
 *  2. token de login em cache (se válido);
 *  3. novo login.
 */
async function getMetadataToken(creds: MetabooksCredentials, forceRefresh = false): Promise<string> {
  if (creds.metadataToken && !forceRefresh) {
    return creds.metadataToken;
  }

  if (!creds.username || !creds.password) {
    if (creds.metadataToken) return creds.metadataToken;
    throw new MetabooksError(
      "Sem credenciais de metadados. Envie X-Metabooks-Username/X-Metabooks-Password " +
        "(login, produção) ou X-Metabooks-Metadata-Token (staging/rc) — ou configure as " +
        "variáveis de ambiente equivalentes."
    );
  }

  const key = tenantKey(creds);
  const now = Date.now();
  if (!forceRefresh) {
    const cached = tokenCache.get(key);
    if (cached && cached.expiresAt > now) return cached.token;
  }

  const token = await performLogin(creds);
  tokenCache.set(key, { token, expiresAt: now + TOKEN_TTL_MS });
  return token;
}

/** Invalida o cache de login do tenant (após 401). */
function invalidateMetadataToken(creds: MetabooksCredentials): void {
  tokenCache.delete(tenantKey(creds));
}

/** Recupera o token de cover/mmo do tenant, ou lança erro orientativo. */
function staticTokenForScope(
  creds: MetabooksCredentials,
  scope: TokenScope.COVER | TokenScope.MMO
): string {
  const token = scope === TokenScope.COVER ? creds.coverToken : creds.mmoToken;
  if (!token) {
    const headerName =
      scope === TokenScope.COVER ? "X-Metabooks-Cover-Token" : "X-Metabooks-Mmo-Token";
    throw new MetabooksError(
      `Token de '${scope}' não fornecido. Envie o header ${headerName} (ou a variável de ambiente). ` +
        "Capas e mídia exigem tokens dedicados — login/metadados NÃO os acessa (seção 5.5.5)."
    );
  }
  return token;
}

/**
 * Faz uma requisição autenticada à API usando as credenciais do tenant atual.
 */
export async function metabooksRequest<T = unknown>(
  path: string,
  scope: TokenScope,
  options: {
    method?: "GET" | "POST";
    params?: Record<string, unknown>;
    data?: unknown;
    accept?: string;
    contentType?: string;
    responseType?: AxiosRequestConfig["responseType"];
  } = {}
): Promise<T> {
  const creds = currentCredentials();
  const url = `${creds.baseUrl}/${path.replace(/^\/+/, "")}`;
  const accept = options.accept ?? "application/json";

  const doRequest = async (token: string): Promise<T> => {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: accept,
    };
    if (options.contentType) headers["Content-Type"] = options.contentType;

    const config: AxiosRequestConfig = {
      method: options.method ?? "GET",
      url,
      headers,
      params: options.params,
      data: options.data,
      timeout: REQUEST_TIMEOUT,
      responseType: options.responseType ?? "json",
      maxRedirects: 5,
    };
    const response = await axios(config);
    return response.data as T;
  };

  // Cover/MMO: token estático direto.
  if (scope === TokenScope.COVER || scope === TokenScope.MMO) {
    return doRequest(staticTokenForScope(creds, scope));
  }

  // Metadados: token estático OU login com renovação automática.
  let token = await getMetadataToken(creds, false);
  try {
    return await doRequest(token);
  } catch (error) {
    const is401 = axios.isAxiosError(error) && error.response?.status === 401;
    const body = axios.isAxiosError(error)
      ? (error.response?.data as ApiErrorBody | undefined)
      : undefined;
    const isInvalidToken = body?.error === "invalid_token";
    const usingLogin = !!creds.username && !!creds.password && !creds.metadataToken;

    if ((is401 || isInvalidToken) && usingLogin) {
      invalidateMetadataToken(creds);
      token = await getMetadataToken(creds, true);
      return await doRequest(token);
    }
    throw error;
  }
}

/** Indica se o tenant atual tem token de cover configurado. */
export function hasCoverToken(): boolean {
  return !!currentCredentials().coverToken;
}

/** Base URL do tenant atual (para montar URLs de capa). */
export function currentBaseUrl(): string {
  return currentCredentials().baseUrl;
}

/**
 * Converte qualquer erro em mensagem acionável em português, mapeando os
 * códigos HTTP e os error codes JSON da Metabooks.
 */
export function handleApiError(error: unknown, context?: string): string {
  const prefix = context ? `Erro ao ${context}: ` : "Erro: ";

  if (error instanceof MetabooksError) {
    return prefix + error.message;
  }

  if (axios.isAxiosError(error)) {
    const axErr = error as AxiosError<ApiErrorBody>;

    if (axErr.response) {
      const status = axErr.response.status;
      const body = axErr.response.data;
      const apiCode = body?.error;
      const apiDesc = body?.error_description;

      const codeHints: Record<string, string> = {
        invalid_token:
          "Token inválido ou expirado. Se usa login, tente novamente; se usa token estático, verifique-o.",
        unauthorized:
          "Não autorizado. Credenciais incorretas ou o token não tem permissão para este recurso.",
        access_denied:
          "Acesso negado. O token não tem permissão para este dado (ex.: capas exigem token de cover).",
        no_permission: "Permissão insuficiente para o nível do token/login fornecido.",
        not_found: "Produto/recurso indisponível.",
        product_blocked: "Produto somente para exibição (read-only), não pode ser recuperado.",
        not_acceptable:
          "Formato não aceitável. Verifique os cabeçalhos Accept/Content-Type para o endpoint.",
        forbidden: "O token/acesso não está autorizado a acessar este dado.",
      };

      const statusHints: Record<number, string> = {
        400: "Requisição malformada. Revise os parâmetros enviados.",
        401: "Não autorizado (401). Login/token ausente, inválido ou expirado.",
        403: "Proibido (403). O token não tem permissão para este recurso.",
        404: "Não encontrado (404). Verifique o ISBN/GTIN/UUID/ID informado.",
        406: "Formato não aceitável (406). Ajuste o cabeçalho Accept.",
        500: "Erro interno do servidor Metabooks (500). Tente novamente mais tarde.",
        503: "Serviço temporariamente indisponível (503). Tente novamente mais tarde.",
      };

      let msg = prefix;
      if (apiCode && codeHints[apiCode]) {
        msg += codeHints[apiCode];
      } else if (statusHints[status]) {
        msg += statusHints[status];
      } else {
        msg += `A API retornou status ${status}.`;
      }
      if (apiDesc) msg += ` (detalhe: ${apiDesc})`;
      return msg;
    }

    if (axErr.code === "ECONNABORTED") {
      return prefix + "tempo de requisição esgotado. Tente novamente.";
    }
    if (axErr.code === "ENOTFOUND" || axErr.code === "ECONNREFUSED") {
      return (
        prefix +
        "não foi possível conectar à API. Verifique a URL base " +
        "(produção, staging ou rc) e a conectividade de rede."
      );
    }
    return prefix + `falha de rede (${axErr.code ?? "desconhecida"}).`;
  }

  return prefix + (error instanceof Error ? error.message : String(error));
}
