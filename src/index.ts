#!/usr/bin/env node
/**
 * Servidor MCP (somente leitura) para a API REST v2 da Metabooks — MULTI-TENANT.
 *
 * Cada editora configura, no seu conector MCP, headers HTTP com as próprias
 * credenciais Metabooks. O servidor usa essas credenciais por requisição,
 * isoladas via AsyncLocalStorage. Há fallback para variáveis de ambiente
 * (modo single-tenant), útil para testes.
 *
 * Transportes:
 *  - HTTP (Streamable HTTP, stateless) — recomendado para rodar online (padrão).
 *  - stdio — uso local/desktop (usa credenciais do ambiente).
 *
 * Headers de credenciais Metabooks (por requisição):
 *  - X-Metabooks-Username / X-Metabooks-Password   (login, produção)
 *  - X-Metabooks-Metadata-Token                    (token estático, staging/rc)
 *  - X-Metabooks-Cover-Token                       (capas, opcional)
 *  - X-Metabooks-Mmo-Token                         (mídia/MMO, opcional)
 *  - X-Metabooks-Base-Url                          (sobrescreve a URL base)
 *
 * Variáveis de ambiente:
 *  - METABOOKS_* (fallback single-tenant: USERNAME, PASSWORD, METADATA_TOKEN,
 *    COVER_TOKEN, MMO_TOKEN, BASE_URL)
 *  - REQUIRE_TENANT_CREDENTIALS=true  -> exige que as credenciais venham por
 *    header (recomendado em produção multi-tenant; não usa fallback de ambiente
 *    para metadados).
 *  - MCP_AUTH_TOKEN  -> protege o endpoint /mcp (gateway). Recomendado online.
 *  - PORT (padrão 3000), TRANSPORT ('http' | 'stdio', padrão 'http')
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import express, { type Request, type Response } from "express";
import { registerTools } from "./tools/index.js";
import { DEFAULT_BASE_URL } from "./constants.js";
import {
  credentialsFromRequest,
  envHasMetadataAuth,
  runWithCredentials,
  type MetabooksCredentials,
} from "./services/credentials.js";

const SERVER_NAME = "metabooks-mcp-server";
const SERVER_VERSION = "2.0.0";

function isMultiTenantRequired(): boolean {
  return (process.env.REQUIRE_TENANT_CREDENTIALS || "").toLowerCase() === "true";
}

function createServer(): McpServer {
  const server = new McpServer({ name: SERVER_NAME, version: SERVER_VERSION });
  registerTools(server);
  return server;
}

/** Valida o token de proteção do endpoint MCP, se configurado. */
function checkGatewayAuth(req: Request): boolean {
  const expected = process.env.MCP_AUTH_TOKEN?.trim();
  if (!expected) return true;
  const header = req.header("authorization") ?? "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return !!match && match[1] === expected;
}

/** Verifica se a requisição traz credenciais de metadados (login ou token). */
function requestHasMetadataAuth(creds: MetabooksCredentials): boolean {
  return (!!creds.username && !!creds.password) || !!creds.metadataToken;
}

async function runHTTP(): Promise<void> {
  const multiTenant = isMultiTenantRequired();
  if (!multiTenant && !envHasMetadataAuth()) {
    // Em modo single-tenant, exige credenciais no ambiente.
    throw new Error(
      "Sem credenciais de metadados no ambiente. Em produção, defina " +
        "METABOOKS_USERNAME e METABOOKS_PASSWORD; em staging/rc, METABOOKS_METADATA_TOKEN. " +
        "Para modo multi-tenant (credenciais por editora via header), defina " +
        "REQUIRE_TENANT_CREDENTIALS=true."
    );
  }

  const app = express();
  app.use(express.json({ limit: "2mb" }));

  app.get("/health", (_req: Request, res: Response) => {
    res.json({
      status: "ok",
      server: SERVER_NAME,
      version: SERVER_VERSION,
      mode: multiTenant ? "multi-tenant" : "single-tenant",
      default_base_url: process.env.METABOOKS_BASE_URL?.trim() || DEFAULT_BASE_URL,
    });
  });

  app.post("/mcp", async (req: Request, res: Response) => {
    if (!checkGatewayAuth(req)) {
      res.status(401).json({
        jsonrpc: "2.0",
        error: { code: -32001, message: "Não autorizado: token de acesso ao MCP inválido." },
        id: null,
      });
      return;
    }

    const creds = credentialsFromRequest(req);

    // Em modo multi-tenant, exige credenciais de metadados na própria requisição.
    if (multiTenant && !requestHasMetadataAuth(creds)) {
      res.status(401).json({
        jsonrpc: "2.0",
        error: {
          code: -32002,
          message:
            "Credenciais Metabooks ausentes. Envie X-Metabooks-Username/X-Metabooks-Password " +
            "(produção) ou X-Metabooks-Metadata-Token (staging/rc) nos headers do conector.",
        },
        id: null,
      });
      return;
    }

    try {
      const server = createServer();
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true,
      });
      res.on("close", () => {
        transport.close();
        server.close();
      });
      await server.connect(transport);
      // Executa o processamento da requisição dentro do contexto de credenciais.
      await runWithCredentials(creds, () => transport.handleRequest(req, res, req.body));
    } catch (error) {
      console.error("Erro ao processar requisição MCP:", error);
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: "2.0",
          error: { code: -32603, message: "Erro interno do servidor MCP." },
          id: null,
        });
      }
    }
  });

  const notAllowed = (_req: Request, res: Response) => {
    res.status(405).json({
      jsonrpc: "2.0",
      error: { code: -32000, message: "Método não permitido. Use POST em /mcp." },
      id: null,
    });
  };
  app.get("/mcp", notAllowed);
  app.delete("/mcp", notAllowed);

  const port = parseInt(process.env.PORT || "3000", 10);
  app.listen(port, "0.0.0.0", () => {
    console.error(
      `${SERVER_NAME} v${SERVER_VERSION} (${multiTenant ? "multi-tenant" : "single-tenant"}) ` +
        `rodando em http://0.0.0.0:${port}/mcp`
    );
    console.error(`Healthcheck: http://0.0.0.0:${port}/health`);
  });
}

async function runStdio(): Promise<void> {
  if (!envHasMetadataAuth()) {
    throw new Error(
      "Modo stdio requer credenciais no ambiente: METABOOKS_USERNAME/METABOOKS_PASSWORD " +
        "ou METABOOKS_METADATA_TOKEN."
    );
  }
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`${SERVER_NAME} v${SERVER_VERSION} rodando via stdio`);
}

const transport = (process.env.TRANSPORT || "http").toLowerCase();
const main = transport === "stdio" ? runStdio : runHTTP;

main().catch((error) => {
  console.error("Falha ao iniciar o servidor:", error instanceof Error ? error.message : error);
  process.exit(1);
});
