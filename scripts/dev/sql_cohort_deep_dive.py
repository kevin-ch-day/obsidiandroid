#!/usr/bin/env python3
"""Advanced SQL cohort analytics for canonical V3 profiles (live DB vs frozen runs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from obsidiandroid.cli.profile_manager import load_profile  # noqa: E402
from obsidiandroid.database import db_engine  # noqa: E402
from obsidiandroid.database.db_sample_metadata_fetchers import _cohort_loader_sql_parts  # noqa: E402
from obsidiandroid.pipeline.stage_samples import _resolve_dataset_time_contract  # noqa: E402


def _profile_loader_parts(profile_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = load_profile(profile_id)
    gates = profile.get("cohort_gates") or {}
    time_contract = _resolve_dataset_time_contract(gates=gates, run_id="sql_deep_dive")
    parts = _cohort_loader_sql_parts(
        type_slug=profile.get("type_slug_filter"),
        min_samples_per_family=gates.get("min_samples_per_family"),
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        exclude_unknown_type_slug=bool(gates.get("exclude_unknown_type_slug", False)),
        exclude_weak_label_kinds=bool(gates.get("exclude_weak_label_kinds", False)),
        exclude_family_label_conflicts=bool(gates.get("exclude_family_label_conflicts", False)),
        effective_time_start_utc=time_contract.get("start_utc"),
        effective_time_end_utc=time_contract.get("end_utc"),
        require_effective_first_seen=bool(time_contract.get("require_effective_first_seen", True)),
        include_family_canonical=tuple(gates.get("include_families") or ()),
        exclude_family_ids=tuple(gates.get("exclude_family_ids") or ()),
        exclude_family_canonical=tuple(gates.get("exclude_families") or ()),
    )
    return profile, parts


def _fetch_governed_frame(parts: dict[str, Any]) -> pd.DataFrame:
    governed_where = " AND ".join(parts["where_clauses"])
    sql = f"""
        SELECT
            y.sample_id,
            y.family_label,
            y.sample_label_kind,
            y.classification_primary AS category_primary,
            y.android_package_name,
            COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) AS effective_ts,
            f.family_id,
            f.family_name AS family_canonical,
            t.type_slug,
            v.resolved_family_lc,
            s.vt_malicious_count,
            s.vt_suspicious_count
        FROM malware_sample_catalog y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["scan_one"]} s ON s.sample_id = y.sample_id
        LEFT JOIN {parts["fam_one"]} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {governed_where}
    """
    return db_engine.execute_query(
        sql,
        params=tuple(parts["params"]),
        fetch=True,
        as_dataframe=True,
    )


def _classification_lane(df: pd.DataFrame) -> pd.Series:
    primary = df["category_primary"].fillna("").astype(str).str.strip().str.lower()
    benign = primary.str.contains("benign|clean|harmless|safe", regex=True)
    malicious = primary.str.contains("malicious|trojan|threat|risk|suspicious", regex=True)
    vt_pos = (df["vt_malicious_count"].fillna(0) + df["vt_suspicious_count"].fillna(0)) >= 1
    lane = pd.Series("other_lane", index=df.index, dtype="object")
    lane[benign] = "benign_primary_label"
    lane[malicious & ~benign] = "malicious_primary_label"
    lane[vt_pos & ~(benign | malicious)] = "vt_positive_no_malicious_primary"
    lane[df["vt_malicious_count"].isna() & df["vt_suspicious_count"].isna()] = "no_scan_summary"
    return lane


def _concentration_metrics(df: pd.DataFrame) -> dict[str, Any]:
    fam = (
        df.loc[df["family_id"].notna(), "family_canonical"]
        .astype(str)
        .value_counts()
        .sort_values(ascending=False)
    )
    total = int(fam.sum()) if not fam.empty else 0
    if total <= 0 or fam.empty:
        return {}
    top_family = str(fam.index[0])
    top_n = int(fam.iloc[0])
    return {
        "top_family": top_family,
        "top_family_count": top_n,
        "top_family_share_pct": round(100.0 * top_n / total, 4),
        "top3_share_pct": round(100.0 * fam.head(3).sum() / total, 4),
        "top5_share_pct": round(100.0 * fam.head(5).sum() / total, 4),
        "trainable_family_classes_ge1": int(len(fam)),
        "benchmark_eligible_families_n_ge_3": int((fam >= 3).sum()),
        "sub_threshold_families_n_lt_3": int((fam < 3).sum()),
        "rows_in_sub_threshold_families": int(fam[fam < 3].sum()),
    }


def _frozen_cohort_foundation(slot: str) -> dict[str, Any]:
    path = REPO_ROOT / "output" / "runs" / slot / "diagnostics" / "cohort_foundation.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _permission_coverage(sample_ids: set[int]) -> dict[str, Any]:
    if not sample_ids:
        return {"governed_rows": 0, "rows_with_permission_obs": 0, "coverage_pct": 0.0}
    pi_all = db_engine.execute_permission_query(
        "SELECT DISTINCT sample_id FROM android_permission_obs_sample",
        fetch=True,
        as_dataframe=True,
    )
    perm_rows = 0
    if pi_all is not None and not pi_all.empty:
        perm_rows = sum(1 for x in pi_all["sample_id"].dropna().tolist() if int(x) in sample_ids)
    governed_rows = len(sample_ids)
    return {
        "governed_rows": governed_rows,
        "rows_with_permission_obs": perm_rows,
        "coverage_pct": round(100.0 * perm_rows / governed_rows, 2) if governed_rows else 0.0,
    }


def analyze_profile(profile_id: str, *, slot: str) -> dict[str, Any]:
    _profile, parts = _profile_loader_parts(profile_id)
    df = _fetch_governed_frame(parts)
    frozen = _frozen_cohort_foundation(slot)
    fts = frozen.get("family_type_summary") or {}

    if df is None or df.empty:
        return {"profile_id": profile_id, "slot": slot, "error": "governed cohort empty"}

    df = df.copy()
    df["classification_lane"] = _classification_lane(df)
    df["effective_year"] = pd.to_datetime(df["effective_ts"], errors="coerce", utc=True).dt.year

    weak_kinds = {"filename", "hash_like", "opaque_string", "unclassified"}
    raw = df["family_label"].fillna("").astype(str).str.strip().str.lower()
    canon = df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    conflict_mask = (
        raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"}) == False  # noqa: E712
    ) & (
        canon.isin({"", "unknown", "other", "unmapped", "none", "null"}) == False  # noqa: E712
    ) & (raw != canon)

    fam_counts = (
        df.loc[df["family_id"].notna(), "family_canonical"]
        .astype(str)
        .value_counts()
    )
    boundary = (
        fam_counts[(fam_counts >= 2) & (fam_counts <= 4)]
        .reset_index()
        .rename(columns={"index": "family_canonical", "family_canonical": "family_canonical", 0: "n"})
    )
    if "count" in boundary.columns:
        boundary = boundary.rename(columns={"count": "n"})

    top_pairs = (
        df.groupby([df["family_canonical"].fillna("<unmapped>"), df["type_slug"].fillna("<none>")], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values("row_count", ascending=False)
        .head(20)
    )

    out: dict[str, Any] = {
        "profile_id": profile_id,
        "slot": slot,
        "governed_summary": {
            "governed_rows": int(len(df)),
            "family_id_classes": int(df["family_id"].nunique(dropna=True)),
            "family_name_classes": int(df["family_canonical"].nunique(dropna=True)),
            "type_classes": int(df["type_slug"].nunique(dropna=True)),
            "missing_family_id_rows": int(df["family_id"].isna().sum()),
            "benign_primary_rows": int((df["classification_lane"] == "benign_primary_label").sum()),
            "malicious_primary_rows": int((df["classification_lane"] == "malicious_primary_label").sum()),
            "vt_positive_unlabeled_primary_rows": int(
                (df["classification_lane"] == "vt_positive_no_malicious_primary").sum()
            ),
            "missing_package_rows": int(df["android_package_name"].fillna("").astype(str).str.strip().eq("").sum()),
            "weak_label_kind_rows": int(df["sample_label_kind"].astype(str).isin(weak_kinds).sum()),
        },
        "concentration": _concentration_metrics(df),
        "top_family_type_pairs": top_pairs.to_dict(orient="records"),
        "type_distribution": (
            df["type_slug"].fillna("<none>").astype(str).value_counts().reset_index()
            .rename(columns={"index": "type_slug", "type_slug": "type_slug", "count": "row_count"})
            .to_dict(orient="records")
        ),
        "weak_label_hotspots": (
            df.loc[df["sample_label_kind"].astype(str).isin(weak_kinds)]
            .groupby([df["family_canonical"].fillna("<unmapped>"), "sample_label_kind"])
            .size()
            .reset_index(name="row_count")
            .sort_values("row_count", ascending=False)
            .head(15)
            .to_dict(orient="records")
        ),
        "raw_vs_canonical_conflicts": int(conflict_mask.sum()),
        "support_boundary_families_n2_to_n4": boundary.to_dict(orient="records"),
        "permission_obs_coverage": _permission_coverage({int(x) for x in df["sample_id"].dropna().tolist()}),
        "frozen_compare": {
            "frozen_prepared_rows": frozen.get("cohort_prepared_row_count"),
            "frozen_family_count": fts.get("family_count"),
            "frozen_type_count": fts.get("type_count"),
            "frozen_top_family": fts.get("top_family"),
            "frozen_top_family_share_pct": fts.get("top_family_share_pct"),
            "frozen_top5_share_pct": fts.get("top5_share_pct"),
        },
    }

    if profile_id == "android_malware_all_current":
        godfather = (
            df.loc[df["family_canonical"].astype(str).str.lower() == "godfather"]
            .groupby(["sample_label_kind", "classification_lane"])
            .size()
            .reset_index(name="row_count")
            .sort_values("row_count", ascending=False)
            .to_dict(orient="records")
        )
        out["godfather_label_vt_breakdown"] = godfather
        buckets = fam_counts.reset_index()
        buckets.columns = ["family_canonical", "n"]
        out["family_support_buckets"] = [
            {
                "support_bucket": "benchmark_eligible",
                "family_count": int((buckets["n"] >= 3).sum()),
                "row_count": int(buckets.loc[buckets["n"] >= 3, "n"].sum()),
            },
            {
                "support_bucket": "below_n3",
                "family_count": int((buckets["n"] < 3).sum()),
                "row_count": int(buckets.loc[buckets["n"] < 3, "n"].sum()),
            },
        ]

    if profile_id == "android_malware_major_families":
        out["year_distribution"] = (
            df["effective_year"].dropna().astype(int).value_counts().sort_index()
            .reset_index()
            .rename(columns={"index": "effective_year", "effective_year": "effective_year", "count": "row_count"})
            .to_dict(orient="records")
        )

    live_gov = int(len(df))
    frozen_gov = int(
        (frozen.get("gate_stats") or {}).get("governed_cohort_count_sql")
        or (frozen.get("cohort_attrition") or {}).get("governed_sql_total")
        or 0
    )
    out["drift"] = {"live_governed_sql": live_gov, "frozen_governed_sql": frozen_gov, "delta": live_gov - frozen_gov}
    return out


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-id",
        action="append",
        default=[],
        help="Profile to analyze (default: both canonical profiles).",
    )
    args = parser.parse_args()
    targets = args.profile_id or [
        "android_malware_all_current",
        "android_malware_major_families",
    ]
    slot_by_profile = {
        "android_malware_all_current": "allcurrent_diagnostic",
        "android_malware_major_families": "majorfam_benchmark",
    }
    analyses = [
        analyze_profile(pid, slot=slot_by_profile.get(pid, pid.replace("android_malware_", "") + "_diagnostic"))
        for pid in targets
    ]
    print(json.dumps({"analyses": analyses}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
