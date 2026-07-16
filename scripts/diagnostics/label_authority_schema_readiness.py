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

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.database import db_engine
from obsidiandroid.database.authority_contracts import (
    CURRENT_OPERATOR_VIEW_COLUMNS,
    CURRENT_POLICY_TABLE_COLUMNS,
    LIVE_AUTHORITY_REQUIRED_COLUMNS,
    active_column_contract,
    evaluate_object_contracts,
    fetch_columns_df,
    fetch_objects_df,
    object_presence,
)
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

LIVE_AUTHORITY_OBJECTS = [
    "v_android_sample_family_type_authority",
]

def _fetch_columns() -> pd.DataFrame:
    return fetch_columns_df()


def _fetch_objects() -> pd.DataFrame:
    return fetch_objects_df()


def _object_presence(objects_df: pd.DataFrame, name: str) -> str:
    return object_presence(objects_df, name)


def _missing_columns(columns_df: pd.DataFrame, object_name: str, required: list[str]) -> list[str]:
    if columns_df.empty:
        return list(required)
    mask = columns_df["table_name"].astype(str).str.lower() == str(object_name).lower()
    present = {
        str(value).lower()
        for value in columns_df.loc[mask, "column_name"].astype(str).tolist()
    }
    return [col for col in required if col.lower() not in present]


def _active_column_contract(columns_df: pd.DataFrame, object_name: str) -> str:
    return active_column_contract(columns_df, object_name)


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
    proposed_presence: dict[str, str] = {}
    for object_name in PROPOSED_OBJECTS:
        status = _object_presence(objects_df, object_name)
        proposed_presence[object_name] = status
        print(f"- {object_name}: {status}")

    print("\nCurrent live authority objects")
    live_authority_present = False
    live_authority_contracts = evaluate_object_contracts(
        LIVE_AUTHORITY_REQUIRED_COLUMNS,
        columns_df=columns_df,
        objects_df=objects_df,
    )
    for object_name in LIVE_AUTHORITY_OBJECTS:
        status = _object_presence(objects_df, object_name)
        if status != "missing":
            live_authority_present = True
        missing = list(live_authority_contracts.get(object_name, {}).get("missing_columns", []))
        missing_text = ", ".join(missing) if missing else "-"
        print(f"- {object_name}: {status}; missing columns: {missing_text}")

    print("\nCurrent operator views")
    operator_views_ready = True
    operator_contracts = evaluate_object_contracts(
        CURRENT_OPERATOR_VIEW_COLUMNS,
        columns_df=columns_df,
        objects_df=objects_df,
    )
    for object_name in CURRENT_OPERATOR_VIEW_COLUMNS:
        status = _object_presence(objects_df, object_name)
        missing = list(operator_contracts.get(object_name, {}).get("missing_columns", []))
        if status == "missing" or missing:
            operator_views_ready = False
        missing_text = ", ".join(missing) if missing else "-"
        print(f"- {object_name}: {status}; missing columns: {missing_text}")

    print("\nCurrent policy tables")
    policy_tables_ready = True
    policy_contracts = evaluate_object_contracts(
        CURRENT_POLICY_TABLE_COLUMNS,
        columns_df=columns_df,
        objects_df=objects_df,
    )
    for object_name in CURRENT_POLICY_TABLE_COLUMNS:
        status = _object_presence(objects_df, object_name)
        missing = list(policy_contracts.get(object_name, {}).get("missing_columns", []))
        active_contract = _active_column_contract(columns_df, object_name)
        if status == "missing" or missing or active_contract == "missing":
            policy_tables_ready = False
        missing_text = ", ".join(missing) if missing else "-"
        print(
            f"- {object_name}: {status}; missing columns: {missing_text}; "
            f"active-column contract: {active_contract}"
        )

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
        if live_authority_present:
            print("- current live authority coverage view is already present")
            if operator_views_ready and policy_tables_ready:
                print("- current operator triage views satisfy the expected live contract")
                print("- current generic-token policy table satisfies the expected live contract")
            else:
                if not operator_views_ready:
                    print("- one or more current operator triage views are missing or incomplete")
                if not policy_tables_ready:
                    print("- generic-token policy table is missing or incomplete for the live contract")
        elif any(status != "missing" for status in proposed_presence.values()):
            print("- label-authority foundation rollout appears partially applied")
        else:
            print("- label-authority foundation objects still need to be applied")
        return 0

    print("- base schema is missing prerequisites; review the gaps above before applying DDL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
