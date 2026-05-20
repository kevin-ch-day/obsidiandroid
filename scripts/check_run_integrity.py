#!/usr/bin/env python3
"""Compatibility wrapper for ``scripts.diagnostics.check_run_integrity``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.diagnostics.check_run_integrity as _impl  # noqa: E402

_as_float = _impl._as_float
_as_int = _impl._as_int
_close = _impl._close
_load_json = _impl._load_json
compare_run_artifacts = _impl.compare_run_artifacts
main = _impl.main
resolve_default_paths = _impl.resolve_default_paths

__all__ = [
    "_as_float",
    "_as_int",
    "_close",
    "_load_json",
    "compare_run_artifacts",
    "main",
    "resolve_default_paths",
]


if __name__ == "__main__":
    raise SystemExit(main())
