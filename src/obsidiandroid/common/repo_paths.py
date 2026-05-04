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
