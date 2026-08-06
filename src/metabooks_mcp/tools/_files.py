"""Utilitários compartilhados de arquivo para as tools (capas, mídia).

Modelo de ameaça
----------------
O ``dest`` destas tools é escolhido pelo MODELO, e o contexto do modelo é
alimentado por conteúdo da API (título, sinopse, nome de mídia) que terceiros
editam. Sem confinamento, uma injeção de prompt consegue induzir a gravação
sobre arquivos sensíveis do usuário — inclusive o ``claude_desktop_config.json``,
onde ficam as credenciais Metabooks.

Por isso a gravação é limitada a raízes permitidas (por padrão ``~/Downloads``,
ajustável em ``METABOOKS_DOWNLOAD_DIR``), nomes de arquivo são higienizados, a
extensão é forçada para o tipo real do conteúdo e sobrescrever exige pedido
explícito.
"""

import os
import re
import tempfile

ENV_DOWNLOAD_DIR = "METABOOKS_DOWNLOAD_DIR"

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class DestinationError(Exception):
    """Destino de gravação recusado (fora das raízes permitidas, já existe…)."""


def allowed_roots() -> list[str]:
    """Raízes onde a gravação é permitida.

    ``METABOOKS_DOWNLOAD_DIR`` aceita uma ou mais pastas separadas pelo
    separador de path do sistema (``:`` no Unix, ``;`` no Windows); é o ponto
    de ajuste para quem precisa salvar fora de ``~/Downloads``.
    """
    raw = os.environ.get(ENV_DOWNLOAD_DIR, "").strip()
    if raw:
        roots = [
            os.path.abspath(os.path.expanduser(part))
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
        if roots:
            return roots
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        return [os.path.abspath(downloads)]
    return [os.path.abspath(os.path.join(tempfile.gettempdir(), "metabooks-mcp"))]


def default_download_dir() -> str:
    """Pasta padrão para salvar arquivos (primeira raiz permitida)."""
    return allowed_roots()[0]


def safe_filename(name: str, fallback: str = "arquivo") -> str:
    """Higieniza um nome de arquivo: sem separadores de path, sem surpresas."""
    name = os.path.basename(str(name or "")).strip()
    name = _SAFE_CHARS.sub("_", name).strip("._-")
    return name or fallback


def _real_prefix(path: str) -> str:
    """Resolve symlinks do trecho JÁ EXISTENTE do caminho.

    Impede que um symlink dentro da raiz permitida (``~/Downloads/x -> /etc``)
    sirva de ponte para fora dela.
    """
    path = os.path.abspath(path)
    head = path
    tail: list[str] = []
    while head and not os.path.exists(head):
        head, part = os.path.split(head)
        if not part:
            break
        tail.append(part)
    return os.path.join(os.path.realpath(head or os.sep), *reversed(tail))


def _is_within(root: str, target: str) -> bool:
    root = os.path.realpath(root) if os.path.exists(root) else os.path.abspath(root)
    try:
        return os.path.commonpath([root, target]) == root
    except ValueError:  # discos diferentes no Windows
        return False


def resolve_target(
    dest: str | None,
    filename: str,
    *,
    expected_ext: str | None = None,
    overwrite: bool = False,
) -> str:
    """Resolve — e valida — o caminho de destino de um download.

    - ``dest`` None  → ``default_download_dir()/filename``
    - ``dest`` pasta → ``dest/filename`` (existente, terminada em separador ou sem extensão)
    - ``dest`` arquivo com extensão → usado como está, com o nome higienizado

    A extensão é forçada para ``expected_ext`` quando informada, para que um
    JPEG/PDF nunca seja gravado sobre um ``.json``, ``.py`` ou ``.bashrc``.

    Levanta ``DestinationError`` se o caminho final cair fora das raízes
    permitidas ou se o arquivo já existir sem ``overwrite=True``.
    """
    filename = safe_filename(filename)
    roots = allowed_roots()

    if dest is None:
        target = os.path.join(roots[0], filename)
    else:
        expanded = os.path.expanduser(str(dest))
        as_path = os.path.abspath(expanded)
        looks_like_dir = (
            os.path.isdir(as_path)
            or expanded.endswith(("/", "\\"))
            or not os.path.splitext(as_path)[1]
        )
        if looks_like_dir:
            target = os.path.join(as_path, filename)
        else:
            target = os.path.join(
                os.path.dirname(as_path), safe_filename(os.path.basename(as_path), filename)
            )

    if expected_ext:
        want = "." + expected_ext.lstrip(".").lower()
        if os.path.splitext(target)[1].lower() != want:
            target += want

    target = _real_prefix(target)
    if not any(_is_within(root, target) for root in roots):
        raise DestinationError(
            f"Destino fora das pastas permitidas: {target}. "
            f"Permitidas: {os.pathsep.join(roots)}. "
            f"Para liberar outra pasta, defina {ENV_DOWNLOAD_DIR} na configuração do servidor."
        )
    if os.path.exists(target) and not overwrite:
        raise DestinationError(
            f"O arquivo já existe: {target}. Peça overwrite=true para substituí-lo."
        )
    return target
