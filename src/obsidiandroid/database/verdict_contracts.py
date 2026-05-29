"""Shared verdict-table and vendor-engine contract helpers."""

from __future__ import annotations

import pandas as pd

from . import db_engine, schema_map
from .verdict_semantics import VERDICT_METADATA_COLUMNS


def fetch_verdict_table_columns() -> list[str]:
    """Return ordered columns from the wide vendor-verdict table."""
    verdict_table = schema_map.table("vendor_verdicts")
    return [str(column) for column in db_engine.get_table_columns(verdict_table)]


def fetch_vendor_verdict_columns(*, include_metadata: bool = False) -> list[str]:
    """Return wide verdict columns, optionally excluding metadata columns."""
    columns = fetch_verdict_table_columns()
    if include_metadata:
        return columns
    return [column for column in columns if column not in VERDICT_METADATA_COLUMNS]


def fetch_vendor_engine_flags() -> pd.DataFrame:
    """Return normalized active/trusted flags keyed by vendor_key."""
    vendors_table = schema_map.table("vendor_engines")
    engine_col = schema_map.column("vendor_engines", "engine_name")
    active_col = schema_map.column("vendor_engines", "active_flag")
    trusted_col = schema_map.column("vendor_engines", "trusted_flag")
    query = f"""
        SELECT
            LOWER(TRIM({engine_col})) AS vendor_key,
            {active_col} AS is_engine_active,
            {trusted_col} AS is_trusted_vendor
        FROM {vendors_table}
    """
    df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
