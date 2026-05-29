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
    "android_sample_family_type_authority_view": "v_android_sample_family_type_authority",
    "android_missing_resolution_triage_view": "v_android_missing_resolution_triage",
    "vt_false_positive_review_effective_view": "v_vt_false_positive_review_candidates_effective",
    "vt_false_positive_review_triage_view": "v_vt_false_positive_review_candidates_triage",
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

COMPATIBLE_COLUMNS = {
    "vendor_label_generic_tokens": {
        "active_flag": ("is_active", "active_flag"),
    },
}


def table(name: str) -> str:
    """Resolve logical table name to physical table name."""
    return TABLES.get(name, name)


def column(table_name: str, logical_column: str) -> str:
    """Resolve logical column name to physical column name."""
    return COLUMNS.get(table_name, {}).get(logical_column, logical_column)


def compatible_columns(table_name: str, logical_column: str) -> tuple[str, ...]:
    """Return canonical-first compatible physical columns for a logical column."""
    configured = COMPATIBLE_COLUMNS.get(table_name, {}).get(logical_column)
    if configured:
        return tuple(configured)
    return (column(table_name, logical_column),)


def resolve_existing_column(
    table_name: str,
    logical_column: str,
    available_columns: set[str] | list[str] | tuple[str, ...],
) -> str | None:
    """Return the first compatible physical column present in ``available_columns``."""
    available = {str(value).strip().lower() for value in available_columns if str(value).strip()}
    for candidate in compatible_columns(table_name, logical_column):
        if candidate.lower() in available:
            return candidate
    return None


def current_schema() -> str:
    """Return current active database/schema name."""
    return DB_NAME
