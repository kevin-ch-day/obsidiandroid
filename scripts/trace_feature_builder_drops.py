#!/usr/bin/env python3
"""Compatibility wrapper for ``scripts.diagnostics.trace_feature_builder_drops``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.diagnostics.trace_feature_builder_drops import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
