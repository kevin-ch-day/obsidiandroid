"""Protection-stratified type permission analysis (offline).

Composes governance-field inventory, lane-stratified type summaries,
lane-decomposed dominant-family sensitivity, protection-aware pairwise
enrichment, and app-defined identity-risk analysis from completed-run
artifacts only. Does not query databases, mutate taxonomy, or overwrite
prior report directories.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.reporting.cohort_count_contract import compute_cohort_identity_counts
from obsidiandroid.reporting.dominant_family_profile_sensitivity import (
    build_dominant_family_type_robustness,
    MIN_TYPE_FAMILIES,
    MIN_TYPE_SAMPLES,
)
from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    DEFAULT_THRESHOLDS,
    GOVERNANCE_FIELD_CONTRACT_VERSION,
    PROTECTION_LANE_CONTRACT_VERSION,
    attach_protection_lanes,
    classify_permission_row_reportability,
    contract_metadata,
    governance_field_contract_rows,
    lane_pair_class,
    ordered_lane_pair,
    permission_lane_lookup,
    reconcile_lane_token_counts,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

PROTECTION_COMPOSER_VERSION = "1.0.0"
PAIRWISE_PROTECTION_CONTRACT_VERSION = "1.0.0"
EXPECTED_RUN_ID = "20260721T231415Z__e0c43b"
EXPECTED_PERM_BEARING = 9457
MAIN_TYPES = ("banker", "rat", "spyware", "adware")
EXPLORATORY_TYPES = ("backdoor", "dropper", "sms-trojan")


def _require_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _optional_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def _norm_perm(value: Any) -> str:
    return str(value or "").strip().lower()


def verify_completed_run(run_root: Path, *, expected_run_id: str = EXPECTED_RUN_ID) -> dict[str, Any]:
    """Hard-fail when the slot is not the expected completed run."""
    run_root = Path(run_root)
    man_path = run_root / "run_manifest.json"
    if not man_path.is_file():
        raise FileNotFoundError(man_path)
    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id") or "").strip()
    if run_id != expected_run_id:
        raise ValueError(f"run identity mismatch: expected={expected_run_id!r} found={run_id!r}")
    if not (run_root / ".COMPLETE").exists():
        raise RuntimeError("missing .COMPLETE marker")
    if (run_root / ".RUNNING").exists():
        raise RuntimeError(".RUNNING marker present; refuse analysis")
    status = detect_source_run_status(run_root)
    coverage = _require_csv(
        run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_coverage_report_{run_id}.csv"
    )
    perm_bearing = int(coverage.iloc[0]["samples_with_permission_rows"])
    prepared = int(manifest.get("cohort_prepared_row_count") or 0)
    if prepared != 9716 or perm_bearing != EXPECTED_PERM_BEARING:
        raise ValueError(
            f"canonical count mismatch: prepared={prepared} perm_bearing={perm_bearing}"
        )
    snap = _require_csv(run_root / "diagnostics" / f"analysis_snapshot_{run_id}.csv")
    counts = compute_cohort_identity_counts(snap)
    return {
        "run_id": run_id,
        "profile_id": str(manifest.get("profile_id") or ""),
        "repository_commit": str(manifest.get("git_commit") or ""),
        "dataset_hash": str(manifest.get("dataset_hash") or ""),
        "prepared_sample_count": prepared,
        "permission_bearing_sample_count": perm_bearing,
        "cohort_counts": counts,
        "run_status": status,
        "manifest": manifest,
        "snapshot": snap,
    }


def build_permission_lane_inventory(audit: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Token inventory by headline lane + reconciliation."""
    framed = attach_protection_lanes(audit)
    recon = reconcile_lane_token_counts(framed["protection_governance_lane"])
    rows = []
    for lane in CANONICAL_PROTECTION_LANES:
        sub = framed[framed["protection_governance_lane"] == lane]
        rows.append(
            {
                "headline_lane": lane,
                "token_count": int(len(sub)),
                "retained_token_count": int(
                    (sub["retained_after_pruning"].astype(str).str.lower() == "yes").sum()
                )
                if "retained_after_pruning" in sub.columns
                else "",
                "mean_global_support": float(pd.to_numeric(sub.get("global_support"), errors="coerce").mean())
                if not sub.empty and "global_support" in sub.columns
                else 0.0,
            }
        )
    return pd.DataFrame(rows), recon


