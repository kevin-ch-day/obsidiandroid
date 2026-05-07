"""Emit cohort foundation artifacts for self-service DB / profile reconciliation.

Artifacts under ``diagnostics/`` summarize **SQL profile scope** (database head counts from
``get_type_cohort_gate_stats``) versus the **prepared cohort** (the returned ``samples_df``).
See ``obsidiandroid.diagnostics.cohort_vocabulary`` for canonical manifest key names.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.database import db_config

from .cohort_vocabulary import KEY_COHORT_PREPARED_ROW_COUNT, KEY_COHORT_SQL_SCOPE_ROW_COUNT


COHORT_SOURCE_TABLES = (
    "malware_sample_catalog",
    "malware_artifact_hash_registry (ranked subquery)",
    "virustotal_sample_scan_summary (ranked subquery)",
    "v_android_apk_family_resolved (ranked subquery)",
    "android_malware_family",
    "android_malware_type",
)


def _pct(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round(100.0 * float(numer) / float(denom), 4)


def _family_shares(samples_df: pd.DataFrame, *, col: str = "family_canonical") -> dict[str, Any]:
    if col not in samples_df.columns or samples_df.empty:
        return {
            "family_count": 0,
            "type_count": 0,
            "top_family": "",
            "top_family_count": 0,
            "top_family_share_pct": 0.0,
            "top3_share_pct": 0.0,
            "top5_share_pct": 0.0,
            "family_distribution": {},
            "type_distribution": {},
        }
    total = int(len(samples_df))
    fc = samples_df[col].fillna("unknown").astype(str)
    vc = fc.value_counts()
    top = str(vc.index[0]) if len(vc) else ""
    top_n = int(vc.iloc[0]) if len(vc) else 0
    top3 = int(vc.head(3).sum()) if len(vc) else 0
    top5 = int(vc.head(5).sum()) if len(vc) else 0
    type_dist: dict[str, int] = {}
    if "type_slug" in samples_df.columns:
        type_dist = (
            samples_df["type_slug"].fillna("unknown").astype(str).value_counts().head(40).to_dict()
        )
    fam_dist = {str(k): int(v) for k, v in vc.head(50).items()}
    type_count = int(samples_df["type_slug"].nunique()) if "type_slug" in samples_df.columns else 0
    return {
        "family_count": int(vc.shape[0]),
        "type_count": type_count,
        "top_family": top,
        "top_family_count": top_n,
        "top_family_share_pct": _pct(top_n, total),
        "top3_share_pct": _pct(top3, total),
        "top5_share_pct": _pct(top5, total),
        "family_distribution": fam_dist,
        "type_distribution": {str(k): int(v) for k, v in type_dist.items()},
    }


def _low_support_families_retained(
    samples_df: pd.DataFrame,
    *,
    min_support_configured: int,
    family_col: str = "family_canonical",
) -> list[dict[str, Any]]:
    if family_col not in samples_df.columns or samples_df.empty:
        return []
    counts = samples_df.groupby(family_col, dropna=False).size()
    out: list[dict[str, Any]] = []
    for fam, cnt in counts.items():
        c = int(cnt)
        if c < int(min_support_configured):
            out.append({"family": str(fam), "rows_in_cohort": c, "below_threshold": int(min_support_configured)})
    out.sort(key=lambda x: x["rows_in_cohort"])
    return out


def _missing_vt_time_rate(samples_df: pd.DataFrame) -> float:
    sub = "vt_first_submission_date" if "vt_first_submission_date" in samples_df.columns else None
    itw = "vt_first_seen_itw_date" if "vt_first_seen_itw_date" in samples_df.columns else None
    eff = "effective_first_seen_at_utc" if "effective_first_seen_at_utc" in samples_df.columns else None
    if eff and eff in samples_df.columns:
        m = samples_df[eff].isna().sum()
        return _pct(int(m), len(samples_df))
    if sub and itw:
        m = (samples_df[sub].isna() & samples_df[itw].isna()).sum()
        return _pct(int(m), len(samples_df))
    if sub:
        m = samples_df[sub].isna().sum()
        return _pct(int(m), len(samples_df))
    return 0.0


def build_cohort_foundation_payload(
    *,
    run_id: str,
    profile_id: str,
    profile: dict[str, Any],
    gate_stats: dict[str, Any],
    samples_df: pd.DataFrame,
    time_contract: dict[str, Any],
    type_slug: str | None,
    min_samples_per_family_sql: int | None,
    configured_min_samples_per_family: int,
) -> dict[str, Any]:
    """Assemble JSON-serializable cohort foundation summary."""
    gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
    n = int(len(samples_df))
    sid_u = int(samples_df["sample_id"].nunique()) if "sample_id" in samples_df.columns else 0
    dup_surplus = max(0, n - sid_u)
    sha_u = int(samples_df["sha256"].nunique()) if "sha256" in samples_df.columns else 0
    pkg_missing = 0
    if "android_package_name" in samples_df.columns:
        pkg_missing = int(
            (samples_df["android_package_name"].fillna("").astype(str).str.strip() == "").sum()
        )
    shares = _family_shares(samples_df)
    low_sup = _low_support_families_retained(
        samples_df,
        min_support_configured=max(1, int(configured_min_samples_per_family)),
    )
    upstream_min = gates.get("upstream_expected_min_gate_total")
    env_min = os.environ.get("SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL", "").strip()
    upstream_min_i: int | None = None
    for candidate in (upstream_min, env_min or None):
        if candidate is None or str(candidate).strip() == "":
            continue
        try:
            upstream_min_i = int(candidate)
            break
        except (TypeError, ValueError):
            continue
    sql_scope_total = int(gate_stats.get("total_candidates", 0) or 0)
    interim_notes: list[str] = []
    if upstream_min_i is not None and sql_scope_total < upstream_min_i:
        interim_notes.append(
            f"Cohort SQL scope row count ({sql_scope_total}) is below expected minimum ({upstream_min_i}); "
            "the database snapshot may be incomplete or profile gates may exclude a large share — "
            "not a final paper cohort."
        )
        if profile_id == "research_all_malicious":
            interim_notes.append(
                "Current DB snapshot may be incomplete due to upstream Erebus reprocessing. "
                "Treat this run as pipeline validation, not final paper evidence."
            )

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        KEY_COHORT_SQL_SCOPE_ROW_COUNT: sql_scope_total,
        KEY_COHORT_PREPARED_ROW_COUNT: n,
        "run_id": run_id,
        "profile_id": profile_id,
        "primary_db_name": getattr(db_config, "DB_NAME", ""),
        "permission_intel_db_name": getattr(db_config, "PERMISSION_INTEL_DB_NAME", ""),
        "cohort_source_tables": list(COHORT_SOURCE_TABLES),
        "time_contract": {
            "enabled": time_contract.get("enabled"),
            "start_utc": time_contract.get("start_utc"),
            "end_utc": time_contract.get("end_utc"),
            "timestamp_field": time_contract.get("timestamp_field"),
            "require_effective_first_seen": time_contract.get("require_effective_first_seen"),
        },
        "type_slug_filter_effective": type_slug,
        "min_samples_per_family_configured": int(configured_min_samples_per_family),
        "min_samples_per_family_applied_in_sql": min_samples_per_family_sql is not None,
        "min_samples_per_family_sql_value": min_samples_per_family_sql,
        "gate_stats": {
            "total_candidates": int(gate_stats.get("total_candidates", 0) or 0),
            "excluded_unmapped_family": int(gate_stats.get("excluded_unmapped_family", 0) or 0),
            "excluded_unknown_type_slug": int(gate_stats.get("excluded_unknown_type_slug", 0) or 0),
            "excluded_missing_sha256": int(gate_stats.get("excluded_missing_sha256", 0) or 0),
            "excluded_missing_hash_registry": int(gate_stats.get("excluded_missing_hash_registry", 0) or 0),
            "excluded_missing_package_name": int(gate_stats.get("excluded_missing_package_name", 0) or 0),
            "excluded_low_support": int(gate_stats.get("excluded_low_support", 0) or 0),
            "governed_cohort_count_sql": int(gate_stats.get("governed_cohort_count", gate_stats.get("final_count_estimate", 0)) or 0),
            "final_count_estimate_sequential_legacy": gate_stats.get("final_count_estimate_sequential_legacy"),
        },
        "profile_excluded_family_canonical": list(gate_stats.get("excluded_family_canonical") or []),
        "loaded_dataframe": {
            "rows": n,
            "columns": int(samples_df.shape[1]),
            "distinct_sample_id": sid_u,
            "distinct_sha256": sha_u,
            "duplicate_sample_id_surplus": dup_surplus,
        },
        "missing_package_rate_pct": _pct(pkg_missing, n),
        "missing_vt_timestamp_rate_pct": _missing_vt_time_rate(samples_df),
        "family_type_summary": shares,
        "low_support_families_retained_in_cohort": low_sup[:200],
        "cohort_definition_notes": [
            "Prepared cohort: rows in samples_df after cohort SQL fetch plus in-Python dataset/time contract filters.",
            "gate_stats.total_candidates: SQL head count for the same profile scope (joins + time window + exclusions).",
            "Marginal exclusion buckets in gate_stats can overlap; trust governed_cohort_count_sql and loaded_dataframe.rows.",
            "min_samples_per_family applies in SQL only when type_slug_filter selects a single malware type.",
            "Final research totals may change until upstream Erebus ingestion finishes rebuilding.",
        ],
        "interim_rebuild_warnings": interim_notes,
    }
    return payload


def export_cohort_foundation_bundle(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    profile: dict[str, Any],
    gate_stats: dict[str, Any],
    samples_df: pd.DataFrame,
    time_contract: dict[str, Any],
    type_slug: str | None,
    min_samples_per_family_sql: int | None,
    configured_min_samples_per_family: int,
    artifact_list: list[str] | None = None,
) -> list[str]:
    """Write cohort_foundation.{json,md,csv} under diagnostics_dir. Returns written paths."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_cohort_foundation_payload(
        run_id=run_id,
        profile_id=profile_id,
        profile=profile,
        gate_stats=gate_stats,
        samples_df=samples_df,
        time_contract=time_contract,
        type_slug=type_slug,
        min_samples_per_family_sql=min_samples_per_family_sql,
        configured_min_samples_per_family=configured_min_samples_per_family,
    )
    paths: list[str] = []

    json_path = diagnostics_dir / "cohort_foundation.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    paths.append(str(json_path))

    counts_rows: list[dict[str, str]] = []
    for key, val in payload.get("gate_stats", {}).items():
        counts_rows.append({"metric": key, "value": str(val), "section": "cohort_sql_scope"})
    ld = payload.get("loaded_dataframe", {})
    for key, val in ld.items():
        counts_rows.append({"metric": f"loaded_{key}", "value": str(val), "section": "prepared_cohort"})
    counts_rows.append(
        {"metric": "missing_package_rate_pct", "value": str(payload.get("missing_package_rate_pct")), "section": "quality"}
    )
    counts_rows.append(
        {
            "metric": "missing_vt_timestamp_rate_pct",
            "value": str(payload.get("missing_vt_timestamp_rate_pct")),
            "section": "quality",
        }
    )
    ft = payload.get("family_type_summary", {})
    counts_rows.append({"metric": "family_count", "value": str(ft.get("family_count")), "section": "families"})
    counts_rows.append({"metric": "type_count", "value": str(ft.get("type_count")), "section": "families"})
    counts_rows.append({"metric": "top_family_share_pct", "value": str(ft.get("top_family_share_pct")), "section": "families"})

    counts_path = diagnostics_dir / "cohort_foundation_counts.csv"
    with counts_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["section", "metric", "value"])
        w.writeheader()
        w.writerows(counts_rows)
    paths.append(str(counts_path))

    schema_rows: list[dict[str, Any]] = []
    for col in samples_df.columns:
        ser = samples_df[col]
        schema_rows.append(
            {
                "column": col,
                "dtype": str(ser.dtype),
                "non_null_count": int(ser.notna().sum()),
                "null_count": int(ser.isna().sum()),
                "nunique": int(ser.nunique(dropna=True)),
            }
        )
    schema_path = diagnostics_dir / "cohort_foundation_schema.csv"
    with schema_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["column", "dtype", "non_null_count", "null_count", "nunique"],
        )
        w.writeheader()
        w.writerows(schema_rows)
    paths.append(str(schema_path))

    md_lines = [
        "# Cohort foundation (samples stage)",
        "",
        f"- **run_id:** `{run_id}`",
        f"- **profile_id:** `{profile_id}`",
        f"- **primary DB:** `{payload.get('primary_db_name')}`",
        "",
        "## Time contract",
        "",
        f"- start: `{payload.get('time_contract', {}).get('start_utc')}`",
        f"- end: `{payload.get('time_contract', {}).get('end_utc')}`",
        "",
        "## Database: cohort SQL scope (``gate_stats``)",
        "",
        f"- SQL profile scope (``total_candidates``): **{payload['gate_stats']['total_candidates']}**",
        f"- SQL governed row count (``governed_cohort_count_sql``): **{payload['gate_stats']['governed_cohort_count_sql']}**",
        f"- excluded_unmapped_family: {payload['gate_stats']['excluded_unmapped_family']}",
        f"- excluded_unknown_type_slug: {payload['gate_stats']['excluded_unknown_type_slug']}",
        f"- excluded_missing_sha256 / hash_registry: {payload['gate_stats']['excluded_missing_sha256']} / "
        f"{payload['gate_stats']['excluded_missing_hash_registry']}",
        "",
        "## Prepared cohort: loaded dataframe",
        "",
        f"- rows × columns: **{ld.get('rows')}** × **{ld.get('columns')}**",
        f"- distinct sample_id: {ld.get('distinct_sample_id')} (duplicate surplus {ld.get('duplicate_sample_id_surplus')})",
        f"- distinct sha256: {ld.get('distinct_sha256')}",
        "",
        "## What this cohort is / is not",
        "",
        *(f"- {note}" for note in payload.get("cohort_definition_notes", [])),
        "",
    ]
    warns = payload.get("interim_rebuild_warnings") or []
    if warns:
        md_lines.extend(["## Warnings", ""])
        md_lines.extend(f"- **{w}**" for w in warns)
        md_lines.append("")
    md_path = diagnostics_dir / "cohort_foundation.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    paths.append(str(md_path))

    if isinstance(artifact_list, list):
        artifact_list.extend(paths)
    return paths


