"""Locked paper cohort materialization helpers.

Strict paper-locked runs must resolve membership from the immutable lock first,
then audit live DB drift around that frozen cohort. Current live SQL gates and
current taxonomy are useful for diagnostics, but they are not allowed to
silently redefine the locked benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.database import db_engine
from obsidiandroid.database import db_sample_metadata_queries
from obsidiandroid.governance.cohort_lock_manifest import load_lock_manifest, read_member_list
from obsidiandroid.governance.cohort_reproducibility import apply_analysis_snapshot_lock


UNKNOWN_TYPE_VALUES = {"", "unknown", "none", "null", "nan"}


@dataclass(frozen=True)
class LockedPaperMaterializationResult:
    """Materialized locked paper cohort plus emitted diagnostics."""

    samples_df: pd.DataFrame
    missing_locked_members_path: str
    label_drift_csv_path: str
    label_drift_summary_path: str
    label_drift_report_path: str
    archived_label_snapshot_available: bool
    archived_label_snapshot_status: str
    archived_label_snapshot_path: str
    archived_label_snapshot_hash: str


def materialize_locked_paper_cohort(
    *,
    profile: dict[str, Any],
    run_id: str,
    current_fetch_df: pd.DataFrame,
    snapshot_lock_file: str,
    diagnostics_dir: Path,
) -> LockedPaperMaterializationResult:
    """Resolve a locked paper cohort from the immutable lock before live SQL gates.

    Args:
        profile: Loaded profile dictionary containing ``paper_lock`` metadata.
        run_id: Active run identifier for artifact payloads.
        current_fetch_df: Current live SQL-governed cohort slice for drift auditing.
        snapshot_lock_file: Path to the canonical member-list CSV.
        diagnostics_dir: Run diagnostics directory for emitted artifacts.
    """

    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    raw_lock = profile.get("paper_lock", {}) if isinstance(profile.get("paper_lock"), dict) else {}
    manifest = load_lock_manifest(raw_lock) or {}
    lock_members = read_member_list(snapshot_lock_file)
    lock_ids = set(lock_members["sample_id"].astype(int).tolist())
    current_ids = _sample_id_set(current_fetch_df)

    broad_df = db_sample_metadata_queries.load_samples_by_type(
        type_slug=None,
        min_samples_per_family=None,
        require_mapped_family=False,
        require_sha256=False,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=False,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        limit=None,
        family_cap=None,
        family_cap_seed=None,
        type_cap=None,
        type_cap_seed=None,
        type_cap_by_slug=None,
        effective_time_start_utc=None,
        effective_time_end_utc=None,
        require_effective_first_seen=False,
        exclude_family_ids=None,
        exclude_family_canonical=None,
    )
    materialized_df = apply_analysis_snapshot_lock(
        broad_df,
        snapshot_lock_file,
        fail_closed=True,
    )
    live_label_df = materialized_df.copy()
    broad_ids = _sample_id_set(materialized_df)

    archived_label_df, archived_meta = _load_archived_label_snapshot(
        manifest=manifest,
        raw_lock=raw_lock,
    )
    if archived_label_df is not None:
        materialized_df = _apply_archived_labels(materialized_df, archived_label_df)

    missing_report_df = _build_missing_locked_members_report(
        lock_members=lock_members,
        broad_df=live_label_df,
        current_fetch_df=current_fetch_df,
        lock_source=str(raw_lock.get("sample_id_lock_source", "") or snapshot_lock_file),
        time_window=manifest.get("time_window", {}) if isinstance(manifest.get("time_window"), dict) else {},
    )
    missing_locked_members_path = diagnostics_dir / "missing_locked_members.csv"
    missing_report_df.to_csv(missing_locked_members_path, index=False)

    drift_df, drift_summary = _build_label_drift_report(
        lock_members=lock_members,
        materialized_df=materialized_df,
        live_label_df=live_label_df,
        current_fetch_ids=current_ids,
        manifest=manifest,
        archived_meta=archived_meta,
    )
    label_drift_csv_path = diagnostics_dir / "locked_paper_label_drift.csv"
    drift_df.to_csv(label_drift_csv_path, index=False)
    label_drift_summary_path = diagnostics_dir / "locked_paper_label_drift_summary.json"
    label_drift_summary_path.write_text(
        json.dumps(drift_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    label_drift_report_path = diagnostics_dir / "locked_paper_label_drift_report.md"
    label_drift_report_path.write_text(
        _render_label_drift_report_md(
            run_id=run_id,
            profile_id=str(profile.get("profile_id", "") or ""),
            summary=drift_summary,
            missing_locked_members_path=missing_locked_members_path,
            label_drift_csv_path=label_drift_csv_path,
        ),
        encoding="utf-8",
    )

    materialized_df.attrs["paper_locked_materialization"] = {
        "mode": "immutable_lock_first_broad_catalog_fetch",
        "lock_file_count": int(len(lock_members)),
        "materialized_count": int(len(materialized_df)),
        "current_fetch_sql_count": int(len(current_fetch_df)),
        "broad_catalog_match_count": int(len(live_label_df)),
        "excluded_by_current_fetch_sql_count": int((missing_report_df["excluded_by_current_fetch_sql"] == True).sum()),
        "missing_from_catalog_count": int((missing_report_df["missing_from_catalog"] == True).sum()),
        "missing_locked_members_csv": str(missing_locked_members_path),
        "label_drift_csv": str(label_drift_csv_path),
        "label_drift_summary_json": str(label_drift_summary_path),
        "label_drift_report_md": str(label_drift_report_path),
    }
    materialized_df.attrs["paper_locked_label_snapshot"] = {
        "status": archived_meta["status"],
        "available": bool(archived_meta["available"]),
        "path": str(archived_meta["path"]),
        "label_snapshot_hash": str(archived_meta["label_snapshot_hash"]),
        "taxonomy_hash": str(archived_meta["label_snapshot_hash"]),
    }
    materialized_df.attrs["paper_locked_current_live_labels"] = live_label_df
    materialized_df.attrs["paper_locked_current_fetch_sample_ids"] = sorted(current_ids)

    return LockedPaperMaterializationResult(
        samples_df=materialized_df,
        missing_locked_members_path=str(missing_locked_members_path),
        label_drift_csv_path=str(label_drift_csv_path),
        label_drift_summary_path=str(label_drift_summary_path),
        label_drift_report_path=str(label_drift_report_path),
        archived_label_snapshot_available=bool(archived_meta["available"]),
        archived_label_snapshot_status=str(archived_meta["status"]),
        archived_label_snapshot_path=str(archived_meta["path"]),
        archived_label_snapshot_hash=str(archived_meta["label_snapshot_hash"]),
    )


def _sample_id_set(df: pd.DataFrame) -> set[int]:
    if "sample_id" not in df.columns:
        return set()
    return set(pd.to_numeric(df["sample_id"], errors="coerce").dropna().astype(int).tolist())


def _normalize_sample_id_frame(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "sample_id" in work.columns:
        work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce")
        work = work.dropna(subset=["sample_id"])
        work["sample_id"] = work["sample_id"].astype(int)
    return work.sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _load_archived_label_snapshot(
    *,
    manifest: dict[str, Any],
    raw_lock: dict[str, Any],
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    baseline_root = Path(str(manifest.get("baseline_artifact_root", "") or "")).resolve() if str(
        manifest.get("baseline_artifact_root", "") or ""
    ).strip() else None
    path_candidates: list[Path] = []
    source_artifacts = manifest.get("source_artifacts", {}) if isinstance(manifest.get("source_artifacts"), dict) else {}
    raw_candidates = [
        manifest.get("label_snapshot_path"),
        raw_lock.get("label_snapshot_file"),
        raw_lock.get("label_snapshot_path"),
        source_artifacts.get("label_snapshot_csv"),
        source_artifacts.get("paper_label_snapshot_csv"),
        source_artifacts.get("analysis_snapshot_sample_csv"),
        source_artifacts.get("analysis_snapshot_csv"),
    ]
    for raw_path in raw_candidates:
        value = str(raw_path or "").strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute() and baseline_root is not None:
            path = baseline_root / path
        path_candidates.append(path.resolve())
    for candidate in path_candidates:
        if not candidate.exists():
            continue
        try:
            df = pd.read_csv(candidate)
        except Exception:
            continue
        normalized = _normalize_archived_label_snapshot(df)
        if normalized is None:
            continue
        return normalized, {
            "available": True,
            "status": "baseline_artifact_label_snapshot",
            "path": str(candidate),
            "label_snapshot_hash": _label_snapshot_hash(normalized),
        }

    historical_run_id = str(manifest.get("canonical_historical_run_id", "") or raw_lock.get("canonical_historical_run_id", "") or "").strip()
    if historical_run_id:
        warehouse_df = _load_archived_label_snapshot_from_warehouse(historical_run_id)
        if warehouse_df is not None and not warehouse_df.empty:
            normalized = _normalize_archived_label_snapshot(warehouse_df)
            if normalized is not None:
                return normalized, {
                    "available": True,
                    "status": "results_warehouse_analysis_snapshot_sample",
                    "path": f"analysis_snapshot_sample:{historical_run_id}",
                    "label_snapshot_hash": _label_snapshot_hash(normalized),
                }

    return None, {
        "available": False,
        "status": "archived_label_snapshot_unavailable",
        "path": "",
        "label_snapshot_hash": "",
    }


def _load_archived_label_snapshot_from_warehouse(run_id: str) -> pd.DataFrame | None:
    query = """
        SELECT sample_id, sha256, family_id, family_canonical, type_slug
        FROM analysis_snapshot_sample
        WHERE run_id = %s
    """
    try:
        with db_engine.database_connection() as conn:
            frame = pd.read_sql_query(query, conn, params=(run_id,))
    except Exception:
        return None
    return frame if isinstance(frame, pd.DataFrame) else None


def _normalize_archived_label_snapshot(df: pd.DataFrame) -> pd.DataFrame | None:
    required = {"sample_id", "family_canonical", "type_slug"}
    if not required.issubset(df.columns):
        return None
    work = df.copy()
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work.dropna(subset=["sample_id"])
    work["sample_id"] = work["sample_id"].astype(int)
    if "family_id" not in work.columns:
        work["family_id"] = pd.NA
    if "sha256" not in work.columns:
        work["sha256"] = ""
    keep = ["sample_id", "sha256", "family_id", "family_canonical", "type_slug"]
    return work[keep].drop_duplicates("sample_id").sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _label_snapshot_hash(df: pd.DataFrame) -> str:
    ordered = _normalize_archived_label_snapshot(df)
    if ordered is None:
        return ""
    records = []
    for _, row in ordered.iterrows():
        records.append(
            {
                "sample_id": int(row["sample_id"]),
                "family_id": None if pd.isna(row.get("family_id")) else int(row["family_id"]),
                "family_canonical": str(row.get("family_canonical", "") or "").strip(),
                "type_slug": str(row.get("type_slug", "") or "").strip().lower(),
            }
        )
    return hash_payload(records)


def _apply_archived_labels(samples_df: pd.DataFrame, archived_label_df: pd.DataFrame) -> pd.DataFrame:
    live = _normalize_sample_id_frame(samples_df)
    archived = _normalize_archived_label_snapshot(archived_label_df)
    assert archived is not None
    merged = live.merge(
        archived.rename(
            columns={
                "sha256": "archived_sha256",
                "family_id": "archived_family_id",
                "family_canonical": "archived_family_canonical",
                "type_slug": "archived_type_slug",
            }
        ),
        on="sample_id",
        how="left",
    )
    if "family_id" in merged.columns:
        merged["family_id"] = merged["archived_family_id"].combine_first(merged["family_id"])
    else:
        merged["family_id"] = merged["archived_family_id"]
    merged["family_canonical"] = merged["archived_family_canonical"].combine_first(merged["family_canonical"])
    merged["type_slug"] = merged["archived_type_slug"].combine_first(merged["type_slug"])
    merged = merged.drop(
        columns=[
            "archived_sha256",
            "archived_family_id",
            "archived_family_canonical",
            "archived_type_slug",
        ],
        errors="ignore",
    )
    return merged


def _build_missing_locked_members_report(
    *,
    lock_members: pd.DataFrame,
    broad_df: pd.DataFrame,
    current_fetch_df: pd.DataFrame,
    lock_source: str,
    time_window: dict[str, Any],
) -> pd.DataFrame:
    output_columns = [
        "sample_id",
        "sha256",
        "lock_source",
        "missing_reason",
        "missing_from_catalog",
        "excluded_by_current_fetch_sql",
        "outside_time_window",
        "missing_family",
        "missing_type",
        "missing_permissions",
        "missing_vt_summary",
        "current_family_canonical",
        "current_type_slug",
        "effective_first_seen_at_utc",
        "vt_first_seen_itw_date",
        "vt_first_submission_date",
    ]
    broad_lookup = _normalize_sample_id_frame(broad_df).set_index("sample_id", drop=False) if not broad_df.empty else pd.DataFrame()
    current_ids = _sample_id_set(current_fetch_df)
    rows: list[dict[str, Any]] = []
    for sample_id in lock_members["sample_id"].astype(int).tolist():
        live_row = broad_lookup.loc[sample_id] if sample_id in broad_lookup.index else None
        live_frame = live_row if isinstance(live_row, pd.Series) else None
        flags = _locked_member_flags(live_frame, time_window=time_window)
        present_in_catalog = live_frame is not None
        excluded_by_current_fetch_sql = present_in_catalog and sample_id not in current_ids
        record = {
            "sample_id": int(sample_id),
            "sha256": str(live_frame.get("sha256", "") or "") if live_frame is not None else "",
            "lock_source": str(lock_source),
            "missing_reason": _primary_missing_reason(
                missing_from_catalog=not present_in_catalog,
                excluded_by_current_fetch_sql=excluded_by_current_fetch_sql,
                **flags,
            ),
            "missing_from_catalog": bool(not present_in_catalog),
            "excluded_by_current_fetch_sql": bool(excluded_by_current_fetch_sql),
            **flags,
        }
        if live_frame is not None:
            record.update(
                {
                    "current_family_canonical": str(live_frame.get("family_canonical", "") or ""),
                    "current_type_slug": str(live_frame.get("type_slug", "") or ""),
                    "effective_first_seen_at_utc": str(live_frame.get("effective_first_seen_at_utc", "") or ""),
                    "vt_first_seen_itw_date": str(live_frame.get("vt_first_seen_itw_date", "") or ""),
                    "vt_first_submission_date": str(live_frame.get("vt_first_submission_date", "") or ""),
                }
            )
        else:
            record.update(
                {
                    "current_family_canonical": "",
                    "current_type_slug": "",
                    "effective_first_seen_at_utc": "",
                    "vt_first_seen_itw_date": "",
                    "vt_first_submission_date": "",
                }
            )
        if any(
            bool(record[key])
            for key in (
                "missing_from_catalog",
                "excluded_by_current_fetch_sql",
                "outside_time_window",
                "missing_family",
                "missing_type",
                "missing_permissions",
                "missing_vt_summary",
            )
        ):
            rows.append(record)
    if not rows:
        return pd.DataFrame(columns=output_columns)
    return pd.DataFrame(rows).sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _locked_member_flags(row: pd.Series | None, *, time_window: dict[str, Any]) -> dict[str, bool]:
    if row is None:
        return {
            "outside_time_window": False,
            "missing_family": False,
            "missing_type": False,
            "missing_permissions": False,
            "missing_vt_summary": False,
        }
    type_slug = str(row.get("type_slug", "") or "").strip().lower()
    family_values = [
        str(row.get("family_canonical", "") or "").strip(),
        str(row.get("family_id", "") or "").strip(),
    ]
    permissions = str(row.get("permissions", "") or "").strip()
    vt_status = str(row.get("vt_scan_status", "") or "").strip()
    vt_counts = [
        row.get("vt_malicious_count"),
        row.get("vt_suspicious_count"),
        row.get("vt_undetected_count"),
        row.get("vt_harmless_count"),
    ]
    effective_ts = pd.to_datetime(row.get("effective_first_seen_at_utc"), errors="coerce", utc=True)
    start_ts = pd.to_datetime(str(time_window.get("start_utc", "") or ""), errors="coerce", utc=True)
    end_ts = pd.to_datetime(str(time_window.get("end_utc", "") or ""), errors="coerce", utc=True)
    outside_time_window = False
    if pd.notna(effective_ts):
        if pd.notna(start_ts) and effective_ts < start_ts:
            outside_time_window = True
        if pd.notna(end_ts) and effective_ts >= end_ts:
            outside_time_window = True
    return {
        "outside_time_window": bool(outside_time_window),
        "missing_family": all(value == "" or value.lower() == "nan" for value in family_values),
        "missing_type": type_slug in UNKNOWN_TYPE_VALUES,
        "missing_permissions": permissions == "",
        "missing_vt_summary": vt_status == "" and all(pd.isna(value) for value in vt_counts),
    }


def _primary_missing_reason(
    *,
    missing_from_catalog: bool,
    excluded_by_current_fetch_sql: bool,
    outside_time_window: bool,
    missing_family: bool,
    missing_type: bool,
    missing_permissions: bool,
    missing_vt_summary: bool,
) -> str:
    if missing_from_catalog:
        return "missing_from_catalog"
    if outside_time_window:
        return "outside_time_window"
    if missing_family:
        return "missing_family"
    if missing_type:
        return "missing_type"
    if missing_permissions:
        return "missing_permissions"
    if missing_vt_summary:
        return "missing_vt_summary"
    if excluded_by_current_fetch_sql:
        return "excluded_by_current_fetch_sql"
    return "none"


def _build_label_drift_report(
    *,
    lock_members: pd.DataFrame,
    materialized_df: pd.DataFrame,
    live_label_df: pd.DataFrame,
    current_fetch_ids: set[int],
    manifest: dict[str, Any],
    archived_meta: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    archived_available = bool(archived_meta.get("available"))
    archived_lookup = _normalize_sample_id_frame(materialized_df).set_index("sample_id", drop=False)
    live_lookup = _normalize_sample_id_frame(live_label_df).set_index("sample_id", drop=False)
    rows: list[dict[str, Any]] = []
    family_transition_counts: dict[str, int] = {}
    type_transition_counts: dict[str, int] = {}
    family_changed = 0
    type_changed = 0
    excluded_by_current = 0
    for sample_id in lock_members["sample_id"].astype(int).tolist():
        archived_row = archived_lookup.loc[sample_id] if sample_id in archived_lookup.index else None
        live_row = live_lookup.loc[sample_id] if sample_id in live_lookup.index else None
        archived_series = archived_row if isinstance(archived_row, pd.Series) else None
        live_series = live_row if isinstance(live_row, pd.Series) else None
        archived_family = str(archived_series.get("family_canonical", "") or "") if archived_series is not None and archived_available else ""
        archived_type = str(archived_series.get("type_slug", "") or "") if archived_series is not None and archived_available else ""
        live_family = str(live_series.get("family_canonical", "") or "") if live_series is not None else ""
        live_type = str(live_series.get("type_slug", "") or "") if live_series is not None else ""
        family_changed_flag = bool(archived_available and archived_family != live_family)
        type_changed_flag = bool(archived_available and archived_type != live_type)
        excluded_flag = sample_id not in current_fetch_ids
        if family_changed_flag:
            family_changed += 1
            key = f"{archived_family} -> {live_family}"
            family_transition_counts[key] = family_transition_counts.get(key, 0) + 1
        if type_changed_flag:
            type_changed += 1
            key = f"{archived_type} -> {live_type}"
            type_transition_counts[key] = type_transition_counts.get(key, 0) + 1
        if excluded_flag:
            excluded_by_current += 1
        rows.append(
            {
                "sample_id": int(sample_id),
                "sha256": str(live_series.get("sha256", "") or archived_series.get("sha256", "") or "") if live_series is not None or archived_series is not None else "",
                "archived_family_canonical": archived_family,
                "current_live_family_canonical": live_family,
                "family_transition": f"{archived_family} -> {live_family}" if archived_available else "",
                "family_changed": family_changed_flag,
                "archived_type_slug": archived_type,
                "current_live_type_slug": live_type,
                "type_transition": f"{archived_type} -> {live_type}" if archived_available else "",
                "type_changed": type_changed_flag,
                "missing_from_current_fetch_sql": bool(excluded_flag),
            }
        )
    frame = pd.DataFrame(rows).sort_values("sample_id", kind="mergesort").reset_index(drop=True)
    summary = {
        "status": str(archived_meta.get("status", "")),
        "archived_label_snapshot_available": archived_available,
        "archived_label_snapshot_path": str(archived_meta.get("path", "")),
        "archived_label_snapshot_hash": str(archived_meta.get("label_snapshot_hash", "")),
        "expected_taxonomy_hash": str(manifest.get("taxonomy_hash", "") or ""),
        "lock_sample_count": int(len(lock_members)),
        "materialized_sample_count": int(len(materialized_df)),
        "family_changed_count": int(family_changed),
        "type_changed_count": int(type_changed),
        "currently_missing_from_current_fetch_sql_count": int(excluded_by_current),
        "family_transition_counts": dict(sorted(family_transition_counts.items())),
        "type_transition_counts": dict(sorted(type_transition_counts.items())),
    }
    return frame, summary


def _render_label_drift_report_md(
    *,
    run_id: str,
    profile_id: str,
    summary: dict[str, Any],
    missing_locked_members_path: Path,
    label_drift_csv_path: Path,
) -> str:
    lines = [
        "# Locked Paper Label Drift Report",
        "",
        f"- run_id: `{run_id}`",
        f"- profile_id: `{profile_id}`",
        f"- archived_label_snapshot_status: `{summary.get('status')}`",
        f"- archived_label_snapshot_available: `{summary.get('archived_label_snapshot_available')}`",
        f"- lock_sample_count: `{summary.get('lock_sample_count')}`",
        f"- materialized_sample_count: `{summary.get('materialized_sample_count')}`",
        f"- family_changed_count: `{summary.get('family_changed_count')}`",
        f"- type_changed_count: `{summary.get('type_changed_count')}`",
        f"- missing_from_current_fetch_sql_count: `{summary.get('currently_missing_from_current_fetch_sql_count')}`",
        f"- missing_locked_members_csv: `{missing_locked_members_path}`",
        f"- label_drift_csv: `{label_drift_csv_path}`",
    ]
    if summary.get("archived_label_snapshot_available"):
        lines.extend(
            [
                "",
                "## Top Transitions",
                "",
                f"- family_transition_counts: `{summary.get('family_transition_counts')}`",
                f"- type_transition_counts: `{summary.get('type_transition_counts')}`",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Status",
                "",
                "Archived paper label snapshot is unavailable in the current baseline bundle and results warehouse.",
                "Current live labels were retained only for drift auditing. Strict paper validation must fail until",
                "an archived label snapshot is restored for this lock version.",
            ]
        )
    return "\n".join(lines) + "\n"
