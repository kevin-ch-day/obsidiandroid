#!/usr/bin/env python3
"""Static scan for suspicious ``.predict()`` / ``.predict_proba()`` call sites (repo-root entry).

Canonical implementation: :mod:`scripts.dev.run_ml_static_scan`.
"""

from __future__ import annotations

import sys

from scripts.dev.run_ml_static_scan import main

__all__ = ["main"]

if __name__ == "__main__":
    sys.exit(main())