def append_research_warnings_for_upstream_expectation(
    manifest_context: dict[str, Any],
    *,
    profile_id: str,
    sql_scope_row_count: int,
    gates: dict[str, Any],
) -> None:
    """Append pipeline research warnings when optional upstream min threshold is breached."""
    raw = gates.get("upstream_expected_min_gate_total")
    env_min = os.environ.get("SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL", "").strip()
    min_g: int | None = None
    for candidate in (raw, env_min or None):
        if candidate is None or str(candidate).strip() == "":
            continue
        try:
            min_g = int(candidate)
            break
        except (TypeError, ValueError):
            continue
    if min_g is None or sql_scope_row_count >= min_g:
        return
    msg = (
        f"cohort_sql_scope_row_count={sql_scope_row_count} is below expected minimum={min_g} "
        "(cohort_gates.upstream_expected_min_gate_total or SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL); "
        "the database snapshot may be incomplete or profile gates exclude a large share — not a final paper cohort."
    )
    rw = manifest_context.setdefault("_research_warning_messages", [])
    if isinstance(rw, list) and msg not in rw:
        rw.append(msg)
    if profile_id == "research_all_malicious":
        msg2 = (
            "Current DB snapshot may be incomplete due to upstream Erebus reprocessing. "
            "Treat this run as pipeline validation, not final paper evidence."
        )
        if isinstance(rw, list) and msg2 not in rw:
            rw.append(msg2)
