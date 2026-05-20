"""Read-only readiness audit for label-authority schema rollout.

Checks:
- base Erebus tables/views and expected columns
- presence of proposed label-authority tables/views
- coverage of core wide VT vendor columns used by the initial evidence seed
- estimated seedable vendor-label evidence volume

This script does not modify the database.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import db_engine
from obsidiandroid.database.schema_map import table


REQUIRED_BASE_OBJECTS: dict[str, list[str]] = {
    table("sample_catalog"): [
        "sample_id",
        "sha256",
        "sample_label",
        "family_label",
        "classification_primary",
        "classification_subtype",
        "vt_first_seen_itw_date",
        "vt_first_submission_at_utc",
    ],
    "android_malware_family": [
        "family_id",
        "family_slug",
        "family_name",
        "primary_type_id",
        "is_active",
    ],
    "android_malware_type": [
        "type_id",
        "type_slug",
    ],
    "v_android_apk_family_resolved": [
        "sample_id",
        "resolved_family_lc",
    ],
    table("vendor_verdicts"): [
        "sample_id",
        "updated_at",
    ],
    table("vendor_engines"): [
        "vendor_key",
        "is_engine_active",
        "is_trusted_vendor",
    ],
}

CORE_VENDOR_COLUMNS = [
    "ahnlab_v3",
    "alibaba",
    "avast",
    "avast_mobile",
    "bitdefender",
    "bitdefenderfalx",
    "ikarus",
    "k7gw",
    "kaspersky",
    "lionic",
    "microsoft",
    "tencent",
    "zonealarm",
]

PROPOSED_OBJECTS = [
    table("family_alias_fact"),
    table("family_authority_fact"),
    table("family_label_evidence"),
    table("vendor_label_generic_tokens"),
    table("av_engine_dependency_fact"),
    table("sample_temporal_resolved_view"),
    table("label_authority_resolution_view"),
]


def _fetch_columns() -> pd.DataFrame:
    query = """
        SELECT
            table_name,
            column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        ORDER BY table_name, ordinal_position
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def _fetch_objects() -> pd.DataFrame:
    query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        ORDER BY table_name
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def _object_presence(objects_df: pd.DataFrame, name: str) -> str:
    if objects_df.empty:
        return "missing"
    mask = objects_df["table_name"].astype(str).str.lower() == str(name).lower()
    if not mask.any():
        return "missing"
    table_type = str(objects_df.loc[mask, "table_type"].iloc[0]).upper()
    if "VIEW" in table_type:
        return "view"
    return "table"


def _missing_columns(columns_df: pd.DataFrame, object_name: str, required: list[str]) -> list[str]:
    if columns_df.empty:
        return list(required)
    mask = columns_df["table_name"].astype(str).str.lower() == str(object_name).lower()
    present = {
        str(value).lower()
        for value in columns_df.loc[mask, "column_name"].astype(str).tolist()
    }
    return [col for col in required if col.lower() not in present]


def _estimate_seedable_vendor_rows() -> pd.DataFrame:
    verdict_table = table("vendor_verdicts")
    parts: list[str] = []
    for vendor_col in CORE_VENDOR_COLUMNS:
        parts.append(
            f"""
            SELECT
                '{vendor_col}' AS vendor_key,
                COUNT(*) AS nonempty_rows
            FROM {verdict_table}
            WHERE {vendor_col} IS NOT NULL
              AND TRIM({vendor_col}) <> ''
              AND LOWER(TRIM({vendor_col})) NOT IN (
                  'none','null','n/a','undetected','clean','benign','harmless',
                  'safe','approved','verified','type-unsupported','type_unsupported',
                  'timeout','failure'
              )
            """
        )
    union_query = "\nUNION ALL\n".join(parts)
    query = f"""
        SELECT vendor_key, nonempty_rows
        FROM (
            {union_query}
        ) AS vendor_counts
        ORDER BY nonempty_rows DESC, vendor_key ASC
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def main() -> int:
    print("Label Authority Schema Readiness")
    print("=" * 34)

    columns_df = _fetch_columns()
    objects_df = _fetch_objects()

    print("\nBase object prerequisites")
    all_ready = True
    for object_name, required_cols in REQUIRED_BASE_OBJECTS.items():
        status = _object_presence(objects_df, object_name)
        missing = _missing_columns(columns_df, object_name, required_cols)
        if status == "missing" or missing:
            all_ready = False
        missing_text = ", ".join(missing) if missing else "-"
        print(f"- {object_name}: {status}; missing columns: {missing_text}")

    print("\nCore vendor columns for first evidence seed")
    vendor_missing = _missing_columns(columns_df, table("vendor_verdicts"), CORE_VENDOR_COLUMNS)
    if vendor_missing:
        print(f"- missing vendor columns: {', '.join(vendor_missing)}")
    else:
        print("- all core vendor columns present")

    print("\nProposed label-authority objects")
    for object_name in PROPOSED_OBJECTS:
        status = _object_presence(objects_df, object_name)
        print(f"- {object_name}: {status}")

    print("\nEstimated seedable vendor-label evidence rows")
    seed_df = _estimate_seedable_vendor_rows()
    if isinstance(seed_df, pd.DataFrame) and not seed_df.empty:
        total_rows = int(seed_df["nonempty_rows"].sum())
        print(f"- total seedable rows across core vendor set: {total_rows}")
        for _, row in seed_df.iterrows():
            print(f"  - {row['vendor_key']}: {int(row['nonempty_rows'])}")
    else:
        print("- no seedable rows or verdict table unavailable")

    print("\nOverall readiness")
    if all_ready and not vendor_missing:
        print("- base schema looks ready for the label-authority foundation pack")
        return 0

    print("- base schema is missing prerequisites; review the gaps above before applying DDL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
