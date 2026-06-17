"""Utilitários compartilhados de arquivo para as tools (capas, mídia)."""

import os
import tempfile


def default_download_dir() -> str:
    """Pasta padrão para salvar arquivos: ~/Downloads (se existir) ou pasta temp."""
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else tempfile.gettempdir()


def resolve_target(dest: str | None, filename: str) -> str:
    """Resolve o caminho de destino de um download.

    - ``dest`` None  → ``default_download_dir()/filename``
    - ``dest`` pasta → ``dest/filename`` (existente ou terminada em separador)
    - ``dest`` arquivo com extensão → usado como está
    - ``dest`` sem extensão → tratado como pasta
    """
    if dest is None:
        return os.path.abspath(os.path.join(default_download_dir(), filename))
    dest = os.path.expanduser(dest)
    if os.path.isdir(dest) or dest.endswith(("/", "\\")):
        target = os.path.join(dest, filename)
    elif os.path.splitext(dest)[1]:
        target = dest
    else:
        target = os.path.join(dest, filename)
    return os.path.abspath(target)
