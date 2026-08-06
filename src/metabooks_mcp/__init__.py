"""Metabooks MCP Server — acesso somente leitura à API REST v2 da Metabooks."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("metabooks-mcp")
except PackageNotFoundError:  # execução direta da árvore de código, sem instalar
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
