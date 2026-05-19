# Filename: src/obsidiandroid/database/schema_map.py
"""Database schema compatibility map for ObsidianDroid.

Centralizes logical-to-physical table/column mappings so schema migrations
can be handled in one place.

Canonical implementation; the repo-root ``database.schema_map`` shim has been retired.
"""

from __future__ import annotations

from .db_config import DB_NAME

TABLES = {
    "vendor_engines": "virustotal_vendor_engines",
    "vendor_verdicts": "virustotal_sample_vendor_engine_verdicts",
    "sample_catalog": "malware_sample_catalog",
    "artifact_hashes": "malware_artifact_hash_registry",
}


COLUMNS = {
    "vendor_engines": {
        "engine_name": "vendor_key",
        "trusted_flag": "is_trusted_vendor",
        "active_flag": "is_engine_active",
    },
    "vendor_verdicts": {
        "sample_id": "sample_id",
        "updated_at": "updated_at",
    },
}


def table(name: str) -> str:
    """Resolve logical table name to physical table name."""
    return TABLES.get(name, name)


def column(table_name: str, logical_column: str) -> str:
    """Resolve logical column name to physical column name."""
    return COLUMNS.get(table_name, {}).get(logical_column, logical_column)


def current_schema() -> str:
    """Return current active database/schema name."""
    return DB_NAME
