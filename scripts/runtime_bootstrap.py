"""Shared ``sys.path`` setup for repository ``scripts/`` entrypoints.

``python scripts/<tool>.py`` puts only the ``scripts/`` directory on ``sys.path`` first.
Callers insert the repository root so ``import config`` and ``import scripts…`` resolve.
This module prepends ``<repo>/src`` when that directory exists so **checkouts without an
editable install** can ``import obsidiandroid`` before :func:`ensure_repo_src_on_sys_path`
runs (which is a no-op when the package is not under a ``src/`` tree).

Import **after** the repository root is on ``sys.path``:

``import scripts.runtime_bootstrap  # noqa: F401``
"""

from __future__ import annotations

import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
_repo_root = _scripts_dir.parent
_src = _repo_root / "src"

for _p in (_src, _repo_root):
    if _p is _src and not _p.is_dir():
        continue
    _s = str(_p.resolve())
    if _s not in sys.path:
        sys.path.insert(0, _s)
