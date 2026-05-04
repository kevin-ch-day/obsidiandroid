#!/usr/bin/env python3
"""SELECT-only cohort / catalog reconciliation for Erebus rebuild monitoring.

Terminology (see ``analysis/diagnostics/cohort_vocabulary.py``): *raw hash+time* counts
catalog+registry rows under the time contract; *cohort SQL profile scope* matches
``gate_stats.total_candidates``; the governed SQL count matches the profile's conjunctive
cohort loader.

Example:
  python scripts/check_cohort_foundation.py --profile research_all_malicious
  python scripts/check_cohort_foundation.py --profile research_all_malicious --expected-raw-min 3000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_SRC = ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from database import db_engine
from database import db_sample_metadata_queries
from database.cohort_sql_fragments import latest_artifact_hash_registry_subquery
from database.db_sample_metadata_fetchers import _cohort_loader_sql_parts
import obsidiandroid.cli.profile_manager as profile_manager
from analysis.pipeline.sample_exports import resolve_dataset_time_contract


def _count_raw_android_apk_with_hash_and_time(
    *,
    time_start: str | None,
    time_end: str | None,
    require_ts: bool,
) -> int:
    """Android APK rows with hash-registry join + effective VT timestamp window (no taxonomy gates)."""
    hash_one = latest_artifact_hash_registry_subquery()
    ts = "COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc)"
    where = ["y.platform = 'android'", "y.file_extension = 'apk'"]
    params: list = []
    if require_ts:
        where.append(f"{ts} IS NOT NULL")
    if time_start:
        where.append(f"{ts} >= %s")
        params.append(time_start)
    if time_end:
        where.append(f"{ts} < %s")
        params.append(time_end)
    sql = f"""
        SELECT COUNT(*) AS c
        FROM malware_sample_catalog y
        JOIN {hash_one} x ON x.sha256 = y.sha256
        WHERE {" AND ".join(where)}
    """
    _cols, rows = db_engine.execute_query(sql, params=tuple(params), fetch=True, return_columns=True)
    return int(rows[0][0]) if rows else 0


def _governed_group_counts(
    parts: dict[str, Any],
    *,
    group_sql: str,
    limit: int,
) -> list[tuple[str, int]]:
    """GROUP BY distribution over the same governed WHERE as the cohort loader."""
    governed_where = " AND ".join(parts["where_clauses"])
    sql = f"""
        SELECT {group_sql} AS grp, COUNT(*) AS c
        FROM malware_sample_catalog y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["scan_one"]} s ON s.sample_id = y.sample_id
        LEFT JOIN {parts["fam_one"]} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {governed_where}
        GROUP BY grp
        ORDER BY c DESC
        LIMIT %s
    """
    params = tuple(list(parts["params"]) + [int(limit)])
    _cols, rows = db_engine.execute_query(sql, params=params, fetch=True, return_columns=True)
    out: list[tuple[str, int]] = []
    for row in rows or []:
        if not row:
            continue
        k = row[0]
        out.append((str(k) if k is not None else "", int(row[1] or 0)))
    return out


def _count_mapped_excluded_canonical_families(
    *,
    time_start: str | None,
    time_end: str | None,
    require_ts: bool,
    exclude_canonical: tuple[str, ...],
) -> int:
    """Rows mapped to excluded canonical family names before SQL exclusion (same join stack as gate stats)."""
    if not exclude_canonical:
        return 0
    from database.cohort_sql_fragments import (
        latest_family_resolution_subquery,
        latest_vt_scan_summary_subquery,
    )

    hash_one = latest_artifact_hash_registry_subquery()
    scan_one = latest_vt_scan_summary_subquery()
    fam_one = latest_family_resolution_subquery()
    ts = "COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc)"
    where = [
        "y.platform = 'android'",
        "y.file_extension = 'apk'",
        f"{ts} IS NOT NULL" if require_ts else "1=1",
    ]
    params: list = []
    if time_start:
        where.append(f"{ts} >= %s")
        params.append(time_start)
    if time_end:
        where.append(f"{ts} < %s")
        params.append(time_end)
    placeholders = ", ".join(["%s"] * len(exclude_canonical))
    where.append(f"LOWER(TRIM(f.family_name)) IN ({placeholders})")
    params.extend(exclude_canonical)
    sql = f"""
        SELECT COUNT(*) AS c
        FROM malware_sample_catalog y
        JOIN {hash_one} x ON x.sha256 = y.sha256
        LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
        LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {" AND ".join(where)}
    """
    _cols, rows = db_engine.execute_query(sql, params=tuple(params), fetch=True, return_columns=True)
    return int(rows[0][0]) if rows else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cohort foundation DB checks (SELECT-only).")
    parser.add_argument("--profile", required=True, help="Profile id or path under profiles/.")
    parser.add_argument(
        "--expected-raw-min",
        type=int,
        default=None,
        help="Warn when raw hash+time catalog count is below this threshold.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Optional path to write JSON summary.",
    )
    args = parser.parse_args()

    profile = profile_manager.load_profile(args.profile)
    profile_id = str(profile.get("profile_id", args.profile))
    gates = profile.get("cohort_gates", {}) if isinstance(profile.get("cohort_gates"), dict) else {}
    type_slug = profile.get("type_slug_filter")
    tc = resolve_dataset_time_contract(gates=gates, run_id="check_cohort_foundation")
    time_start = tc.get("start_utc")
    time_end = tc.get("end_utc")
    require_ts = bool(tc.get("require_effective_first_seen", True))
    exclude_families = tuple(
        str(x).strip().lower()
        for x in (gates.get("exclude_families") or [])
        if str(x).strip()
    )

    min_support_cfg = int(gates.get("min_samples_per_family", 3))
    min_support_sql = None if not type_slug else min_support_cfg

    stats = db_sample_metadata_queries.get_type_cohort_gate_stats(
        type_slug=type_slug,
        min_samples_per_family=min_support_sql,
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        exclude_unknown_type_slug=bool(gates.get("exclude_unknown_type_slug", False)),
        effective_time_start_utc=time_start,
        effective_time_end_utc=time_end,
        require_effective_first_seen=require_ts,
        exclude_family_canonical=exclude_families if exclude_families else None,
    )

    raw_catalog = _count_raw_android_apk_with_hash_and_time(
        time_start=time_start,
        time_end=time_end,
        require_ts=require_ts,
    )
    excluded_family_hits = _count_mapped_excluded_canonical_families(
        time_start=time_start,
        time_end=time_end,
        require_ts=require_ts,
        exclude_canonical=exclude_families,
    )

    parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_support_sql,
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        exclude_unknown_type_slug=bool(gates.get("exclude_unknown_type_slug", False)),
        effective_time_start_utc=time_start,
        effective_time_end_utc=time_end,
        require_effective_first_seen=require_ts,
        exclude_family_ids=None,
        exclude_family_canonical=exclude_families if exclude_families else None,
    )
    governed_sql = f"""
        SELECT COUNT(*) AS c /* check_cohort_foundation_governed */
        FROM malware_sample_catalog y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["scan_one"]} s ON s.sample_id = y.sample_id
        LEFT JOIN {parts["fam_one"]} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {" AND ".join(parts["where_clauses"])}
    """
    _c, grows = db_engine.execute_query(
        governed_sql,
        params=tuple(parts["params"]),
        fetch=True,
        return_columns=True,
    )
    governed_dup = int(grows[0][0]) if grows else 0

    type_dist = _governed_group_counts(
        parts,
        group_sql="COALESCE(NULLIF(TRIM(t.type_slug), ''), '(empty_type)')",
        limit=40,
    )
    family_dist = _governed_group_counts(
        parts,
        group_sql="COALESCE(NULLIF(TRIM(f.family_name), ''), '(unmapped_family_name)')",
        limit=50,
    )

    lines = [
        "=== Cohort foundation DB check ===",
        f"profile_id: {profile_id}",
        f"type_slug_filter: {type_slug!r}",
        f"time_window: {time_start!r} .. {time_end!r}",
        "",
        f"raw_android_apk_with_hash_registry_and_time_window: {raw_catalog}",
        f"cohort SQL profile scope (gate_stats.total_candidates): {stats.get('total_candidates')}",
        f"cohort SQL governed row count (gate_stats.governed_cohort_count): {stats.get('governed_cohort_count')}",
        f"governed_sql_recount: {governed_dup}",
        f"excluded_unmapped_family: {stats.get('excluded_unmapped_family')}",
        f"excluded_unknown_type_slug: {stats.get('excluded_unknown_type_slug')}",
        f"excluded_missing_sha256: {stats.get('excluded_missing_sha256')}",
        f"excluded_missing_hash_registry: {stats.get('excluded_missing_hash_registry')}",
        f"rows_mapped_to_profile_excluded_families (before SQL exclusion): {excluded_family_hits}",
        "",
        "type_distribution (governed SQL, top 40):",
    ]
    for name, cnt in type_dist:
        lines.append(f"  {name}: {cnt}")
    lines.extend(["", "family_distribution (governed SQL, top 50):", ""])
    for name, cnt in family_dist:
        lines.append(f"  {name}: {cnt}")
    lines.append("")

    threshold_msg = (
        "DB appears partially rebuilt or current profile gates are excluding large portions; "
        "do not treat this as final paper cohort."
    )
    warn: list[str] = []
    gate_tot = int(stats.get("total_candidates", 0) or 0)
    if args.expected_raw_min is not None:
        exp = int(args.expected_raw_min)
        if raw_catalog < exp or gate_tot < exp:
            detail = (
                f"(raw_hash_time={raw_catalog}, sql_profile_scope={gate_tot}, "
                f"--expected-raw-min={exp})"
            )
            warn.append(f"{threshold_msg} {detail}")
    if warn:
        lines.append("WARNINGS:")
        lines.extend(f"  - {w}" for w in warn)
        lines.append("")

    report = "\n".join(lines)
    print(report)

    payload = {
        "profile_id": profile_id,
        "type_slug_filter": type_slug,
        "time_contract": {"start_utc": time_start, "end_utc": time_end},
        "raw_android_apk_hash_time_count": raw_catalog,
        "gate_stats": stats,
        "governed_sql_recount": governed_dup,
        "excluded_family_rows_mapped_pre_sql": excluded_family_hits,
        "type_distribution_top": [{"type_slug": k, "count": c} for k, c in type_dist],
        "family_distribution_top": [{"family_name": k, "count": c} for k, c in family_dist],
        "warnings": warn,
    }
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
