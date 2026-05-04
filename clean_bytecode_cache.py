#!/usr/bin/env python3
"""Remove bytecode caches and common ephemeral build/test artifacts (repo-root entry).

Canonical implementation: :mod:`scripts.dev.clean_bytecode_cache`.
"""

from __future__ import annotations

import sys

from scripts.dev.clean_bytecode_cache import clean_bytecode_cache, main

__all__ = ["clean_bytecode_cache", "main"]

if __name__ == "__main__":
    sys.exit(main())
