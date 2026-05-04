"""Ensure repository ``src/`` is on ``sys.path`` when running from a checkout.

Bootstrap order: this module lives outside ``src/``, so it prepends ``./src`` once,
then delegates to :func:`obsidiandroid.common.repo_paths.ensure_repo_src_on_sys_path`
for the canonical check (idempotent).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()
