"""Utilities for reproducible analysis snapshot locking and export."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du


def _emit_csv_with_run_hygiene(*, primary: Path, csv_text: str, global_latest_name: str) -> None:
    """Write run-scoped CSV; under ``runs/`` omit local ``*.latest.*`` and mirror to global diagnostics."""
    from obsidiandroid.common import output_hygiene as oh

    primary = Path(primary)
    primary.parent.mkdir(parents=True, exist_ok=True)
    if oh.path_is_under_output_runs(primary.parent) and oh.run_diagnostics_should_omit_latest_duplicate():
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=primary.parent,
            run_filename=primary.name,
            csv_text=csv_text,
            global_latest_name=global_latest_name,
        )
    else:
        primary.write_text(csv_text, encoding="utf-8")


def _emit_utf8_with_run_hygiene(*, primary: Path, body: str, global_latest_name: str) -> None:
    """Write UTF-8 sidecar (snapshot meta); mirror policy matches :func:`_emit_csv_with_run_hygiene`."""
    from obsidiandroid.common import output_hygiene as oh

    primary = Path(primary)
    primary.parent.mkdir(parents=True, exist_ok=True)
    if oh.path_is_under_output_runs(primary.parent) and oh.run_diagnostics_should_omit_latest_duplicate():
        oh.mirror_utf8_text_run_then_global(
            diagnostics_dir=primary.parent,
            run_filename=primary.name,
            text=body,
            global_latest_name=global_latest_name,
        )
    else:
        primary.write_text(body, encoding="utf-8")


def apply_analysis_snapshot_lock(
    samples_df: pd.DataFrame,
    lock_file: str,
    *,
    fail_closed: bool = False,
) -> pd.DataFrame:
    """Filter samples to a locked analysis snapshot file when it exists.

    Args:
        samples_df: Input sample metadata DataFrame containing `sample_id`.
        lock_file: CSV path containing at least a `sample_id` column.
        fail_closed: When ``True``, invalid or missing lock state raises instead
            of silently falling back to the live cohort.

    Returns:
        Filtered DataFrame sorted by `sample_id`. If lock file is not found
        or invalid, the original DataFrame is returned in deterministic order.
    """
    prepared = _sort_by_sample_id(samples_df)
    metadata = {
        "requested": True,
        "lock_file": str(lock_file),
        "fail_closed": bool(fail_closed),
    }
    if not os.path.exists(lock_file):
        if fail_closed:
            raise ValueError(f"[SNAPSHOT] Lock file not found: {lock_file}")
        _set_snapshot_lock_metadata(prepared, {**metadata, "status": "missing_file", "applied": False})
        du.print_warning(f"[SNAPSHOT] Lock file not found: {lock_file}. Using live dataset.")
        return prepared

    try:
        lock_df = pd.read_csv(lock_file)
    except Exception as exc:
        if fail_closed:
            raise ValueError(f"[SNAPSHOT] Failed to read lock file: {exc}") from exc
        _set_snapshot_lock_metadata(prepared, {**metadata, "status": "read_error", "applied": False})
        du.print_error(f"[SNAPSHOT] Failed to read lock file: {exc}. Using live dataset.")
        return prepared

    if "sample_id" not in lock_df.columns:
        if fail_closed:
            raise ValueError("[SNAPSHOT] Lock file missing 'sample_id' column.")
        _set_snapshot_lock_metadata(prepared, {**metadata, "status": "missing_sample_id_column", "applied": False})
        du.print_error("[SNAPSHOT] Lock file missing 'sample_id' column. Using live dataset.")
        return prepared

    lock_df = lock_df.copy()
    lock_df["sample_id"] = pd.to_numeric(lock_df["sample_id"], errors="coerce")
    lock_df = lock_df.dropna(subset=["sample_id"])
    lock_df["sample_id"] = lock_df["sample_id"].astype(int)
    if lock_df.empty:
        if fail_closed:
            raise ValueError("[SNAPSHOT] Lock file contains no valid sample_id rows.")
        _set_snapshot_lock_metadata(prepared, {**metadata, "status": "empty_lock", "applied": False})
        du.print_error("[SNAPSHOT] Lock file contains no valid sample_id rows. Using live dataset.")
        return prepared

    locked_ids = set(lock_df["sample_id"].tolist())
    live_ids = set(_normalize_ids(prepared["sample_id"].tolist()))
    kept_ids = sorted(live_ids.intersection(locked_ids))

    if not kept_ids:
        if fail_closed:
            raise ValueError("[SNAPSHOT] Lock produced zero overlapping samples.")
        _set_snapshot_lock_metadata(prepared, {**metadata, "status": "zero_overlap", "applied": False})
        du.print_error("[SNAPSHOT] Lock produced zero overlapping samples. Using live dataset.")
        return prepared

    filtered = prepared[prepared["sample_id"].isin(kept_ids)].copy()
    _inherit_dataframe_attrs(filtered, prepared)
    lock_subset = lock_df[lock_df["sample_id"].isin(kept_ids)].drop_duplicates("sample_id")
    filtered = _apply_optional_lock_constraints(filtered, lock_subset)
    _inherit_dataframe_attrs(filtered, prepared)
    filtered = _sort_by_sample_id(filtered)
    _inherit_dataframe_attrs(filtered, prepared)

    missing_from_db = len(locked_ids - live_ids)
    _set_snapshot_lock_metadata(
        filtered,
        {
            **metadata,
            "status": "matched",
            "applied": True,
            "matched_sample_count": int(len(filtered)),
            "lock_sample_count": int(len(locked_ids)),
            "missing_from_db_count": int(missing_from_db),
        },
    )
    du.print_info(
        f"[SNAPSHOT] Lock enabled: {len(filtered)} samples matched. "
        f"Missing from DB: {missing_from_db}."
    )
    return filtered


def export_analysis_snapshot(
    samples_df: pd.DataFrame,
    snapshot_file: str,
    meta_file: str,
    conflict_file: str | None = None,
    selection_rule_version: str | None = None,
    run_id: str | None = None,
) -> None:
    """Export deterministic analysis snapshot IDs and metadata for reproducibility.

    Args:
        samples_df: Input sample metadata DataFrame containing `sample_id`.
        snapshot_file: CSV output path.
        meta_file: Text metadata output path.
        conflict_file: Optional CSV path for SHA256 label conflicts.
        selection_rule_version: Optional selection ruleset identifier.
        run_id: Optional run identifier recorded in metadata.
    """
    if "sample_id" not in samples_df.columns:
        du.print_warning("[SNAPSHOT] Cannot export analysis snapshot: missing 'sample_id'.")
        return

    work_df = samples_df.copy()
    work_df["sample_id"] = pd.to_numeric(work_df["sample_id"], errors="coerce")
    work_df = work_df.dropna(subset=["sample_id"])
    work_df["sample_id"] = work_df["sample_id"].astype(int)
    work_df = _sort_by_sample_id(work_df)
    work_df = _normalize_snapshot_fields(work_df)
    conflicts_df = _build_sha256_label_conflicts(work_df)
    conflicted_sha256 = set()
    if not conflicts_df.empty:
        conflicted_sha256 = set(conflicts_df["sha256"].tolist())
        if conflict_file:
            cbuf = StringIO()
            conflicts_df.to_csv(cbuf, index=False)
            _emit_csv_with_run_hygiene(
                primary=Path(conflict_file),
                csv_text=cbuf.getvalue(),
                global_latest_name="analysis_snapshot_label_conflicts.latest.csv",
            )
        du.print_warning(
            f"[SNAPSHOT] Found {len(conflicts_df)} SHA256 label conflict(s). "
            "Conflicted hashes were quarantined from snapshot export."
        )

    snapshot_df = work_df[["sample_id"]].drop_duplicates("sample_id").sort_values("sample_id")
    sha_df = (
        work_df[["sample_id", "sha256"]]
        .drop_duplicates("sample_id")
        .copy()
    )
    snapshot_df = snapshot_df.merge(sha_df, on="sample_id", how="left")

    fam_df = work_df[["sample_id", "family_id"]].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(fam_df, on="sample_id", how="left")

    family_name_df = work_df[["sample_id", "family_name"]].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(family_name_df, on="sample_id", how="left")

    canonical_df = work_df[["sample_id", "family_canonical"]].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(canonical_df, on="sample_id", how="left")

    type_df = work_df[["sample_id", "type_slug"]].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(type_df, on="sample_id", how="left")
    raw_taxonomy_df = work_df[
        [
            "sample_id",
            "category_primary",
            "category_subtype",
            "sample_label_kind",
            "family_label_raw",
            "vt_family_token",
            "source_batch_label",
        ]
    ].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(raw_taxonomy_df, on="sample_id", how="left")
    temporal_df = work_df[
        [
            "sample_id",
            "vt_first_seen_itw_date",
            "vt_first_submission_at_utc",
            "effective_first_seen_at_utc",
            "effective_first_seen_year",
            "effective_first_seen_month",
        ]
    ].drop_duplicates("sample_id").copy()
    snapshot_df = snapshot_df.merge(temporal_df, on="sample_id", how="left")

    if conflicted_sha256:
        is_conflicted = snapshot_df["sha256"].fillna("").astype(str).str.strip().str.lower().isin(conflicted_sha256)
        dropped_count = int(is_conflicted.sum())
        if dropped_count > 0:
            snapshot_df = snapshot_df.loc[~is_conflicted].copy()
            du.print_warning(f"[SNAPSHOT] Dropped {dropped_count} sample(s) due to SHA256 label conflicts.")

    snapshot_df["feature_hash"] = snapshot_df.apply(_compute_snapshot_feature_hash, axis=1)
    snapshot_df = _sort_by_sample_id(snapshot_df)

    sbuf = StringIO()
    snapshot_df.to_csv(sbuf, index=False)
    _emit_csv_with_run_hygiene(
        primary=Path(snapshot_file),
        csv_text=sbuf.getvalue(),
        global_latest_name="analysis_snapshot.latest.csv",
    )

    sample_id_digest = _hash_ids(snapshot_df["sample_id"].tolist())
    snapshot_sha_digest = _hash_sha256_values(snapshot_df["sha256"].tolist())
    itw_series = pd.to_datetime(snapshot_df["vt_first_seen_itw_date"], errors="coerce", utc=True)
    sub_series = pd.to_datetime(snapshot_df["vt_first_submission_at_utc"], errors="coerce", utc=True)
    eff_series = pd.to_datetime(snapshot_df["effective_first_seen_at_utc"], errors="coerce", utc=True)
    total_rows = max(len(snapshot_df), 1)
    itw_count = int(itw_series.notna().sum())
    fallback_count = int(((itw_series.isna()) & (sub_series.notna())).sum())
    eff_non_null = eff_series.dropna()
    earliest = eff_non_null.min().isoformat() if not eff_non_null.empty else ""
    latest = eff_non_null.max().isoformat() if not eff_non_null.empty else ""
    extracted_at_utc = datetime.now(timezone.utc).isoformat()
    meta_lines = [
        f"sample_count={len(snapshot_df)}\n",
        f"sha256={sample_id_digest}\n",
        f"sample_id_sha256={sample_id_digest}\n",
        f"snapshot_sha256_hash={snapshot_sha_digest}\n",
        f"snapshot_sha256_count={_count_non_empty_sha256(snapshot_df['sha256'])}\n",
        f"label_conflict_count={len(conflicts_df)}\n",
        f"selection_rule_version={selection_rule_version or 'snapshot_v1'}\n",
        "temporal_anchor_version=v1_itw_preferred_submission_fallback\n",
        f"pct_itw_available={round(itw_count / total_rows, 6)}\n",
        f"pct_submission_fallback={round(fallback_count / total_rows, 6)}\n",
        f"earliest_timestamp={earliest}\n",
        f"latest_timestamp={latest}\n",
        f"run_id={run_id or ''}\n",
        f"extracted_at_utc={extracted_at_utc}\n",
    ]
    meta_body = "".join(meta_lines)
    _emit_utf8_with_run_hygiene(
        primary=Path(meta_file),
        body=meta_body,
        global_latest_name="analysis_snapshot.latest.meta.txt",
    )

    du.print_info(
        f"[SNAPSHOT] Analysis snapshot exported:{du.format_console_path(snapshot_file)}"
    )
    du.print_info(
        f"[SNAPSHOT] Analysis snapshot metadata:{du.format_console_path(meta_file)}"
    )
    if conflict_file and os.path.exists(conflict_file):
        du.print_info(
            f"[SNAPSHOT] Label conflict quarantine:{du.format_console_path(conflict_file)}"
        )


def apply_cohort_lock(samples_df: pd.DataFrame, lock_file: str) -> pd.DataFrame:
    """Backward-compatible alias for analysis snapshot lock filtering."""
    fail_closed = bool(
        getattr(app_config, "REQUIRE_SNAPSHOT_LOCK_IN_EVIDENCE_MODE", True)
        and getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False)
    )
    return apply_analysis_snapshot_lock(
        samples_df=samples_df,
        lock_file=lock_file,
        fail_closed=fail_closed,
    )


def export_cohort_snapshot(samples_df: pd.DataFrame, snapshot_file: str, meta_file: str) -> None:
    """Backward-compatible alias for analysis snapshot export."""
    export_analysis_snapshot(
        samples_df=samples_df,
        snapshot_file=snapshot_file,
        meta_file=meta_file,
    )


def _sort_by_sample_id(df: pd.DataFrame) -> pd.DataFrame:
    if "sample_id" not in df.columns:
        return df
    return df.sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _normalize_ids(values: Iterable[object]) -> set[int]:
    normalized: set[int] = set()
    for value in values:
        try:
            if pd.isna(value):
                continue
            normalized.add(int(float(value)))
        except Exception:
            continue
    return normalized


def _hash_ids(ids: list[int]) -> str:
    encoded = ",".join(str(sample_id) for sample_id in ids).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _set_snapshot_lock_metadata(df: pd.DataFrame, payload: dict[str, object]) -> None:
    """Attach snapshot-lock metadata to a returned dataframe."""
    attrs = dict(getattr(df, "attrs", {}))
    attrs["snapshot_lock"] = dict(payload)
    df.attrs = attrs


def _inherit_dataframe_attrs(target: pd.DataFrame, source: pd.DataFrame) -> None:
    """Preserve attrs across pandas copy/filter/sort operations that drop them."""
    source_attrs = dict(getattr(source, "attrs", {}))
    if not source_attrs:
        return
    merged = dict(source_attrs)
    merged.update(dict(getattr(target, "attrs", {})))
    target.attrs = merged


def _hash_sha256_values(values: list[object]) -> str:
    normalized = [
        str(value).strip().lower()
        for value in values
        if str(value).strip().lower() and str(value).strip().lower() != "nan"
    ]
    normalized.sort()
    encoded = ",".join(normalized).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _count_non_empty_sha256(values: pd.Series) -> int:
    if values.empty:
        return 0
    normalized = values.fillna("").astype(str).str.strip().str.lower()
    return int((normalized != "").sum())


def _normalize_snapshot_fields(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    if "sha256" not in normalized.columns:
        normalized["sha256"] = ""
    normalized["sha256"] = normalized["sha256"].fillna("").astype(str).str.strip().str.lower()

    if "family_id" not in normalized.columns:
        normalized["family_id"] = -1
    normalized["family_id"] = pd.to_numeric(normalized["family_id"], errors="coerce").fillna(-1).astype(int)

    if "family_canonical" not in normalized.columns:
        normalized["family_canonical"] = ""
    normalized["family_canonical"] = (
        normalized["family_canonical"].fillna("").astype(str).str.strip()
    )

    if "family_name" not in normalized.columns:
        normalized["family_name"] = ""
    normalized["family_name"] = normalized["family_name"].fillna("").astype(str).str.strip()

    if "type_slug" not in normalized.columns:
        normalized["type_slug"] = "unknown"
    normalized["type_slug"] = (
        normalized["type_slug"].fillna("").astype(str).str.strip().str.lower()
    )
    normalized.loc[normalized["type_slug"] == "", "type_slug"] = "unknown"

    for column in (
        "category_primary",
        "category_subtype",
        "sample_label_kind",
        "family_label_raw",
        "vt_family_token",
        "source_batch_label",
    ):
        if column not in normalized.columns:
            normalized[column] = ""
        normalized[column] = normalized[column].fillna("").astype(str).str.strip()
        if column != "source_batch_label":
            normalized[column] = normalized[column].str.lower()

    if "vt_first_seen_itw_date" not in normalized.columns:
        normalized["vt_first_seen_itw_date"] = pd.NaT
    if "vt_first_submission_at_utc" not in normalized.columns:
        if "vt_first_submission_date" in normalized.columns:
            normalized["vt_first_submission_at_utc"] = normalized["vt_first_submission_date"]
        else:
            normalized["vt_first_submission_at_utc"] = pd.NaT
    normalized["vt_first_seen_itw_date"] = pd.to_datetime(
        normalized["vt_first_seen_itw_date"], errors="coerce", utc=True
    )
    normalized["vt_first_submission_at_utc"] = pd.to_datetime(
        normalized["vt_first_submission_at_utc"], errors="coerce", utc=True
    )
    normalized["effective_first_seen_at_utc"] = normalized["vt_first_seen_itw_date"].where(
        normalized["vt_first_seen_itw_date"].notna(),
        normalized["vt_first_submission_at_utc"],
    )
    normalized["effective_first_seen_year"] = normalized["effective_first_seen_at_utc"].dt.year.astype("Int64")
    normalized["effective_first_seen_month"] = normalized["effective_first_seen_at_utc"].dt.strftime("%Y-%m")
    normalized.loc[normalized["effective_first_seen_month"] == "NaT", "effective_first_seen_month"] = ""
    return normalized


def _build_sha256_label_conflicts(work_df: pd.DataFrame) -> pd.DataFrame:
    usable = work_df[work_df["sha256"].ne("")].copy()
    if usable.empty:
        return pd.DataFrame(
            columns=[
                "sha256",
                "sample_count",
                "sample_ids",
                "family_ids",
                "type_slugs",
                "conflict_reason",
            ]
        )

    grouped = usable.groupby("sha256", dropna=False)
    rows: list[dict[str, object]] = []
    for sha256, group in grouped:
        family_values = sorted({int(v) for v in group["family_id"].tolist()})
        type_values = sorted({str(v).strip().lower() for v in group["type_slug"].tolist()})
        has_family_conflict = len(family_values) > 1
        has_type_conflict = len(type_values) > 1
        if not has_family_conflict and not has_type_conflict:
            continue
        reasons: list[str] = []
        if has_family_conflict:
            reasons.append("family_id_conflict")
        if has_type_conflict:
            reasons.append("type_slug_conflict")
        rows.append(
            {
                "sha256": str(sha256),
                "sample_count": int(group["sample_id"].nunique()),
                "sample_ids": "|".join(str(v) for v in sorted(group["sample_id"].unique().tolist())),
                "family_ids": "|".join(str(v) for v in family_values),
                "type_slugs": "|".join(type_values),
                "conflict_reason": "|".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def _compute_snapshot_feature_hash(row: pd.Series) -> str:
    family_id = pd.to_numeric(pd.Series([row.get("family_id", -1)]), errors="coerce").fillna(-1).astype(int).iloc[0]
    tokens = [
        str(int(row.get("sample_id", 0))),
        str(row.get("sha256", "")).strip().lower(),
        str(family_id),
        str(row.get("family_canonical", "")).strip().lower(),
        str(row.get("type_slug", "")).strip().lower(),
        str(row.get("category_primary", "")).strip().lower(),
        str(row.get("category_subtype", "")).strip().lower(),
        str(row.get("sample_label_kind", "")).strip().lower(),
        str(row.get("family_label_raw", "")).strip().lower(),
        str(row.get("vt_family_token", "")).strip().lower(),
        str(row.get("source_batch_label", "")).strip(),
        str(row.get("effective_first_seen_at_utc", "")),
    ]
    encoded = "|".join(tokens).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _apply_optional_lock_constraints(
    samples_df: pd.DataFrame,
    lock_subset: pd.DataFrame,
) -> pd.DataFrame:
    if samples_df.empty or lock_subset.empty:
        return samples_df

    merged = samples_df.merge(
        lock_subset,
        on="sample_id",
        how="left",
        suffixes=("", "_lock"),
    )
    kept_mask = pd.Series(True, index=merged.index)

    if "sha256_lock" in merged.columns and "sha256" in merged.columns:
        lock_sha = merged["sha256_lock"].fillna("").astype(str).str.strip().str.lower()
        live_sha = merged["sha256"].fillna("").astype(str).str.strip().str.lower()
        sha_mismatch = (lock_sha != "") & (lock_sha != live_sha)
        if sha_mismatch.any():
            du.print_warning(
                f"[SNAPSHOT] Dropping {int(sha_mismatch.sum())} SHA256-mismatched locked sample(s)."
            )
            kept_mask = kept_mask & (~sha_mismatch)

    if "family_id_lock" in merged.columns and "family_id" in merged.columns:
        lock_family = pd.to_numeric(merged["family_id_lock"], errors="coerce")
        live_family = pd.to_numeric(merged["family_id"], errors="coerce")
        fam_mismatch = lock_family.notna() & live_family.notna() & (lock_family != live_family)
        if fam_mismatch.any():
            du.print_warning(
                f"[SNAPSHOT] Dropping {int(fam_mismatch.sum())} family-id-mismatched locked sample(s)."
            )
            kept_mask = kept_mask & (~fam_mismatch)

    keep_cols = [col for col in merged.columns if not col.endswith("_lock")]
    return merged.loc[kept_mask, keep_cols].copy()
