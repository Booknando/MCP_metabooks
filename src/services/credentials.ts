/**
 * Contexto de credenciais por requisição (multi-tenant).
 *
 * Cada editora configura, no seu conector MCP, headers HTTP com as próprias
 * credenciais Metabooks. Cada requisição POST /mcp roda dentro de um
 * AsyncLocalStorage que carrega essas credenciais, de modo que o cliente HTTP
 * (services/client.ts) use sempre as credenciais daquela editora — sem
 * vazamento entre requisições concorrentes.
 *
 * Headers aceitos (case-insensitive):
 *   X-Metabooks-Username        \  login (produção)
 *   X-Metabooks-Password        /
 *   X-Metabooks-Metadata-Token  -> token estático de metadados (staging/rc)
 *   X-Metabooks-Cover-Token     -> token de capas (opcional)
 *   X-Metabooks-Mmo-Token       -> token de mídia/MMO (opcional)
 *   X-Metabooks-Base-Url        -> sobrescreve a URL base (opcional)
 *
 * Fallback: se um header não vier, usa-se a variável de ambiente equivalente.
 * Assim o servidor funciona tanto em modo single-tenant (env) quanto
 * multi-tenant (headers por editora).
 */

import { AsyncLocalStorage } from "node:async_hooks";
import type { Request } from "express";
import { DEFAULT_BASE_URL } from "../constants.js";

/** Credenciais efetivas de uma requisição. */
export interface MetabooksCredentials {
  baseUrl: string;
  username?: string;
  password?: string;
  metadataToken?: string;
  coverToken?: string;
  mmoToken?: string;
}

const storage = new AsyncLocalStorage<MetabooksCredentials>();

/** Lê um header (case-insensitive) e retorna trimmed ou undefined. */
function header(req: Request, name: string): string | undefined {
  const v = req.header(name);
  if (Array.isArray(v)) return v[0]?.trim() || undefined;
  return v?.trim() || undefined;
}

/**
 * Monta as credenciais de uma requisição a partir dos headers, com fallback
 * para as variáveis de ambiente.
 */
export function credentialsFromRequest(req: Request): MetabooksCredentials {
  const baseUrl =
    header(req, "x-metabooks-base-url") ||
    process.env.METABOOKS_BASE_URL?.trim() ||
    DEFAULT_BASE_URL;

  return {
    baseUrl: baseUrl.replace(/\/+$/, ""),
    username: header(req, "x-metabooks-username") || process.env.METABOOKS_USERNAME?.trim() || undefined,
    password:
      req.header("x-metabooks-password") /* senha pode ter espaços */ ||
      process.env.METABOOKS_PASSWORD ||
      undefined,
    metadataToken:
      header(req, "x-metabooks-metadata-token") ||
      process.env.METABOOKS_METADATA_TOKEN?.trim() ||
      undefined,
    coverToken:
      header(req, "x-metabooks-cover-token") || process.env.METABOOKS_COVER_TOKEN?.trim() || undefined,
    mmoToken:
      header(req, "x-metabooks-mmo-token") || process.env.METABOOKS_MMO_TOKEN?.trim() || undefined,
  };
}

/** Executa `fn` com as credenciais da requisição no contexto. */
export function runWithCredentials<T>(creds: MetabooksCredentials, fn: () => T): T {
  return storage.run(creds, fn);
}

/**
 * Recupera as credenciais do contexto atual. Se não houver contexto (ex.: modo
 * stdio), cai para as variáveis de ambiente.
 */
export function currentCredentials(): MetabooksCredentials {
  const ctx = storage.getStore();
  if (ctx) return ctx;
  // Fallback para stdio / chamadas fora de requisição HTTP.
  const baseUrl = (process.env.METABOOKS_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(/\/+$/, "");
  return {
    baseUrl,
    username: process.env.METABOOKS_USERNAME?.trim() || undefined,
    password: process.env.METABOOKS_PASSWORD || undefined,
    metadataToken: process.env.METABOOKS_METADATA_TOKEN?.trim() || undefined,
    coverToken: process.env.METABOOKS_COVER_TOKEN?.trim() || undefined,
    mmoToken: process.env.METABOOKS_MMO_TOKEN?.trim() || undefined,
  };
}

/**
 * Indica se há ao menos uma forma de obter metadados (login ou token estático),
 * considerando o ambiente. Usado para validar a inicialização em modo single-tenant.
 */
export function envHasMetadataAuth(): boolean {
  const hasLogin = !!process.env.METABOOKS_USERNAME?.trim() && !!process.env.METABOOKS_PASSWORD;
  const hasToken = !!process.env.METABOOKS_METADATA_TOKEN?.trim();
  return hasLogin || hasToken;
}