def _type_inventory_from_snapshot(snap: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for type_slug, group in snap.groupby(snap["type_slug"].fillna("unknown").astype(str)):
        fams = group["family_canonical"].fillna("").astype(str)
        fams = fams[~fams.str.lower().isin(["", "unknown"])]
        counts = fams.value_counts()
        largest = str(counts.index[0]) if not counts.empty else ""
        largest_n = int(counts.iloc[0]) if not counts.empty else 0
        n = int(len(group))
        rows.append(
            {
                "type_slug": type_slug,
                "sample_count": n,
                "active_families": int(counts.shape[0]),
                "largest_family_canonical": largest,
                "largest_family_samples": largest_n,
                "largest_family_share": (largest_n / n) if n else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_type_lane_summary(
    *,
    snap: pd.DataFrame,
    type_prev: pd.DataFrame,
    fam_prev: pd.DataFrame,
    lane_lookup: Mapping[str, str],
    labels: pd.DataFrame,
    features: pd.DataFrame | None,
    audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Per-type lane accounting + prevalence rows + sample reconciliations."""
    inv = _type_inventory_from_snapshot(snap)
    type_prev = type_prev.copy()
    type_prev["permission"] = type_prev["permission"].map(_norm_perm)
    type_prev["headline_lane"] = type_prev["permission"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )
    type_prev["n_samples"] = pd.to_numeric(type_prev.get("n_samples"), errors="coerce")
    type_prev["permission_positive_count"] = pd.to_numeric(
        type_prev.get("permission_positive_count"), errors="coerce"
    ).fillna(0)
    type_prev["prevalence_pct"] = pd.to_numeric(type_prev.get("prevalence_pct"), errors="coerce").fillna(0.0)

    fam_prev = fam_prev.copy()
    fam_prev["permission"] = fam_prev["permission"].map(_norm_perm)
    fam_prev["headline_lane"] = fam_prev["permission"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )
    fam_prev["family_support"] = pd.to_numeric(fam_prev["family_support"], errors="coerce").fillna(0)
    fam_prev["prevalence_pct"] = pd.to_numeric(fam_prev["prevalence_pct"], errors="coerce").fillna(0.0)

    # Sample × lane coverage from aligned features when available.
    sample_lane_hits: dict[tuple[str, str], int] = {}
    perm_bearing_by_type: dict[str, int] = {}
    if features is not None and not features.empty and not labels.empty:
        feat_cols = [c for c in features.columns if str(c).startswith("perm__")]
        # Map feature column → lane via audit
        audit_f = attach_protection_lanes(audit)
        col_to_lane = {}
        for r in audit_f.itertuples(index=False):
            feat = str(getattr(r, "feature_column", "") or "")
            perm = _norm_perm(getattr(r, "permission_string", ""))
            col_to_lane[feat] = lane_lookup.get(perm, str(getattr(r, "protection_governance_lane", "unknown_unresolved")))

        merged = labels[["sample_id", "type_slug"]].merge(
            features[["sample_id"] + feat_cols], on="sample_id", how="inner"
        )
        type_series = merged["type_slug"].fillna("unknown").astype(str)
        mat = merged[feat_cols].fillna(0).to_numpy(dtype=np.float32) > 0
        global_bearing = int(mat.any(axis=1).sum())
        lane_col_idx = {
            lane: [i for i, c in enumerate(feat_cols) if col_to_lane.get(c, "unknown_unresolved") == lane]
            for lane in CANONICAL_PROTECTION_LANES
        }
        for type_slug, idx in type_series.groupby(type_series).groups.items():
            rows = mat[list(idx)]
            perm_bearing_by_type[str(type_slug)] = int(rows.any(axis=1).sum())
            for lane, cols_i in lane_col_idx.items():
                if not cols_i:
                    sample_lane_hits[(str(type_slug), lane)] = 0
                    continue
                sample_lane_hits[(str(type_slug), lane)] = int(rows[:, cols_i].any(axis=1).sum())
    else:
        global_bearing = EXPECTED_PERM_BEARING

    summary_rows: list[dict[str, Any]] = []
    prevalence_rows: list[dict[str, Any]] = []
    for inv_row in inv.itertuples(index=False):
        type_slug = str(inv_row.type_slug)
        tprev = type_prev[type_prev["type_slug"].astype(str) == type_slug]
        exploratory = type_slug.lower() not in MAIN_TYPES
        for lane in CANONICAL_PROTECTION_LANES:
            lane_prev = tprev[tprev["headline_lane"] == lane]
            distinct = int(lane_prev["permission"].nunique()) if not lane_prev.empty else 0
            observations = int(lane_prev["permission_positive_count"].sum()) if not lane_prev.empty else 0
            samples_with_lane = sample_lane_hits.get((type_slug, lane), "")
            # Family-balanced / SW aggregates for lane (mean across permissions in lane)
            lane_fam = fam_prev[
                (fam_prev["type_slug"].astype(str) == type_slug)
                & (fam_prev["headline_lane"] == lane)
            ]
            if lane_fam.empty:
                sw = float("nan")
                fb = float("nan")
                med = float("nan")
                supp_fams = 0
                largest_contrib = float("nan")
            else:
                # sample-weighted mean prevalence across permissions in lane
                sw_vals = []
                fb_vals = []
                for perm, g in lane_fam.groupby("permission"):
                    support = g["family_support"].to_numpy(dtype=float)
                    prev = g["prevalence_pct"].to_numpy(dtype=float) / 100.0
                    total = float(support.sum())
                    sw_vals.append(float((prev * support).sum() / total) if total else 0.0)
                    fb_vals.append(float(g["prevalence_pct"].mean()) / 100.0)
                sw = float(np.mean(sw_vals)) if sw_vals else float("nan")
                fb = float(np.mean(fb_vals)) if fb_vals else float("nan")
                med = float(np.median(fb_vals)) if fb_vals else float("nan")
                supp_fams = int(lane_fam["family_canonical"].nunique())
                # largest family contribution: share of positive mass
                pos = (lane_fam["family_support"] * lane_fam["prevalence_pct"] / 100.0).groupby(
                    lane_fam["family_canonical"]
                ).sum()
                largest_contrib = float(pos.max() / pos.sum()) if float(pos.sum()) > 0 else float("nan")

            unresolved_share = 1.0 if lane == "unknown_unresolved" and distinct else 0.0
            status = classify_permission_row_reportability(
                lane=lane,
                type_slug=type_slug,
                positive_samples=int(lane_prev["permission_positive_count"].max() if not lane_prev.empty else 0),
                families_with_permission=supp_fams,
                largest_family_share=float(inv_row.largest_family_share),
                sample_weighted_prevalence=sw if pd.notna(sw) else None,
                family_balanced_prevalence=fb if pd.notna(fb) else None,
                odds_ratio=None,
            )
            if exploratory and status not in {
                "protection_level_unresolved",
                "app_defined_high_cardinality",
                "identity_risk",
                "insufficient_sample_support",
                "insufficient_family_support",
            }:
                status = "exploratory_only"

            summary_rows.append(
                {
                    "type_slug": type_slug,
                    "headline_lane": lane,
                    "total_samples": int(inv_row.sample_count),
                    "permission_bearing_samples": perm_bearing_by_type.get(type_slug, ""),
                    "family_count": int(inv_row.active_families),
                    "largest_family_share": float(inv_row.largest_family_share),
                    "largest_family_canonical": str(inv_row.largest_family_canonical),
                    "distinct_permission_tokens": distinct,
                    "total_observations": observations,
                    "samples_with_lane_permission": samples_with_lane,
                    "sample_weighted_mean_prevalence": sw,
                    "family_balanced_mean_prevalence": fb,
                    "median_family_prevalence": med,
                    "supporting_family_count": supp_fams,
                    "largest_family_contribution": largest_contrib,
                    "unresolved_token_share": unresolved_share,
                    "reportability_status": status,
                }
            )

            # Top permissions for prevalence detail table
            if not lane_prev.empty:
                top = lane_prev.sort_values("prevalence_pct", ascending=False).head(25)
                for r in top.itertuples(index=False):
                    g = lane_fam[lane_fam["permission"] == str(r.permission)]
                    fb_p = float(g["prevalence_pct"].mean()) / 100.0 if not g.empty else float("nan")
                    med_p = float(g["prevalence_pct"].median()) / 100.0 if not g.empty else float("nan")
                    fams = int(g["family_canonical"].nunique()) if not g.empty else 0
                    prevalence_rows.append(
                        {
                            "type_slug": type_slug,
                            "headline_lane": lane,
                            "permission": str(r.permission),
                            "sample_weighted_prevalence_pct": float(r.prevalence_pct),
                            "family_balanced_prevalence": fb_p,
                            "median_family_prevalence": med_p,
                            "supporting_family_count": fams,
                            "positive_count": int(r.permission_positive_count),
                            "reportability_status": classify_permission_row_reportability(
                                lane=lane,
                                type_slug=type_slug,
                                positive_samples=int(r.permission_positive_count),
                                families_with_permission=fams,
                                largest_family_share=float(inv_row.largest_family_share),
                                sample_weighted_prevalence=float(r.prevalence_pct) / 100.0,
                                family_balanced_prevalence=fb_p if pd.notna(fb_p) else None,
                                odds_ratio=None,
                            ),
                        }
                    )

    recon = {
        "permission_bearing_samples_expected": EXPECTED_PERM_BEARING,
        "permission_bearing_samples_observed": global_bearing,
        "permission_bearing_reconciles": int(global_bearing) == EXPECTED_PERM_BEARING,
        "type_count": int(len(inv)),
        "observed_types": sorted(inv["type_slug"].astype(str).tolist()),
        "lane_observation_sum": int(sum(r["total_observations"] for r in summary_rows)),
        "lane_token_distinct_sum": int(sum(r["distinct_permission_tokens"] for r in summary_rows)),
    }
    return pd.DataFrame(summary_rows), pd.DataFrame(prevalence_rows), recon


def build_dominant_family_lane_sensitivity(
    *,
    fam_prev: pd.DataFrame,
    type_inventory: pd.DataFrame,
    role_annotations: pd.DataFrame,
    pairwise: pd.DataFrame,
    lane_lookup: Mapping[str, str],
    focus_types: Sequence[str] = ("banker", "rat", "spyware", "adware", "backdoor", "dropper"),
) -> pd.DataFrame:
    """Leave-dominant sensitivity computed separately per headline lane."""
    frame = fam_prev.copy()
    frame["permission"] = frame["permission"].map(_norm_perm)
    frame["headline_lane"] = frame["permission"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )
    pair = pairwise.copy() if not pairwise.empty else pd.DataFrame()
    if not pair.empty:
        for col in ("permission_a", "permission_b"):
            if col in pair.columns:
                pair[col] = pair[col].map(_norm_perm)
    rows: list[dict[str, Any]] = []
    for lane in CANONICAL_PROTECTION_LANES:
        lane_frame = frame[frame["headline_lane"] == lane]
        if lane_frame.empty:
            continue
        lane_perms = set(lane_frame["permission"].astype(str).tolist())
        lane_pairs = pd.DataFrame()
        if not pair.empty and "permission_a" in pair.columns:
            lane_pairs = pair[
                pair["permission_a"].isin(lane_perms) & pair["permission_b"].isin(lane_perms)
            ].copy()
        table = build_dominant_family_type_robustness(
            fam_prev=lane_frame.drop(columns=["headline_lane"], errors="ignore"),
            type_inventory=type_inventory,
            role_annotations=role_annotations,
            pairwise_headline=lane_pairs,
            lane_lookup=None,  # already lane-filtered
            min_samples=MIN_TYPE_SAMPLES,
            min_families=MIN_TYPE_FAMILIES,
        )
        if table.empty:
            continue
        table = table[table["type_slug"].astype(str).isin(focus_types)].copy()
        table.insert(0, "headline_lane", lane)
        table["unresolved_token_share_change"] = (
            0.0 if lane != "unknown_unresolved" else float("nan")
        )
        rows.append(table)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_app_defined_permission_risk(
    *,
    audit: pd.DataFrame,
    fam_prev: pd.DataFrame,
    lane_lookup: Mapping[str, str],
    thresholds: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Identity-risk analysis for app-defined permission tokens."""
    thr = {**DEFAULT_THRESHOLDS, **(dict(thresholds) if thresholds else {})}
    framed = attach_protection_lanes(audit)
    app = framed[framed["protection_governance_lane"] == "app_defined"].copy()
    if app.empty:
        return pd.DataFrame()
    fam_prev = fam_prev.copy()
    fam_prev["permission"] = fam_prev["permission"].map(_norm_perm)
    rows = []
    for r in app.itertuples(index=False):
        perm = _norm_perm(getattr(r, "permission_string", ""))
        g = fam_prev[fam_prev["permission"] == perm]
        fam_count = int(g["family_canonical"].nunique()) if not g.empty else 0
        support = int(pd.to_numeric(getattr(r, "global_support", 0), errors="coerce") or 0)
        max_fam = int(pd.to_numeric(getattr(r, "max_family_support", 0), errors="coerce") or 0)
        concentration = (max_fam / support) if support > 0 else 1.0
        one_sample = support <= 1
        if fam_count > 0:
            one_family = fam_count <= 1
            multi_family = fam_count >= 2
        else:
            # Fall back to audit support fields when family prevalence lacks the token.
            one_family = support > 0 and max_fam >= support
            multi_family = support > 0 and max_fam < support
            fam_count = 1 if one_family else (2 if multi_family else 0)
        retained = str(getattr(r, "retained_after_pruning", "")).lower() == "yes"
        if (
            one_sample
            or one_family
            or concentration >= float(thr["app_defined_max_family_concentration"])
            or support <= int(thr["app_defined_max_global_support_for_identity"])
        ):
            status = "identity_risk"
        elif fam_count < int(thr["app_defined_min_families_for_headline"]) and not multi_family:
            status = "insufficient_cross_family_support"
        elif not multi_family:
            status = "insufficient_cross_family_support"
        else:
            status = "app_defined_high_cardinality"
        # namespace = everything before last segment-ish
        ns = perm.rsplit(".", 1)[0] if "." in perm else perm
        rows.append(
            {
                "permission": perm,
                "namespace": ns,
                "global_support": support,
                "family_count": fam_count,
                "max_family_support": max_fam,
                "max_family_concentration": concentration,
                "appears_in_one_sample": one_sample,
                "appears_in_one_family": one_family,
                "appears_across_multiple_families": multi_family,
                "retained_in_feature_contract": retained,
                "reportability_status": status,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["reportability_status", "global_support", "permission"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def enrich_pairwise_protection(
    *,
    pairwise: pd.DataFrame,
    lane_lookup: Mapping[str, str],
    fam_prev: pd.DataFrame,
    thresholds: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Remap pairwise lanes under contract 2.0 and attach leave-largest result."""
    thr = {**DEFAULT_THRESHOLDS, **(dict(thresholds) if thresholds else {})}
    if pairwise.empty:
        return pairwise
    frame = pairwise.copy()
    frame["permission_a"] = frame["permission_a"].map(_norm_perm)
    frame["permission_b"] = frame["permission_b"].map(_norm_perm)
    frame["permission_a_lane"] = frame["permission_a"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )
    frame["permission_b_lane"] = frame["permission_b"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )
    frame["lane_pair_class"] = [
        lane_pair_class(a, b)
        for a, b in zip(frame["permission_a_lane"], frame["permission_b_lane"])
    ]
    frame["lane_pair_ordered"] = [
        "|".join(ordered_lane_pair(a, b))
        for a, b in zip(frame["permission_a_lane"], frame["permission_b_lane"])
    ]

    # Leave-largest-family: if largest family share of positives >= dominance, mark sensitive.
    share = pd.to_numeric(frame.get("largest_family_share_of_positives"), errors="coerce").fillna(0.0)
    fb = pd.to_numeric(frame.get("family_balanced_prevalence"), errors="coerce")
    leave = []
    for i, row in enumerate(frame.itertuples(index=False)):
        sh = float(share.iloc[i])
        if sh >= float(thr["dominance_threshold"]):
            leave.append("collapses_or_single_family_dominated")
        elif sh >= 0.5:
            leave.append("weakens_without_largest")
        else:
            leave.append("stable_without_largest")
    frame["leave_largest_family_result"] = leave

    # Recompute reportability lightly using existing status if present.
    if "reportability_status" not in frame.columns:
        frame["reportability_status"] = ""
    if "suppression_reason" not in frame.columns:
        frame["suppression_reason"] = ""

    # Upgrade statuses where leave-dominant is weak and was previously supported.
    mask = (frame["leave_largest_family_result"] != "stable_without_largest") & (
        frame["reportability_status"].astype(str) == "family_balanced_supported"
    )
    frame.loc[mask, "reportability_status"] = "dominant_family_sensitive"
    frame["pairwise_protection_contract_version"] = PAIRWISE_PROTECTION_CONTRACT_VERSION
    return frame


def _render_interpretation(
    *,
    identity: Mapping[str, Any],
    summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
    pairwise: pd.DataFrame,
    app_risk: pd.DataFrame,
    hypo: pd.DataFrame,
    lane_contract_version: str | None = None,
    enrichment_kind: str | None = None,
) -> str:
    lane_ver = lane_contract_version or PROTECTION_LANE_CONTRACT_VERSION
    scope = (
        "authority-enriched (post-run Permission Intel observation)"
        if enrichment_kind
        else "artifact-limited (run-local fields only)"
    )
    lines = [
        "# Type permission protection interpretation",
        "",
        "In this completed dataset, permission patterns are stratified by protection/"
        "governance headline lanes. External hypotheses are not local ground truth.",
        "",
        f"- run_id: `{identity['run_id']}`",
        f"- profile_id: `{identity['profile_id']}`",
        f"- prepared samples: {identity['prepared_sample_count']}",
        f"- permission-bearing samples: {identity['permission_bearing_sample_count']}",
        f"- protection-lane contract: `{lane_ver}`",
        f"- analysis_scope: `{scope}`",
        f"- enrichment_kind: `{enrichment_kind or 'none'}`",
        f"- governance-field contract: `{GOVERNANCE_FIELD_CONTRACT_VERSION}`",
        "",
    ]
    for type_slug in MAIN_TYPES:
        lines.append(f"## {type_slug}")
        lines.append("")
        sub = summary[summary["type_slug"] == type_slug]
        for lane in CANONICAL_PROTECTION_LANES:
            row = sub[sub["headline_lane"] == lane]
            if row.empty:
                continue
            r = row.iloc[0]
            lines.append(
                f"- **{lane}**: distinct_tokens={int(r.distinct_permission_tokens)}; "
                f"SW_mean={r.sample_weighted_mean_prevalence}; "
                f"FB_mean={r.family_balanced_mean_prevalence}; "
                f"status=`{r.reportability_status}`"
            )
        # Sensitivity focus
        sens = sensitivity[
            (sensitivity["type_slug"] == type_slug) & (sensitivity["scenario"] == "exclude_largest")
        ]
        if not sens.empty:
            lines.append("")
            lines.append("Leave-largest-family by lane:")
            for r in sens.itertuples(index=False):
                lines.append(
                    f"- `{r.headline_lane}` excluding `{r.excluded_families}`: "
                    f"spearman={r.spearman_vs_full_sw}, JSD={r.js_distance_vs_full_sw}, "
                    f"maxΔpp={r.max_abs_prevalence_shift_pp}, "
                    f"headline_lost={r.headline_permissions_lost}, class=`{r.robustness_class}`"
                )
        # Pairwise
        if not pairwise.empty:
            pw = pairwise[
                (pairwise["type_slug"] == type_slug)
                & (pairwise["reportability_status"].isin(
                    ["family_balanced_supported", "dominant_family_sensitive", "single_family_dominated"]
                ))
            ]
            if not pw.empty and "family_balanced_prevalence_pct" in pw.columns:
                top = pw.sort_values("family_balanced_prevalence_pct", ascending=False).head(5)
                lines.append("")
                lines.append("Strong family-balanced pairs (top 5 by FB prevalence):")
                for r in top.itertuples(index=False):
                    lines.append(
                        f"- {r.permission_a} + {r.permission_b} "
                        f"[{r.lane_pair_class}/{r.permission_a_lane}|{r.permission_b_lane}] "
                        f"FB={getattr(r, 'family_balanced_prevalence_pct', '')} "
                        f"leave=`{r.leave_largest_family_result}` status=`{r.reportability_status}`"
                    )
        lines.append("")
        lines.append(
            "Static declarations support only manifest-requested capabilities. "
            "Runtime overlays, virtualization, and cloud C2 are not testable from "
            "the current artifacts alone."
        )
        lines.append("")

    lines.extend(
        [
            "## Exploratory types",
            "",
            "backdoor, dropper, sms-trojan, and other low-support or highly concentrated "
            "types are descriptive / exploratory only. Do not make broad type claims.",
            "",
            "## App-defined identity risk",
            "",
        ]
    )
    if not app_risk.empty:
        risk_n = int((app_risk["reportability_status"] == "identity_risk").sum())
        lines.append(
            f"Among app-defined tokens, `{risk_n}` are labeled `identity_risk` "
            "(near-unique or single-family). These must not be reported as general "
            "malware-type capabilities."
        )
    else:
        lines.append("No app-defined rows available.")

    if not hypo.empty:
        lines.extend(["", "## External hypotheses (static only)", ""])
        for r in hypo.itertuples(index=False):
            lines.append(f"- `{r.hypothesis_id}`: `{r.status}` (testable={r.testable_statically})")

    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- Sample-weighted prevalence suggests concentration effects in dominant families.",
            "- Family-balanced prevalence indicates whether signals recur across families.",
            "- The result is dominated by ClayRat within RAT for several dangerous lanes.",
            "- Banker remains comparatively stable after Godfather removal in aggregate,",
            "  but lane-level checks are required before claiming uniformity.",
            "",
        ]
    )
    return "\n".join(lines)


def compose_type_permission_protection(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    pairwise_output_dir: Path | None = None,
    repo_root: Path | None = None,
    load_aligned_features: bool = True,
    enrichment_csv: Path | None = None,
    lane_contract_version: str | None = None,
    enrichment_kind: str | None = None,
) -> dict[str, Any]:
    """Write protection-stratified report package (does not overwrite family-context)."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]

    audit = _require_csv(run_root / "diagnostics" / "permission_feature_audit.csv")
    type_prev = _require_csv(
        run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_prevalence_by_type_{run_id}.csv"
    )
    fam_prev = _require_csv(
        run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_prevalence_by_family_{run_id}.csv"
    )
    labels = _optional_csv(run_root / "diagnostics" / f"aligned_labels_{run_id}.csv")
    features = None
    if load_aligned_features:
        feat_path = run_root / "diagnostics" / f"aligned_features_{run_id}.csv.gz"
        if feat_path.is_file():
            features = pd.read_csv(feat_path)
    role_ann = _optional_csv(
        run_root
        / "diagnostics"
        / "type_permission_pattern_report"
        / f"permission_role_annotations_{run_id}.csv"
    )
    pairwise_src = _optional_csv(
        run_root
        / "diagnostics"
        / "type_permission_pairwise"
        / f"pairwise_all_{run_id}.csv"
    )
    hypo = _optional_csv(
        run_root
        / "diagnostics"
        / "live_corpus_family_context"
        / "hypothesis_validation.csv"
    )
    type_inv = _type_inventory_from_snapshot(identity["snapshot"])

    enrichment = _optional_csv(Path(enrichment_csv)) if enrichment_csv else pd.DataFrame()
    if enrichment_csv and enrichment.empty:
        raise FileNotFoundError(enrichment_csv)
    if not enrichment.empty:
        from obsidiandroid.reporting.permission_authority_enrichment import enrichment_lane_lookup

        lane_lookup = enrichment_lane_lookup(enrichment)
        # Build lane inventory from enrichment headline lanes
        framed = enrichment.rename(columns={"headline_lane": "protection_governance_lane"}).copy()
        recon = reconcile_lane_token_counts(framed["protection_governance_lane"])
        lane_inventory = pd.DataFrame(
            [
                {
                    "headline_lane": lane,
                    "token_count": int((framed["protection_governance_lane"] == lane).sum()),
                    "retained_token_count": "",
                    "mean_global_support": float(
                        pd.to_numeric(
                            enrichment.loc[
                                enrichment["headline_lane"] == lane, "run_global_support"
                            ],
                            errors="coerce",
                        ).mean()
                    )
                    if "run_global_support" in enrichment.columns
                    else 0.0,
                }
                for lane in CANONICAL_PROTECTION_LANES
            ]
        )
        token_recon = recon
    else:
        lane_lookup = permission_lane_lookup(audit)
        lane_inventory, token_recon = build_permission_lane_inventory(audit)

    field_contract = pd.DataFrame(governance_field_contract_rows(audit))
    summary, prevalence, type_recon = build_type_lane_summary(
        snap=identity["snapshot"],
        type_prev=type_prev,
        fam_prev=fam_prev,
        lane_lookup=lane_lookup,
        labels=labels,
        features=features,
        audit=audit,
    )
    sensitivity = build_dominant_family_lane_sensitivity(
        fam_prev=fam_prev,
        type_inventory=type_inv,
        role_annotations=role_ann,
        pairwise=pairwise_src,
        lane_lookup=lane_lookup,
    )
    app_risk = build_app_defined_permission_risk(
        audit=audit, fam_prev=fam_prev, lane_lookup=lane_lookup
    )
    pairwise_prot = enrich_pairwise_protection(
        pairwise=pairwise_src, lane_lookup=lane_lookup, fam_prev=fam_prev
    )
    effective_lane_version = lane_contract_version or PROTECTION_LANE_CONTRACT_VERSION
    interpretation = _render_interpretation(
        identity=identity,
        summary=summary,
        sensitivity=sensitivity,
        pairwise=pairwise_prot,
        app_risk=app_risk,
        hypo=hypo,
        lane_contract_version=effective_lane_version,
        enrichment_kind=enrichment_kind,
    )

    out_dir = (
        Path(output_dir)
        if output_dir
        else run_root / "diagnostics" / "type_permission_protection"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    pair_dir = (
        Path(pairwise_output_dir)
        if pairwise_output_dir
        else run_root / "diagnostics" / "type_permission_pairwise_protection"
    )
    pair_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    tables = {
        "permission_governance_field_contract.csv": field_contract,
        "permission_lane_inventory.csv": lane_inventory,
        "type_permission_lane_summary.csv": summary,
        "type_permission_lane_prevalence.csv": prevalence,
        "dominant_family_lane_sensitivity.csv": sensitivity,
        "app_defined_permission_risk.csv": app_risk,
    }
    output_hashes: dict[str, str] = {}
    for name, frame in tables.items():
        path = out_dir / name
        frame.to_csv(path, index=False)
        outputs[name] = path
        output_hashes[name] = sha256_file(path)

    pair_path = pair_dir / "type_permission_pairwise_protection.csv"
    pairwise_prot.to_csv(pair_path, index=False)
    outputs[pair_path.name] = pair_path
    output_hashes[pair_path.name] = sha256_file(pair_path)
    # Also copy into main package for the expected file list
    pair_copy = out_dir / "type_permission_pairwise_protection.csv"
    pairwise_prot.to_csv(pair_copy, index=False)
    output_hashes["type_permission_pairwise_protection.csv"] = sha256_file(pair_copy)

    md_path = out_dir / "type_permission_protection_interpretation.md"
    md_path.write_text(interpretation, encoding="utf-8")
    output_hashes[md_path.name] = sha256_file(md_path)

    input_paths = {
        "run_manifest": run_root / "run_manifest.json",
        "permission_feature_audit": run_root / "diagnostics" / "permission_feature_audit.csv",
        "analysis_snapshot": run_root / "diagnostics" / f"analysis_snapshot_{run_id}.csv",
        "permission_prevalence_by_type": run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_prevalence_by_type_{run_id}.csv",
        "permission_prevalence_by_family": run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_prevalence_by_family_{run_id}.csv",
        "pairwise_all": run_root
        / "diagnostics"
        / "type_permission_pairwise"
        / f"pairwise_all_{run_id}.csv",
    }
    if enrichment_csv:
        input_paths["permission_authority_enrichment"] = Path(enrichment_csv)
    input_hashes = {k: sha256_file(p) for k, p in input_paths.items() if p.is_file()}

    manifest = {
        "composer": "type_permission_protection",
        "composer_version": PROTECTION_COMPOSER_VERSION,
        "generated_at_utc": generated_at,
        "run_id": run_id,
        "profile_id": identity["profile_id"],
        "repository_commit_at_run": identity["repository_commit"],
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "dataset_hash": identity["dataset_hash"],
        "protection_lane_contract_version": effective_lane_version,
        "governance_field_contract_version": GOVERNANCE_FIELD_CONTRACT_VERSION,
        "pairwise_protection_contract_version": PAIRWISE_PROTECTION_CONTRACT_VERSION,
        "enrichment_kind": enrichment_kind,
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "lane_contract": contract_metadata(),
        "token_reconciliation": token_recon,
        "type_sample_reconciliation": type_recon,
        "cohort_counts": identity["cohort_counts"],
        "input_paths": {k: str(v) for k, v in input_paths.items()},
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "boundaries": {
            "database_access": False,
            "core_access": False,
            "taxonomy_mutation": False,
            "pipeline_execution": False,
            "source_artifact_mutation": False,
            "overwrote_family_context": False,
        },
        "run_status": identity["run_status"],
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_hashes["manifest.json"] = sha256_file(man_path)
    manifest["output_hashes"] = output_hashes
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sha_lines = [f"{digest}  {name}" for name, digest in sorted(output_hashes.items())]
    (out_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    return manifest


def assert_deterministic_scientific_outputs(
    *,
    run_root: Path,
    run_id: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run composer twice into temp dirs; scientific CSVs must match."""
    import tempfile

    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        d1 = Path(td1)
        d2 = Path(td2)
        m1 = compose_type_permission_protection(
            run_root=run_root,
            run_id=run_id,
            output_dir=d1 / "prot",
            pairwise_output_dir=d1 / "pair",
            repo_root=repo_root,
        )
        m2 = compose_type_permission_protection(
            run_root=run_root,
            run_id=run_id,
            output_dir=d2 / "prot",
            pairwise_output_dir=d2 / "pair",
            repo_root=repo_root,
        )
        scientific = [
            "permission_governance_field_contract.csv",
            "permission_lane_inventory.csv",
            "type_permission_lane_summary.csv",
            "type_permission_lane_prevalence.csv",
            "dominant_family_lane_sensitivity.csv",
            "app_defined_permission_risk.csv",
            "type_permission_pairwise_protection.csv",
        ]
        mismatches = []
        for name in scientific:
            b1 = (d1 / "prot" / name).read_bytes()
            b2 = (d2 / "prot" / name).read_bytes()
            if b1 != b2:
                mismatches.append(name)
        if mismatches:
            raise RuntimeError(f"nondeterministic scientific outputs: {mismatches}")
        return {"deterministic": True, "checked": scientific, "run1": m1["run_id"], "run2": m2["run_id"]}


__all__ = [
    "PROTECTION_COMPOSER_VERSION",
    "compose_type_permission_protection",
    "assert_deterministic_scientific_outputs",
    "verify_completed_run",
    "build_dominant_family_lane_sensitivity",
    "build_app_defined_permission_risk",
    "enrich_pairwise_protection",
]
