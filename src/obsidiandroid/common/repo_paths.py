"""Repository layout helpers for running from a source checkout without editable install."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_src_on_sys_path() -> None:
    """Prepend ``<repo>/src`` when this module lives under that tree.

    Resolves the ``src`` directory from ``.../src/obsidiandroid/common/repo_paths.py``
    and prepends it to ``sys.path`` if missing. No-ops when the package is installed
    under ``site-packages`` (parent of ``obsidiandroid`` is not named ``src``).
    """
    here = Path(__file__).resolve()
    if len(here.parents) < 3:
        return
    src_root = here.parents[2]
    if src_root.name != "src":
        return
    if src_root.is_dir() and str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


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
