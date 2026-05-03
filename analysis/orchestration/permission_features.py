"""Permission feature extraction for sample-level modeling."""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from config import app_config
from database import db_engine
from utils import display_utils as du


_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")


def _sanitize_permission_name(permission: str) -> str:
    token = _TOKEN_PATTERN.sub("_", str(permission).strip().lower()).strip("_")
    return token or "unknown_permission"


def _iter_chunks(values: list[int], chunk_size: int = 500) -> Iterable[list[int]]:
    for idx in range(0, len(values), chunk_size):
        yield values[idx : idx + chunk_size]


def _fetch_permission_rows(sample_ids: list[int]) -> pd.DataFrame:
    if not sample_ids:
        return pd.DataFrame()

    frames = []
    for chunk in _iter_chunks(sample_ids):
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT
                ops.sample_id,
                ops.permission_string,
                UPPER(COALESCE(ops.classification, 'UNKNOWN')) AS permission_source,
                UPPER(COALESCE(a.protection_level, o.protection_level, 'UNKNOWN')) AS protection_level
            FROM android_permission_obs_sample ops
            LEFT JOIN android_permission_dict_aosp a
                ON ops.permission_string = a.constant_value
            LEFT JOIN android_permission_dict_oem o
                ON ops.permission_string = o.permission_string
                AND (ops.vendor_id = o.vendor_id OR o.vendor_id IS NULL)
            WHERE ops.sample_id IN ({placeholders})
              AND ops.permission_string IS NOT NULL
              AND TRIM(ops.permission_string) <> ''
        """
        try:
            frame = db_engine.execute_permission_query(
                query,
                params=tuple(chunk),
                fetch=True,
                as_dataframe=True,
            )
        except Exception as exc:  # pylint: disable=broad-except
            setattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", True)
            strict_in_evidence = bool(
                getattr(app_config, "PERMISSION_ENRICHMENT_STRICT_IN_EVIDENCE", False)
            )
            evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False))
            if strict_in_evidence and evidence_mode:
                raise RuntimeError(
                    "[INTEGRITY] Permission enrichment DB fetch failed in evidence mode: "
                    f"{exc}"
                ) from exc
            du.print_warning(
                "[PERMISSIONS] Failed to fetch permission rows; "
                f"continuing without permission enrichment ({exc})."
            )
            return pd.DataFrame()
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_permission_feature_frame(
    samples_df: pd.DataFrame,
    min_permission_support: int = 2,
    max_permission_features: int | None = None,
) -> pd.DataFrame:
    """Build per-sample permission features from observed permission table.

    Args:
        samples_df: Cohort samples containing ``sample_id``.
        min_permission_support: Minimum sample support to keep a permission token.
        max_permission_features: Optional cap for bag-of-words permission columns.

    Returns:
        DataFrame with ``sample_id`` plus permission-derived features.
    """
    setattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", False)
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()
    if "sample_id" not in samples_df.columns:
        return pd.DataFrame()

    sample_ids = sorted(
        {
            int(float(sample_id))
            for sample_id in samples_df["sample_id"].tolist()
            if pd.notna(sample_id)
        }
    )
    permission_df = _fetch_permission_rows(sample_ids)
    feature_df = pd.DataFrame({"sample_id": sample_ids})
    if permission_df.empty:
        return feature_df

    permission_df["sample_id"] = pd.to_numeric(permission_df["sample_id"], errors="coerce").fillna(-1).astype(int)
    permission_df["permission_string"] = (
        permission_df["permission_string"].fillna("").astype(str).str.strip().str.lower()
    )
    permission_df = permission_df[permission_df["permission_string"] != ""]
    if permission_df.empty:
        return feature_df

    permission_counts = permission_df.groupby("permission_string")["sample_id"].nunique()
    keep_permissions = permission_counts[permission_counts >= int(min_permission_support)].sort_values(ascending=False)
    if max_permission_features is not None and int(max_permission_features) > 0:
        keep_permissions = keep_permissions.head(int(max_permission_features))
    keep_tokens = set(keep_permissions.index.tolist())

    bow_df = permission_df[permission_df["permission_string"].isin(keep_tokens)]
    if not bow_df.empty:
        bow = pd.crosstab(bow_df["sample_id"], bow_df["permission_string"])
        bow = (bow > 0).astype(int)
        bow.columns = [f"perm__{_sanitize_permission_name(col)}" for col in bow.columns]
        bow = bow.reset_index()
        feature_df = feature_df.merge(bow, on="sample_id", how="left")

    protection = permission_df["protection_level"].fillna("UNKNOWN").astype(str).str.upper()
    permission_df["is_dangerous"] = protection.str.contains("DANGEROUS", regex=False).astype(int)
    permission_df["is_normal"] = protection.str.contains("NORMAL", regex=False).astype(int)

    source = permission_df["permission_source"].fillna("UNKNOWN").astype(str).str.upper()
    permission_df["is_oem"] = source.isin({"OEM", "APP_DEFINED"}).astype(int)

    counts = (
        permission_df.groupby("sample_id")
        .agg(
            perm__dangerous_count=("is_dangerous", "sum"),
            perm__normal_count=("is_normal", "sum"),
            perm__oem_count=("is_oem", "sum"),
            perm__total_count=("permission_string", "count"),
        )
        .reset_index()
    )
    feature_df = feature_df.merge(counts, on="sample_id", how="left")

    for col in feature_df.columns:
        if col == "sample_id":
            continue
        feature_df[col] = pd.to_numeric(feature_df[col], errors="coerce").fillna(0).astype(int)

    return feature_df.drop_duplicates("sample_id")
