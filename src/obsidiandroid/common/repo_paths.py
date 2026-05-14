"""Repository layout helpers for running from a source checkout without editable install."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_src_on_sys_path() -> Path | None:
    """Prepend ``<repo>/src`` when this module lives under that tree.

    Resolves the ``src`` directory from ``.../src/obsidiandroid/common/repo_paths.py``
    and prepends it to ``sys.path`` if missing. No-ops when the package is installed
    under ``site-packages`` (parent of ``obsidiandroid`` is not named ``src``).

    Returns the resolved ``<repo>/src`` path when detectable, otherwise ``None``.
    """
    here = Path(__file__).resolve()
    if len(here.parents) < 3:
        return None
    src_root = here.parents[2]
    if src_root.name != "src":
        return None
    if not src_root.is_dir():
        return None
    src_str = str(src_root)
    # Ensure idempotence even if callers inserted duplicates earlier.
    while sys.path.count(src_str) > 1:
        sys.path.remove(src_str)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    return src_root


def repo_root() -> Path:
    """Return the repository root for assets like ``profiles/`` and ``config/``.

    When this file lives at ``<repo>/src/obsidiandroid/common/repo_paths.py``,
    returns ``<repo>``. If the on-disk layout does not match (e.g. some installs),
    falls back to :func:`Path.cwd`.
    """
    here = Path(__file__).resolve()
    if len(here.parents) < 4:
        return Path.cwd()
    if here.parents[1].name == "obsidiandroid" and here.parents[2].name == "src":
        return here.parents[3]
    return Path.cwd()


def repo_operator_script(*relative_under_scripts: str) -> Path:
    """Return ``<repo>/scripts/<parts>`` for repo-root operator CLIs.

    Prefer this over ``Path("scripts/...")`` so subprocess launches work when
    :func:`os.getcwd` is not the repository root (menus, IDEs, wrappers).
    """
    return (repo_root() / "scripts").joinpath(*relative_under_scripts)
