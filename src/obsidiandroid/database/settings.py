# Filename: src/obsidiandroid/database/settings.py
"""Structured database configuration (single place for scripts and health checks).

Values mirror canonical ``obsidiandroid.database.db_config`` after optional ``.env`` loading; use this module
when you want explicit fields instead of importing raw module constants.

Canonical implementation; the repo-root ``database.settings`` shim has been retired.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import db_config


@dataclass(frozen=True, slots=True)
class ObsidianConnectionSettings:
    """MySQL connection parameters for the primary and Permission Intel databases."""

    host: str
    port: int
    user: str
    password: str
    database: str
    permission_intel_database: str
    core_database_host: str
    core_database_port: int
    core_database_user: str
    core_database_password: str
    core_database: str
    charset: str


def load_connection_settings() -> ObsidianConnectionSettings:
    """Return current settings from ``db_config`` (reflects env / dotenv)."""
    return ObsidianConnectionSettings(
        host=str(db_config.DB_HOST),
        port=int(db_config.DB_PORT),
        user=str(db_config.DB_USER),
        password=str(db_config.DB_PASSWORD),
        database=str(db_config.DB_NAME),
        permission_intel_database=str(db_config.PERMISSION_INTEL_DB_NAME),
        core_database_host=str(db_config.CORE_DB_HOST),
        core_database_port=int(db_config.CORE_DB_PORT),
        core_database_user=str(db_config.CORE_DB_USER),
        core_database_password=str(db_config.CORE_DB_PASSWORD),
        core_database=str(db_config.CORE_DB_NAME),
        charset=str(db_config.DB_CHARSET),
    )
