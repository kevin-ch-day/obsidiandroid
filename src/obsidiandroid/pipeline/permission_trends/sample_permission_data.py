"""Sample core construction, catalog temporal fields, and permission row fetches."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

import pandas as pd

from obsidiandroid.database import db_engine
from obsidiandroid.database import permission_contracts

from .constants import COMMON_PERMISSIONS, PERMISSION_ALIAS_MAP

def _permission_obs_key_expr() -> str:
    """Return the canonical SQL expression for permission grouping keys."""
    return permission_contracts.permission_obs_key_expr()


def _permission_obs_key_expr_ops() -> str:
    """Return the canonical SQL expression for ``ops``-aliased permission rows."""
    return permission_contracts.permission_obs_key_expr(alias="ops")


def build_sample_core(samples_df: pd.DataFrame) -> pd.DataFrame:
    working = samples_df.copy()
    working["sample_id"] = pd.to_numeric(working["sample_id"], errors="coerce")
    working = working.dropna(subset=["sample_id"])
    working["sample_id"] = working["sample_id"].astype(int)
    for col in ("sha256", "android_package_name", "family_canonical", "type_slug"):
        if col not in working.columns:
            working[col] = ""
    if "family_id" not in working.columns:
        working["family_id"] = -1
    working["sha256"] = working["sha256"].fillna("").astype(str).str.strip().str.lower()
    working["android_package_name"] = (
        working["android_package_name"].fillna("").astype(str).str.strip()
    )
    working["family_id"] = pd.to_numeric(working["family_id"], errors="coerce").fillna(-1).astype(int)
    working["family_canonical"] = working["family_canonical"].fillna("").astype(str).str.strip()
    working["type_slug"] = working["type_slug"].fillna("").astype(str).str.strip().str.lower()
    working.loc[working["type_slug"] == "", "type_slug"] = "unknown"
    if "android_permission_count" not in working.columns:
        working["android_permission_count"] = 0
    working["android_permission_count"] = pd.to_numeric(
        working["android_permission_count"], errors="coerce"
    ).fillna(0).astype(int)
    working = working.sort_values("sample_id").drop_duplicates(subset=["sample_id"]).copy()
    non_empty_sha = working["sha256"].ne("")
    if non_empty_sha.any():
        deduped = working[non_empty_sha].drop_duplicates(subset=["sha256"], keep="first")
        working = pd.concat([deduped, working[~non_empty_sha]], ignore_index=True)
    if "vt_first_submission_at_utc" not in working.columns and "vt_first_submission_date" in working.columns:
        working["vt_first_submission_at_utc"] = working["vt_first_submission_date"]
    for col in ("vt_first_seen_itw_date", "vt_first_submission_at_utc", "effective_first_seen_at_utc"):
        if col not in working.columns:
            working[col] = pd.NaT
    for col in ("effective_first_seen_year", "effective_first_seen_month"):
        if col not in working.columns:
            working[col] = ""
    return working


def attach_temporal_catalog_fields(sample_core_df: pd.DataFrame) -> pd.DataFrame:
    """Attach VT temporal columns from catalog for time-series analytics."""
    out = sample_core_df.copy()
    sample_ids = out["sample_id"].dropna().astype(int).tolist()
    catalog_df = fetch_temporal_fields_for_samples(sample_ids)
    if catalog_df.empty:
        for col in ("vt_first_seen_itw_date", "vt_first_submission_at_utc", "effective_first_seen_at_utc"):
            out[col] = pd.to_datetime(out.get(col), errors="coerce", utc=True)
        if "effective_first_seen_at_utc" not in out.columns:
            out["effective_first_seen_at_utc"] = out["vt_first_seen_itw_date"].where(
                out["vt_first_seen_itw_date"].notna(),
                out["vt_first_submission_at_utc"],
            )
        out["effective_first_seen_year"] = out["effective_first_seen_at_utc"].dt.year.astype("Int64")
        out["effective_first_seen_month"] = out["effective_first_seen_at_utc"].dt.strftime("%Y-%m")
        out.loc[out["effective_first_seen_month"] == "NaT", "effective_first_seen_month"] = ""
        return out
    merged = out.merge(catalog_df, on="sample_id", how="left", suffixes=("", "_catalog"))
    for col in ("vt_first_seen_itw_date", "vt_first_submission_at_utc"):
        base = pd.to_datetime(merged.get(col), errors="coerce", utc=True)
        catalog = pd.to_datetime(merged.get(f"{col}_catalog"), errors="coerce", utc=True)
        merged[col] = base.where(base.notna(), catalog)
        catalog_col = f"{col}_catalog"
        if catalog_col in merged.columns:
            merged = merged.drop(columns=[catalog_col])
    merged["effective_first_seen_at_utc"] = pd.to_datetime(
        merged.get("effective_first_seen_at_utc"), errors="coerce", utc=True
    )
    merged["effective_first_seen_at_utc"] = merged["effective_first_seen_at_utc"].where(
        merged["effective_first_seen_at_utc"].notna(),
        merged["vt_first_seen_itw_date"].where(
            merged["vt_first_seen_itw_date"].notna(),
            merged["vt_first_submission_at_utc"],
        ),
    )
    merged["effective_first_seen_year"] = merged["effective_first_seen_at_utc"].dt.year.astype("Int64")
    merged["effective_first_seen_month"] = merged["effective_first_seen_at_utc"].dt.strftime("%Y-%m")
    merged.loc[merged["effective_first_seen_month"] == "NaT", "effective_first_seen_month"] = ""
    return merged


def fetch_temporal_fields_for_samples(sample_ids: list[int]) -> pd.DataFrame:
    """Fetch ITW/submission temporal fields from malware_sample_catalog by sample_id."""
    if not sample_ids:
        return pd.DataFrame(columns=["sample_id", "vt_first_seen_itw_date", "vt_first_submission_at_utc"])
    frames: list[pd.DataFrame] = []
    chunk_size = 500
    for idx in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[idx : idx + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT
                sample_id,
                vt_first_seen_itw_date,
                vt_first_submission_at_utc
            FROM malware_sample_catalog
            WHERE sample_id IN ({placeholders})
        """
        try:
            frame = db_engine.execute_query(query, params=tuple(chunk), fetch=True, as_dataframe=True)
        except Exception:
            return pd.DataFrame(columns=["sample_id", "vt_first_seen_itw_date", "vt_first_submission_at_utc"])
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["sample_id", "vt_first_seen_itw_date", "vt_first_submission_at_utc"])
    out = pd.concat(frames, ignore_index=True)
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"])
    out["sample_id"] = out["sample_id"].astype(int)
    out["vt_first_seen_itw_date"] = pd.to_datetime(out["vt_first_seen_itw_date"], errors="coerce", utc=True)
    out["vt_first_submission_at_utc"] = pd.to_datetime(
        out["vt_first_submission_at_utc"], errors="coerce", utc=True
    )
    return out.drop_duplicates(subset=["sample_id"], keep="last")


