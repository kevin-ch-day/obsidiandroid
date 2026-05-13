# Filename: src/obsidiandroid/database/split_db_health.py
"""CLI entry for split-database connectivity checks (canonical implementation).

The documented ``python -m database.split_db_health`` path is a small legacy
wrapper that registers this module under ``database.split_db_health`` and runs
the CLI when executed as ``__main__``.
"""

from __future__ import annotations

from .db_engine import split_database_health_cli

__all__ = ["split_database_health_cli"]
