"""Shared contracts and helpers for Android sample metadata query modules."""

from __future__ import annotations

import pandas as pd

from utils import display_utils as du

SUPPORTED_ANDROID_TYPE_SLUGS = (
    "banker",
    "dropper",
    "adware",
    "stealer",
    "sms-trojan",
    "rat",
    "spyware",
    "unknown",
)

QUERY_CONTRACT_VERSION = "android_samples_v1_ordered_2026-03-04"
QUERY_ORDERING_POLICY = "ORDER BY sample_id ASC for cohort and metadata retrieval"
QUERY_CONTRACT_NOTES = (
    "Deterministic query ordering is enforced for key sample retrieval paths. "
    "VT scan summary, family-resolution, and artifact hash-registry joins use "
    "ROW_NUMBER-ranked subqueries so each catalog sample_id maps to one joined row "
    "(see database/cohort_sql_fragments.py)."
)


def get_query_contract_metadata() -> dict:
    """Return DB query determinism contract metadata for run manifests."""
    return {
        "version": QUERY_CONTRACT_VERSION,
        "ordering_policy": QUERY_ORDERING_POLICY,
        "notes": QUERY_CONTRACT_NOTES,
    }


def get_supported_android_type_slugs() -> tuple[str, ...]:
    """Return the canonical Android malware type slugs accepted by this layer."""
    return SUPPORTED_ANDROID_TYPE_SLUGS


def convert_to_dataframe(result: tuple[list, list], label: str = "") -> pd.DataFrame:
    """Validate and convert a ``(columns, rows)`` query result into a DataFrame.

    Args:
        result: Two-item tuple from ``db_engine.execute_query``.
        label: Friendly name used in display logging.

    Returns:
        A populated DataFrame when conversion succeeds, otherwise an empty DataFrame.
    """
    if not isinstance(result, tuple) or len(result) != 2:
        du.print_error(f"[{label}] Unexpected return format: expected (columns, rows).")
        return pd.DataFrame()

    columns, rows = result

    if not isinstance(columns, list) or not isinstance(rows, list):
        du.print_error(
            f"[{label}] Invalid types: Expected (list, list), got {type(columns)}, {type(rows)}."
        )
        return pd.DataFrame()

    try:
        dataframe = pd.DataFrame(rows, columns=columns)
    except Exception as error:  # pylint: disable=broad-except
        du.print_error(f"[{label}] DataFrame construction failed: {error}")
        return pd.DataFrame()

    if dataframe.empty:
        du.print_warning(f"[{label}] Query returned 0 rows.")
    else:
        du.print_success(
            f"[{label}] Loaded {len(dataframe)} rows × {len(dataframe.columns)} columns."
        )

    return dataframe


def log_and_assert_loader_sample_grain(dataframe: pd.DataFrame, *, label: str) -> None:
    """Log row counts and enforce exactly one row per ``sample_id`` at loader boundary."""
    if dataframe.empty or "sample_id" not in dataframe.columns:
        return

    rows_loaded = len(dataframe)
    distinct_sample_ids = int(dataframe["sample_id"].nunique())
    duplicate_surplus = rows_loaded - distinct_sample_ids
    du.print_info(
        f"[DB] Loader grain ({label}): rows_loaded={rows_loaded} "
        f"distinct_sample_ids={distinct_sample_ids} duplicate_surplus={duplicate_surplus}"
    )
    if duplicate_surplus != 0:
        raise ValueError(
            f"[{label}] Cohort loader cardinality breach: duplicate_surplus={duplicate_surplus}. "
            "Inspect primary SQL joins (VT summaries multiplied by sha256/sample_id, "
            "or v_android_apk_family_resolved multiple rows per sample)."
        )
