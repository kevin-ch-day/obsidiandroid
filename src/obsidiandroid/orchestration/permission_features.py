"""Permission feature extraction for sample-level modeling."""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from config import app_config
from obsidiandroid.database import db_engine
from obsidiandroid.database import permission_contracts
from obsidiandroid.cli.ui import display as du

# Grouped permission bundles (coarse capability families; counts are per observed permission row).
PERMISSION_GROUP_DEFINITIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sms_telephony_count", re.compile(r"(?:sms|telephon|mms|send_sms|receive_sms|read_sms|write_sms)", re.I)),
    ("network_c2_count", re.compile(r"(?:internet|network_state|access_network|change_network|vpn|wifi|c2|socket)", re.I)),
    (
        "persistence_autostart_count",
        re.compile(
            r"(?:boot_completed|device_admin|foreground_service|persist|install_shortcut|receive_boot|scheduled|alarm)",
            re.I,
        ),
    ),
    (
        "overlay_accessibility_count",
        re.compile(r"(?:system_alert_window|draw_overlay|accessibility|bind_accessibility)", re.I),
    ),
    (
        "storage_file_access_count",
        re.compile(
            r"(?:external_storage|manage_external|read_external|write_external|media_|documents|downloads|storage)",
            re.I,
        ),
    ),
    (
        "surveillance_sensor_count",
        re.compile(r"(?:camera|microphone|audio|record_audio|video|fine_location|access_fine|body_sensors)", re.I),
    ),
    ("account_contact_count", re.compile(r"(?:account|contacts|read_contacts|write_contacts|call_log|phone_state)", re.I)),
    ("package_inventory_count", re.compile(r"(?:package|query_all_packages|install_packages|request_install)", re.I)),
    ("oem_vendor_specific_count", re.compile(r"^com\.[a-z0-9_.]+\.permission\.", re.I)),
)

_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")
def _permission_obs_key_expr() -> str:
    """Return the SQL expression for the canonical permission grouping key.

    ``permission_string_norm`` is the governed normalized key when present in the
    live Permission Intel schema. Older fixtures or deployments may not expose it,
    so we fall back to the legacy lowercase/trim expression.
    """
    return permission_contracts.permission_obs_key_expr(alias="ops")


def augment_grouped_permission_counts(permission_df: pd.DataFrame, feature_df: pd.DataFrame) -> pd.DataFrame:
    """Attach ``perm_grp__*`` aggregate counts derived from raw permission rows.

    The previous implementation iterated every sample and every regular
    expression in Python.  A current-corpus run has thousands of samples, so
    this vectorized form keeps the same per-row count semantics while grouping
    only the rows that match each capability pattern.
    """
    if permission_df.empty or feature_df.empty:
        return feature_df
    if "sample_id" not in permission_df.columns or "permission_string" not in permission_df.columns:
        return feature_df

    work = permission_df.copy()
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""]
    if work.empty:
        return feature_df

    wide = feature_df.copy()
    if "sample_id" not in wide.columns:
        return feature_df
    sample_ids = sorted({int(x) for x in wide["sample_id"].tolist() if pd.notna(x)})
    base_idx = pd.Index(sample_ids, name="sample_id")
    if base_idx.empty:
        return wide
    work["_sample_id_int"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work[work["_sample_id_int"].notna()].copy()
    work["_sample_id_int"] = work["_sample_id_int"].astype(int)
    work = work[work["_sample_id_int"].isin(base_idx)]
    if work.empty:
        return wide

    agg = pd.DataFrame(index=base_idx)
    permission_text = work["permission_string"]
    for group_name, pattern in PERMISSION_GROUP_DEFINITIONS:
        matched_ids = work.loc[
            permission_text.str.contains(pattern, na=False), "_sample_id_int"
        ]
        counts = matched_ids.value_counts().reindex(base_idx, fill_value=0)
        agg[f"perm_grp__{group_name}"] = counts.to_numpy(dtype=int)

    agg = agg.reset_index()
    merged = wide.merge(agg, on="sample_id", how="left")
    grp_cols = [c for c in merged.columns if c.startswith("perm_grp__")]
    for col in grp_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    return merged


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
        permission_key_expr = _permission_obs_key_expr()
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
                UPPER(COALESCE(ops.classification, 'UNKNOWN')) AS permission_source,
                UPPER(COALESCE(a.protection_level, o.protection_level, 'UNKNOWN')) AS protection_level
            FROM android_permission_obs_sample ops
            LEFT JOIN android_permission_dict_aosp a
                ON {aosp_join}
            LEFT JOIN android_permission_dict_oem o
                ON {oem_join}
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

    out = feature_df.drop_duplicates("sample_id")
    return augment_grouped_permission_counts(permission_df, out)
