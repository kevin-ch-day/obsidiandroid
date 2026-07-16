# Filename: src/obsidiandroid/database/split_db_health.py
"""CLI entry for split-database connectivity checks."""

from __future__ import annotations

import sys

from .db_engine import split_database_health_cli

__all__ = ["split_database_health_cli"]


if __name__ == "__main__":
    raise SystemExit(split_database_health_cli())
