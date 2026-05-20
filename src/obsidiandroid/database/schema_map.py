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
    "family_alias_fact": "malware_family_alias_fact",
    "family_authority_fact": "malware_family_authority_fact",
    "family_label_evidence": "malware_family_label_evidence",
    "vendor_label_generic_tokens": "vendor_label_generic_token_fact",
    "av_engine_dependency_fact": "av_engine_dependency_fact",
    "sample_temporal_resolved_view": "v_android_sample_temporal_resolved",
    "label_authority_resolution_view": "label_authority_resolution_view",
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