def fetch_permission_aggregates() -> pd.DataFrame:
    common_a, common_b = COMMON_PERMISSIONS
    permission_key_expr = _permission_obs_key_expr()
    query = f"""
        SELECT
            sample_id,
            COUNT(*) AS permission_obs_rows,
            COUNT(DISTINCT {permission_key_expr}) AS permission_unique_count,
            SUM(
                CASE WHEN {permission_key_expr} IN ('{common_a}', '{common_b}')
                THEN 1 ELSE 0 END
            ) AS permission_common_rows
        FROM android_permission_obs_sample
        GROUP BY sample_id
    """
    df = db_engine.execute_permission_query(query, fetch=True, as_dataframe=True)
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "permission_obs_rows",
                "permission_unique_count",
                "permission_common_rows",
            ]
        )
    df["sample_id"] = pd.to_numeric(df["sample_id"], errors="coerce")
    df = df.dropna(subset=["sample_id"])
    df["sample_id"] = df["sample_id"].astype(int)
    return df


def fill_permission_observations(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("permission_obs_rows", "permission_unique_count", "permission_common_rows"):
        out[col] = pd.to_numeric(out.get(col, 0), errors="coerce").fillna(0).astype(int)
    return out


def fetch_permission_rows_for_samples(
    sample_ids: list[int],
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Fetch normalized permission observations with optional batch progress events.

    Permission-trends reporting needs a richer row-level contract than the ML
    feature builder.  The optional callback is deliberately observational: a
    renderer or checkpoint writer can report batch progress without changing
    query semantics or causing a reporting failure to interrupt retrieval.
    """
    if not sample_ids:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "permission_string",
                "protection_level",
                "permission_source",
            ]
        )
    chunk_size = 500
    total_batches = (len(sample_ids) + chunk_size - 1) // chunk_size
    frames: list[pd.DataFrame] = []
    cumulative_rows = 0
    stage_started_at = perf_counter()

    def emit_progress(event: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:  # pragma: no cover - presentation must not break data retrieval.
            return

    for idx in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[idx : idx + chunk_size]
        batch_number = (idx // chunk_size) + 1
        emit_progress(
            {
                "phase": "start",
                "batch_number": batch_number,
                "total_batches": total_batches,
                "requested_sample_count": len(chunk),
                "cumulative_rows": cumulative_rows,
                "elapsed_sec": max(0.0, perf_counter() - stage_started_at),
            }
        )
        placeholders = ", ".join(["%s"] * len(chunk))
        permission_key_expr = _permission_obs_key_expr_ops()
        if permission_contracts.permission_dictionary_norm_available():
            aosp_join = f"{permission_key_expr} = a.constant_value_norm"
            oem_join = f"{permission_key_expr} = o.permission_string_norm"
        else:
            aosp_join = "LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(a.constant_value))"
            oem_join = "LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(o.permission_string))"
        query = f"""
            SELECT
                ops.sample_id,
                ops.permission_string AS permission_string_raw,
                {permission_key_expr} AS permission_string,
                UPPER(COALESCE(a.protection_level, o.protection_level, 'UNKNOWN')) AS protection_level,
                UPPER(COALESCE(ops.classification, 'UNKNOWN')) AS permission_source,
                CASE WHEN a.constant_value IS NOT NULL THEN 1 ELSE 0 END AS is_aosp_dict_match,
                CASE WHEN o.permission_string IS NOT NULL THEN 1 ELSE 0 END AS is_oem_dict_match,
                gov.effective_source_family_key,
                gov.candidate_source_family_key,
                gov.effective_review_lane,
                gov.effective_resolution_semantics
            FROM android_permission_obs_sample ops
            LEFT JOIN android_permission_dict_aosp a
              ON {aosp_join}
            LEFT JOIN android_permission_dict_oem o
              ON {oem_join}
             AND (ops.vendor_id = o.vendor_id OR o.vendor_id IS NULL)
            LEFT JOIN vw_permission_vt_current_governed gov
              ON {permission_key_expr} = gov.raw_token_norm
            WHERE ops.sample_id IN ({placeholders})
              AND ops.permission_string IS NOT NULL
              AND TRIM(ops.permission_string) <> ''
        """
        batch_started_at = perf_counter()
        frame = db_engine.execute_permission_query(
            query, params=tuple(chunk), fetch=True, as_dataframe=True
        )
        batch_rows = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
        cumulative_rows += batch_rows
        emit_progress(
            {
                "phase": "complete",
                "batch_number": batch_number,
                "total_batches": total_batches,
                "requested_sample_count": len(chunk),
                "returned_row_count": batch_rows,
                "cumulative_rows": cumulative_rows,
                "query_duration_sec": max(0.0, perf_counter() - batch_started_at),
                "elapsed_sec": max(0.0, perf_counter() - stage_started_at),
            }
        )
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "permission_string",
                "protection_level",
                "permission_source",
                "is_aosp_dict_match",
                "is_oem_dict_match",
                "effective_source_family_key",
                "candidate_source_family_key",
                "effective_review_lane",
                "effective_resolution_semantics",
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"])
    out["sample_id"] = out["sample_id"].astype(int)
    out["permission_string"] = out["permission_string"].fillna("").astype(str).str.strip().str.lower()
    out["permission_string"] = out["permission_string"].replace(PERMISSION_ALIAS_MAP)
    out["protection_level"] = out["protection_level"].fillna("UNKNOWN").astype(str).str.upper()
    out["permission_source"] = out["permission_source"].fillna("UNKNOWN").astype(str).str.upper()
    for col in (
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
        "effective_resolution_semantics",
    ):
        series = out[col] if col in out.columns else pd.Series("", index=out.index, dtype="object")
        out[col] = series.fillna("").astype(str).str.strip().str.lower()
    out["is_aosp_dict_match"] = pd.to_numeric(out.get("is_aosp_dict_match", 0), errors="coerce").fillna(0).astype(int)
    out["is_oem_dict_match"] = pd.to_numeric(out.get("is_oem_dict_match", 0), errors="coerce").fillna(0).astype(int)
    out = out[out["permission_string"] != ""].drop_duplicates(subset=["sample_id", "permission_string"])
    return out


def permission_support_floor(sample_count: int) -> int:
    return int(max(50, round(sample_count * 0.01)))


def filter_permission_rows_by_view(permission_rows_df: pd.DataFrame, view_name: str) -> pd.DataFrame:
    if permission_rows_df.empty:
        return permission_rows_df
    view = str(view_name).strip().lower()
    src = permission_rows_df["permission_source"].fillna("").astype(str).str.upper()
    is_aosp_match = (
        pd.to_numeric(permission_rows_df.get("is_aosp_dict_match", 0), errors="coerce").fillna(0).astype(int) > 0
    )
    is_oem_match = (
        pd.to_numeric(permission_rows_df.get("is_oem_dict_match", 0), errors="coerce").fillna(0).astype(int) > 0
    )
    if view == "inclusive":
        return permission_rows_df.copy()
    if view == "aosp_only":
        perm = permission_rows_df["permission_string"].fillna("").astype(str).str.lower()
        mask = is_aosp_match & perm.str.startswith("android.permission.")
        return permission_rows_df.loc[mask].copy()
    if view == "ecosystem":
        mask = (
            is_aosp_match
            | is_oem_match
            | src.str.contains("GOOGLE", regex=False)
        )
        return permission_rows_df.loc[mask].copy()
    return permission_rows_df.copy()


def build_permission_binary_matrix(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    support_floor: int,
    forced_permissions: set[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    sample_ids = sample_core_df["sample_id"].astype(int).tolist()
    base = pd.DataFrame({"sample_id": sample_ids})
    if permission_rows_df.empty:
        return base, []
    support = permission_rows_df.groupby("permission_string")["sample_id"].nunique().sort_values(ascending=False)
    keep = set(support[support >= support_floor].index.tolist())
    if forced_permissions:
        keep.update({perm for perm in forced_permissions if perm in support.index})
    if not keep:
        return base, []
    work = permission_rows_df[permission_rows_df["permission_string"].isin(keep)].copy()
    if work.empty:
        return base, []
    ctab = pd.crosstab(work["sample_id"], work["permission_string"])
    ctab = (ctab > 0).astype(int).reset_index()
    merged = base.merge(ctab, on="sample_id", how="left").fillna(0)
    for col in merged.columns:
        if col != "sample_id":
            merged[col] = merged[col].astype(int)
    keep_sorted = sorted([col for col in merged.columns if col != "sample_id"])
    return merged, keep_sorted
