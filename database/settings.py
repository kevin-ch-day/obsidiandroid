"""Structured database configuration (single place for scripts and health checks).

Values mirror ``database.db_config`` after optional ``.env`` loading; use this module
when you want explicit fields instead of importing raw module constants.
"""

from __future__ import annotations

from dataclasses import dataclass

from database import db_config


@dataclass(frozen=True, slots=True)
class ObsidianConnectionSettings:
    """MySQL connection parameters for the primary and Permission Intel databases."""

    host: str
    port: int
    user: str
    password: str
    database: str
    permission_intel_database: str
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
        charset=str(db_config.DB_CHARSET),
    )
