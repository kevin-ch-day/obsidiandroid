"""Shared helpers: paths, manifests, profiles, logging, exports, and CLI glue.

Import concrete modules explicitly (e.g. ``from utils import runtime_paths``) to keep
startup cost predictable; this package does not re-export everything by default.

Checkout bootstrap (Pass 102): the first ``import utils`` prepends ``<repo>/src`` when
that directory exists, then calls
:func:`obsidiandroid.common.repo_paths.ensure_repo_src_on_sys_path`.
Leaf ``utils/*.py`` shims do not duplicate this logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path  # noqa: E402

ensure_repo_src_on_sys_path()

__all__: list[str] = []
