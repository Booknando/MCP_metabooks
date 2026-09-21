"""Erros de execução visíveis no protocolo, sem ecoar tokens ou URLs sensíveis."""

import json
from functools import wraps

import httpx
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from ..client import MetabooksError
from ._files import DestinationError, allowed_roots

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                            idempotentHint=True, openWorldHint=True)
DOWNLOAD = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                           idempotentHint=False, openWorldHint=True)


def error_result(payload: dict) -> CallToolResult:
    return CallToolResult(isError=True, content=[
        TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
    ])


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        messages = {
            401: "Autenticação recusada. Confira as credenciais ou renove o token.",
            403: "Acesso negado. Confira o token e a permissão para este serviço.",
            404: "Recurso não encontrado. Confira o identificador informado.",
            429: "Limite de requisições atingido. Aguarde antes de tentar novamente.",
        }
        return f"HTTP {code}: " + messages.get(code, "A API não pôde concluir a solicitação.")
    if isinstance(exc, httpx.TimeoutException):
        return "A API demorou para responder. Tente novamente mais tarde."
    if isinstance(exc, httpx.TransportError):
        return "Falha de conexão com a API. Confira a rede e tente novamente."
    if isinstance(exc, (MetabooksError, DestinationError)):
        return str(exc)
    if isinstance(exc, OSError):
        return "Não foi possível acessar o arquivo. Confira a pasta, permissões e espaço em disco."
    if isinstance(exc, ValueError):
        return "Resposta ou arquivo inválido recebido da API."
    return "Não foi possível concluir a operação. Consulte o diagnóstico do servidor."


def tool_errors(func):
    """Preserva assinatura/schema e transforma erros de negócio em isError=true."""
    @wraps(func)
    async def wrapped(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
        except DestinationError as exc:
            return error_result({"error": friendly_error(exc), "pastas_permitidas": allowed_roots()})
        except Exception as exc:
            return error_result({"error": friendly_error(exc)})
        if isinstance(result, dict) and "error" in result:
            return error_result(result)
        if isinstance(result, dict):
            return CallToolResult(structuredContent=result, content=[
                TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
            ])
        return result
    return wrapped
