"""Offline package-balanced permission sensitivity analysis.

This module consumes only completed-run artifacts.  Package identity is an
accounting key, not a malware-lineage assertion; missing package values are
kept separate and cross-family/type collisions are never auto-merged.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.pipeline.permission_trends.stats_core import js_distance
from obsidiandroid.reporting.dominant_family_profile_sensitivity import spearman_rank_corr
from obsidiandroid.reporting.permission_authority_enrichment import enrichment_lane_lookup
from obsidiandroid.reporting.permission_governance_lanes import DEFAULT_THRESHOLDS
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

PACKAGE_BALANCED_COMPOSER_VERSION = "1.0.0"
PACKAGE_KEY_CONTRACT_VERSION = "1.0.0"
WEIGHTING_CONTRACT_VERSION = "1.0.0"
LINEAGE_BALANCE_UNAVAILABLE = "lineage_balance_unavailable"
DEEP_DIVE_FAMILIES = (
    "ClayRat", "Godfather", "ArsinkRAT", "Devixor", "Gigabud", "Nexus",
    "Joker", "Triada", "Irata", "SpyNote", "PixPirate", "SMSSpy",
    "SaferRat", "Applite",
)
CONCENTRATION_THRESHOLDS = {
    "BROAD_MIN_PACKAGES": 50, "BROAD_MIN_RATIO": 0.70,
    "BROAD_MAX_LARGEST_SHARE": 0.10, "HIGH_LARGEST_SHARE": 0.50,
    "HIGH_HHI": 0.25, "SINGLE_LARGEST_SHARE": 0.85,
    "INSUFFICIENT_KNOWN_SHARE": 0.50, "INSUFFICIENT_MIN_PACKAGES": 3,
    "INSUFFICIENT_MIN_SAMPLES": 30,
    "WEIGHTING_SENSITIVE_DELTA_PP": 20.0,
}
BANNED_OUTPUT_DIRS = {
    "permission_authority_enrichment", "type_permission_protection",
    "type_permission_protection_enriched", "live_corpus_family_context",
    "type_permission_pairwise", "type_permission_pairwise_protection",
    "type_permission_pairwise_protection_enriched",
}


def normalize_package_name(value: Any) -> str:
    """Return the contract package key: trimmed and lower-cased."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip().lower()
    return "" if text in {"", "nan", "none", "null", "(null)"} else text


def assign_package_keys(labels: pd.DataFrame) -> pd.DataFrame:
    """Attach normalized package keys; each missing package gets a synthetic key."""
    out = labels.copy()
    source = out.get("package_name", pd.Series("", index=out.index))
    if "android_package_name" in out.columns:
        source = source.where(source.map(normalize_package_name).ne(""), out["android_package_name"])
    normalized = source.map(normalize_package_name)
    sample_ids = out.get("sample_id", pd.Series(out.index.astype(str), index=out.index)).astype(str)
    out["is_missing_package"] = normalized.eq("")
    out["package_key"] = normalized.where(~out["is_missing_package"],
                                         "__missing_package__:" + sample_ids)
    out["package_key_hash"] = out["package_key"].map(
        lambda value: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    )
    return out


def classify_package_collision(
    *, family_count: int, type_count: int, batch_count: int = 0,
    sha_count: int = 0, is_missing_package: bool = False,
) -> str:
    """Classify package-key reuse without making a lineage inference."""
    if is_missing_package:
        return "unknown_identity"
    if family_count > 1:
        return "cross_family_collision"
    if type_count > 1:
        return "cross_type_collision"
    if sha_count > 1 and batch_count > 1:
        return "likely_repackaging"
    if sha_count > 1:
        return "same_family_multi_sample"
    return "unable_to_interpret"


def compute_hhi(counts: Sequence[float] | pd.Series) -> float:
    """Compute package concentration HHI from non-negative counts."""
    values = np.asarray(counts, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    total = float(values.sum())
    return float(np.square(values / total).sum()) if total else 0.0


def effective_package_count(counts: Sequence[float] | pd.Series) -> float:
    """Return inverse-HHI effective package count."""
    hhi = compute_hhi(counts)
    return float(1.0 / hhi) if hhi else 0.0


def classify_package_concentration_state(
    *, sample_count: int, known_package_count: int, known_package_samples: int,
    largest_package_share: float, hhi: float, conflicted: bool = False,
    thresholds: Mapping[str, Any] | None = None,
) -> str:
    """Apply the package concentration state contract in precedence order."""
    t = {**CONCENTRATION_THRESHOLDS, **(dict(thresholds or {}))}
    if conflicted:
        return "package_identity_conflicted"
    if known_package_count <= 1 or largest_package_share >= t["SINGLE_LARGEST_SHARE"]:
        return "single_package_dominated"
    known_share = known_package_samples / sample_count if sample_count else 0.0
    if (known_share < t["INSUFFICIENT_KNOWN_SHARE"] or
            (sample_count >= t["INSUFFICIENT_MIN_SAMPLES"] and
             known_package_count < t["INSUFFICIENT_MIN_PACKAGES"])):
        return "insufficient_package_identity"
    ratio = known_package_count / known_package_samples if known_package_samples else 0.0
    if (known_package_count >= t["BROAD_MIN_PACKAGES"] and ratio >= t["BROAD_MIN_RATIO"]
            and largest_package_share < t["BROAD_MAX_LARGEST_SHARE"]):
        return "broad_package_diversity"
    if largest_package_share >= t["HIGH_LARGEST_SHARE"] or hhi >= t["HIGH_HHI"]:
        return "high_package_concentration"
    return "moderate_package_concentration"


def _indicator(frame: pd.DataFrame, permission: str) -> pd.Series:
    return pd.to_numeric(frame.get(permission, pd.Series(0, index=frame.index)), errors="coerce").fillna(0).gt(0)


def sample_weighted_prevalence(frame: pd.DataFrame, permission: str) -> float:
    return float(_indicator(frame, permission).mean()) if len(frame) else float("nan")


def package_balanced_prevalence(frame: pd.DataFrame, permission: str) -> float:
    known = frame[~frame["is_missing_package"].astype(bool)]
    if known.empty:
        return float("nan")
    return float(_indicator(known, permission).groupby(known["package_key"]).mean().mean())


def family_balanced_prevalence(frame: pd.DataFrame, permission: str) -> float:
    if frame.empty or "family_canonical" not in frame:
        return float("nan")
    valid = frame[frame["family_canonical"].fillna("").astype(str).str.strip().ne("")]
    return float(_indicator(valid, permission).groupby(valid["family_canonical"]).mean().mean()) if len(valid) else float("nan")


def package_within_family_balanced_prevalence(frame: pd.DataFrame, permission: str) -> float:
    known = frame[~frame["is_missing_package"].astype(bool)].copy()
    known = known[known["family_canonical"].fillna("").astype(str).str.strip().ne("")]
    if known.empty:
        return float("nan")
    per_package = _indicator(known, permission).groupby(
        [known["family_canonical"], known["package_key"]]
    ).mean()
    return float(per_package.groupby(level=0).mean().mean())


def build_identity_grouping_field_contract(labels: pd.DataFrame) -> pd.DataFrame:
    """Describe run-local identity fields and their permitted analysis use."""
    n = len(labels)
    catalog = [
        ("aligned_labels", "sample_id", "Unique prepared-cohort sample identity", "local_run", "yes", "Not malware lineage", True),
        ("aligned_labels", "sha256", "Sample content hash", "local_run", "accounting_only", "Do not print in headline Markdown", False),
        ("aligned_labels", "package_name", "Preferred Android package identity", "local_run", "package_key_source", "Not malware lineage; collisions possible", True),
        ("aligned_labels", "android_package_name", "Fallback package identity", "local_run", "package_key_fallback", "Not malware lineage", True),
        ("aligned_labels", "observed_filename", "Observed filename when present", "local_run", "descriptive_only", "Not a package or lineage key", False),
        ("aligned_labels", "family_id", "Governed family identifier", "local_run", "family_grouping", "Do not invent lineage", True),
        ("aligned_labels", "family_canonical", "Governed family canonical label", "local_run", "family_grouping", "Not package lineage", True),
        ("aligned_labels", "type_slug", "Governed malware type slug", "local_run", "type_grouping", "Not package lineage", True),
        ("aligned_labels", "source_batch_label", "Collection/source batch label", "local_run", "source_batch_grouping", "Not lineage", True),
        ("run_artifacts", "package_lineage_id", "Explicit governed package lineage ID", "absent", "unavailable", "Do not infer lineage", False),
        ("run_artifacts", "apk_signing_certificate_identity", "APK signing certificate identity", "absent", "unavailable", "Do not invent from package names", False),
    ]
    rows = []
    for source, field, meaning, authority, safe_use, unsafe, headline in catalog:
        present = field in labels.columns
        if present:
            s = labels[field]
            if s.dtype == object:
                empty = s.isna() | s.fillna("").astype(str).str.strip().eq("")
                null_rate = float(empty.mean()) if n else 0.0
                uniq = int(s[~empty].astype(str).nunique())
            else:
                null_rate = float(s.isna().mean()) if n else 0.0
                uniq = int(s.nunique(dropna=True))
        else:
            null_rate, uniq = 1.0, 0
        rows.append({
            "source_artifact": source, "field_name": field, "meaning": meaning,
            "present_in_aligned_labels": bool(present), "null_rate": null_rate, "uniqueness": uniq,
            "authority_level": authority, "safe_grouping_use": safe_use,
            "unsafe_interpretation": unsafe,
            "suitable_for_headline_analysis": bool(headline and present),
            "lineage_claim_permitted": False,
        })
    return pd.DataFrame(rows)


def build_package_collision_audit(labels: pd.DataFrame) -> pd.DataFrame:
    """Return hashed-key collision accounting; raw package keys are never exported."""
    keyed = assign_package_keys(labels)
    rows = []
    for key, group in keyed.groupby("package_key", sort=True):
        family_count = int(group.get("family_canonical", pd.Series("", index=group.index)).fillna("").astype(str).nunique())
        type_count = int(group.get("type_slug", pd.Series("", index=group.index)).fillna("").astype(str).nunique())
        batch_count = int(group.get("source_batch_label", pd.Series("", index=group.index)).fillna("").astype(str).nunique())
        sha_count = int(group.get("sha256", group["sample_id"]).fillna("").astype(str).nunique())
        missing = bool(group["is_missing_package"].iloc[0])
        families = sorted({str(x) for x in group.get("family_canonical", pd.Series(dtype=str)).fillna("").astype(str) if str(x)})
        types = sorted({str(x) for x in group.get("type_slug", pd.Series(dtype=str)).fillna("").astype(str) if str(x)})
        rows.append({
            "package_key_hash": hashlib.sha256(str(key).encode("utf-8")).hexdigest(),
            "sample_count": int(len(group)), "family_count": family_count, "type_count": type_count,
            "batch_count": batch_count, "sha_count": sha_count, "is_missing_package": missing,
            "affected_families": "|".join(families[:12]),
            "affected_types": "|".join(types[:12]),
            "collision_class": classify_package_collision(
                family_count=family_count, type_count=type_count, batch_count=batch_count,
                sha_count=sha_count, is_missing_package=missing),
        })
    return pd.DataFrame(rows).sort_values(["collision_class", "package_key_hash"]).reset_index(drop=True)


def _concentration(groups: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    keyed = assign_package_keys(groups)
    rows = []
    for values, group in keyed.groupby(dimensions, dropna=False, sort=True):
        values = values if isinstance(values, tuple) else (values,)
        known = group[~group["is_missing_package"]]
        counts = known["package_key"].value_counts()
        n = len(group); known_n = len(known)
        largest = float(counts.max() / known_n) if known_n else 0.0
        if len(known):
            fam_per_pkg = known.groupby("package_key")["family_canonical"].nunique()
            typ_per_pkg = known.groupby("package_key")["type_slug"].nunique()
            conflict = bool((fam_per_pkg > 1).any() or (typ_per_pkg > 1).any())
        else:
            conflict = False
        row = dict(zip(dimensions, values))
        top3 = float(counts.iloc[:3].sum() / known_n) if known_n and len(counts) else 0.0
        hhi = compute_hhi(counts)
        batch_share = 0.0
        batch_count = 0
        if "source_batch_label" in group.columns and n:
            bc = group["source_batch_label"].fillna("").astype(str)
            vc = bc[bc.ne("")].value_counts()
            batch_count = int(len(vc))
            batch_share = float(vc.iloc[0] / n) if len(vc) else 0.0
        row.update({"sample_count": n, "permission_bearing_sample_count": n,
                    "known_package_samples": known_n,
                    "missing_package_samples": n - known_n,
                    "missing_package_share": float((n - known_n) / n) if n else 0.0,
                    "known_package_count": int(len(counts)),
                    "samples_per_known_package": float(known_n / len(counts)) if len(counts) else float("nan"),
                    "median_samples_per_package": float(counts.median()) if len(counts) else float("nan"),
                    "max_samples_per_package": float(counts.max()) if len(counts) else 0.0,
                    "package_count_to_sample_count_ratio": float(len(counts) / known_n) if known_n else 0.0,
                    "largest_package_sample_share": largest,
                    "largest_package_share": largest,
                    "top_three_package_sample_share": top3,
                    "package_hhi": hhi,
                    "normalized_hhi": float(hhi) if len(counts) <= 1 else float((hhi - 1.0 / len(counts)) / (1.0 - 1.0 / len(counts))),
                    "effective_package_count": effective_package_count(counts),
                    "source_batch_count": batch_count,
                    "largest_source_batch_share": batch_share,
                    "package_collision_count": int(conflict),
                    "has_cross_group_collision": conflict})
        row["concentration_state"] = classify_package_concentration_state(
            sample_count=n, known_package_count=int(len(counts)), known_package_samples=known_n,
            largest_package_share=largest, hhi=hhi, conflicted=conflict)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(dimensions).reset_index(drop=True) if rows else pd.DataFrame()


def build_family_package_concentration(labels: pd.DataFrame) -> pd.DataFrame:
    return _concentration(labels, ["family_canonical"])


def build_type_package_concentration(labels: pd.DataFrame) -> pd.DataFrame:
    return _concentration(labels, ["type_slug"])


def _weighting_row(frame: pd.DataFrame, permission: str) -> dict[str, Any]:
    sw = sample_weighted_prevalence(frame, permission)
    pb = package_balanced_prevalence(frame, permission)
    fb = family_balanced_prevalence(frame, permission)
    pwf = package_within_family_balanced_prevalence(frame, permission)
    vals = [v for v in (pb, fb, pwf) if pd.notna(v)]
    known = frame[~frame["is_missing_package"]]
    positives_by_package = _indicator(known, permission).groupby(known["package_key"]).sum() if len(known) else pd.Series(dtype=float)
    positive_total = float(positives_by_package.sum())
    return {
        "sample_weighted_prevalence": sw, "package_balanced_prevalence": pb,
        "family_balanced_prevalence": fb, "package_within_family_balanced_prevalence": pwf,
        "lineage_balanced_prevalence": LINEAGE_BALANCE_UNAVAILABLE,
        "max_scheme_delta_pp": max((abs(sw - v) * 100 for v in vals), default=float("nan")),
        "supporting_samples": int(len(frame)),
        "supporting_known_packages": int(known["package_key"].nunique()),
        "supporting_families": int(frame.get("family_canonical", pd.Series("", index=frame.index)).nunique()),
        "largest_package_contribution": (
            float(positives_by_package.max() / positive_total) if positive_total else float("nan")
        ),
    }


def _status(concentration: str, delta: float) -> str:
    if concentration in {"package_identity_conflicted", "insufficient_package_identity",
                         "single_package_dominated"}:
        return concentration
    if pd.isna(delta) or delta >= 0.20:
        return "sample_duplication_sensitive"
    if concentration == "high_package_concentration":
        return "package_concentration_driven"
    return "package_balanced_supported"


def build_permission_weighting_comparison(
    *, membership: pd.DataFrame, type_prevalence: pd.DataFrame, family_prevalence: pd.DataFrame,
    lane_lookup: Mapping[str, str] | None = None, deep_dive_families: Sequence[str] = DEEP_DIVE_FAMILIES,
    type_concentration: pd.DataFrame | None = None, family_concentration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Reweight frozen type rows and selected family rows from feature indicators."""
    keyed = assign_package_keys(membership) if "package_key" not in membership.columns else membership
    lane_lookup = lane_lookup or {}
    type_state = {}
    if type_concentration is not None and not type_concentration.empty:
        type_state = dict(zip(type_concentration["type_slug"].astype(str), type_concentration["concentration_state"].astype(str)))
    fam_state = {}
    if family_concentration is not None and not family_concentration.empty:
        fam_state = dict(zip(family_concentration["family_canonical"].astype(str), family_concentration["concentration_state"].astype(str)))
    rows = []
    # Cache membership slices once per group to avoid repeated filtering.
    type_slices = {str(k): v for k, v in keyed.groupby(keyed["type_slug"].astype(str), sort=False)}
    fam_slices = {str(k): v for k, v in keyed.groupby(keyed["family_canonical"].astype(str), sort=False)}
    sources = [(type_prevalence, "type")]
    if not family_prevalence.empty:
        sources.append((family_prevalence[family_prevalence["family_canonical"].isin(deep_dive_families)], "family"))
    for table, scope in sources:
        for record in table.itertuples(index=False):
            perm = str(getattr(record, "permission", "")).strip().lower()
            group_name = str(getattr(record, "type_slug" if scope == "type" else "family_canonical", ""))
            sub = type_slices.get(group_name, pd.DataFrame()) if scope == "type" else fam_slices.get(group_name, pd.DataFrame())
            if sub.empty or not perm or perm not in keyed.columns:
                continue
            row = _weighting_row(sub, perm)
            if scope == "type":
                state = type_state.get(group_name) or "insufficient_package_identity"
            else:
                state = fam_state.get(group_name) or "insufficient_package_identity"
            row.update({"analysis_scope": scope, "type_slug": str(getattr(record, "type_slug", "")),
                        "family_canonical": str(getattr(record, "family_canonical", "")),
                        "permission": perm, "headline_lane": lane_lookup.get(perm, "unknown_unresolved"),
                        "package_concentration_state": state,
                        "reportability_status": _status(state, float(row["max_scheme_delta_pp"]) / 100.0)})
            rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["rank_sample_weighted"] = out.groupby(["analysis_scope", "type_slug"])["sample_weighted_prevalence"].rank(
        method="min", ascending=False)
    out["rank_package_balanced"] = out.groupby(["analysis_scope", "type_slug"])["package_balanced_prevalence"].rank(
        method="min", ascending=False)
    out["rank_shift_vs_sample_weighted"] = out["rank_package_balanced"] - out["rank_sample_weighted"]
    return out.sort_values(["analysis_scope", "type_slug", "family_canonical", "permission"]).reset_index(drop=True)


def build_pairwise_weighting_comparison(
    *,
    membership: pd.DataFrame,
    pairwise: pd.DataFrame,
    type_concentration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Reweight only the frozen pair universe; never mine new pairs."""
    if pairwise.empty:
        return pd.DataFrame()
    keyed = assign_package_keys(membership) if "package_key" not in membership.columns else membership
    type_state = {}
    if type_concentration is not None and not type_concentration.empty:
        type_state = dict(
            zip(type_concentration["type_slug"].astype(str), type_concentration["concentration_state"].astype(str))
        )

    # Cache type slices and binary matrices once.
    type_cache: dict[str, dict[str, Any]] = {}
    for typ, sub in keyed.groupby(keyed["type_slug"].astype(str), sort=False):
        known = sub[~sub["is_missing_package"].astype(bool)]
        type_cache[str(typ)] = {"all": sub, "known": known}

    rows: list[dict[str, Any]] = []
    for pair in pairwise.itertuples(index=False):
        typ = str(getattr(pair, "type_slug", ""))
        a = str(getattr(pair, "permission_a", "")).strip().lower()
        b = str(getattr(pair, "permission_b", "")).strip().lower()
        state = type_state.get(typ, "insufficient_package_identity")
        base = {
            "type_slug": typ,
            "permission_a": a,
            "permission_b": b,
            "artifact_reportability_status": str(getattr(pair, "reportability_status", "")),
            "package_concentration_state": state,
        }
        cache = type_cache.get(typ)
        if cache is None or a not in keyed.columns or b not in keyed.columns:
            base.update(
                {
                    "reportability_transition": "insufficient_package_identity"
                    if state == "insufficient_package_identity"
                    else "exploratory_only",
                    "suppression_reason": "missing_feature_columns_for_pair",
                }
            )
            rows.append(base)
            continue
        sub = cache["all"]
        known = cache["known"]
        ia = sub[a].fillna(0).astype(float).gt(0)
        ib = sub[b].fillna(0).astype(float).gt(0)
        both = ia & ib
        sw = float(both.mean()) if len(sub) else float("nan")
        # package-balanced pair prevalence over known packages
        if len(known):
            both_known = both.loc[known.index]
            pb = float(both_known.groupby(known["package_key"]).mean().mean())
            fam = known["family_canonical"].fillna("").astype(str)
            valid = fam.ne("")
            if valid.any():
                per_pkg = both_known[valid].groupby([fam[valid], known.loc[valid, "package_key"]]).mean()
                pwf = float(per_pkg.groupby(level=0).mean().mean())
                fb = float(both.groupby(sub["family_canonical"]).mean().mean())
            else:
                pwf = float("nan")
                fb = float("nan")
        else:
            pb = float("nan")
            fb = float("nan")
            pwf = float("nan")
        vals = [v for v in (pb, fb, pwf) if pd.notna(v)]
        delta = max((abs(sw - v) * 100 for v in vals), default=float("nan"))
        # contributions
        if len(known) and both_known.any():
            pos_by_pkg = both_known.groupby(known["package_key"]).sum()
            pos_total = float(pos_by_pkg.sum())
            largest_pkg = float(pos_by_pkg.max() / pos_total) if pos_total else float("nan")
        else:
            largest_pkg = float("nan")
        fam_pos = both.groupby(sub["family_canonical"]).sum()
        fam_total = float(fam_pos.sum()) if len(fam_pos) else 0.0
        union = float((ia | ib).sum())
        inter = float(both.sum())
        jaccard = inter / union if union else float("nan")
        pa, pb_m = float(ia.mean()), float(ib.mean())
        lift = (sw / (pa * pb_m)) if pa * pb_m else float("nan")
        if len(known):
            ia_k = ia.loc[known.index]
            ib_k = ib.loc[known.index]
            both_k = both.loc[known.index]
            # package-balanced jaccard approx via sample means on known rows
            union_k = float((ia_k | ib_k).sum())
            jaccard_pb = float(both_k.sum() / union_k) if union_k else float("nan")
            pa_k, pb_k = float(ia_k.mean()), float(ib_k.mean())
            lift_pb = (float(both_k.mean()) / (pa_k * pb_k)) if pa_k * pb_k else float("nan")
        else:
            jaccard_pb = float("nan")
            lift_pb = float("nan")
        transition = _status(state, float(delta) / 100.0 if pd.notna(delta) else float("nan"))
        if transition in {"package_balanced_supported"}:
            transition = "stable_across_weighting"
        rows.append(
            {
                **base,
                "sample_weighted_prevalence": sw,
                "package_balanced_prevalence": pb,
                "family_balanced_prevalence": fb,
                "package_within_family_balanced_prevalence": pwf,
                "lineage_balanced_prevalence": LINEAGE_BALANCE_UNAVAILABLE,
                "max_scheme_delta_pp": delta,
                "supporting_samples": int(inter),
                "supporting_packages": int((both.loc[known.index].groupby(known["package_key"]).sum() > 0).sum())
                if len(known)
                else 0,
                "supporting_families": int((fam_pos > 0).sum()) if len(fam_pos) else 0,
                "largest_package_contribution": largest_pkg,
                "largest_family_contribution": float(fam_pos.max() / fam_total) if fam_total else float("nan"),
                "sample_weighted_jaccard": jaccard,
                "package_balanced_jaccard": jaccard_pb,
                "sample_weighted_lift": lift,
                "package_balanced_lift": lift_pb,
                "reportability_transition": transition,
                "suppression_reason": "",
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["type_slug", "permission_a", "permission_b"])
        .reset_index(drop=True)
    )


def build_dominant_package_sensitivity(
    *,
    membership: pd.DataFrame,
    permissions_by_type: Mapping[str, Sequence[str]],
    pairwise: pd.DataFrame | None = None,
    grouping_field: str = "type_slug",
    concentration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compare full group profiles with dominant package exclusions."""
    keyed = assign_package_keys(membership) if "package_key" not in membership.columns else membership
    state_map: dict[str, str] = {}
    if concentration is not None and not concentration.empty and grouping_field in concentration.columns:
        state_map = dict(
            zip(concentration[grouping_field].astype(str), concentration["concentration_state"].astype(str))
        )
    rows: list[dict[str, Any]] = []
    for typ, permissions in sorted(permissions_by_type.items()):
        sub = keyed[keyed[grouping_field].astype(str).eq(str(typ))].copy()
        if state_map:
            state = state_map.get(str(typ), "insufficient_package_identity")
        else:
            concentration_row = _concentration(sub, [grouping_field])
            state = (
                str(concentration_row["concentration_state"].iloc[0])
                if not concentration_row.empty
                else "insufficient_package_identity"
            )
        known = sub[~sub["is_missing_package"]]
        counts = known["package_key"].value_counts()
        if state in {
            "insufficient_package_identity",
            "package_identity_conflicted",
            "single_package_dominated",
        }:
            rows.append(
                {
                    "analysis_scope": "type" if grouping_field == "type_slug" else "family",
                    "type_slug": typ if grouping_field == "type_slug" else "",
                    "family_canonical": typ if grouping_field == "family_canonical" else "",
                    "scenario": "skipped",
                    "n_samples": int(len(sub)),
                    "known_package_count": int(len(counts)),
                    "package_concentration_state": state,
                    "robustness_class": state,
                }
            )
            continue
        scenarios: dict[str, pd.DataFrame] = {
            "full_sample_weighted": sub,
            "package_balanced": sub,
            "package_within_family_balanced": sub,
        }
        if len(counts):
            scenarios["exclude_largest_package"] = sub[~sub["package_key"].eq(counts.index[0])]
            scenarios["exclude_top3_packages"] = sub[~sub["package_key"].isin(list(counts.index[:3]))]
        full = np.asarray([sample_weighted_prevalence(sub, p) for p in permissions], dtype=float)
        for name, work in scenarios.items():
            if name == "package_balanced":
                values = np.asarray([package_balanced_prevalence(work, p) for p in permissions], dtype=float)
            elif name == "package_within_family_balanced":
                values = np.asarray(
                    [package_within_family_balanced_prevalence(work, p) for p in permissions], dtype=float
                )
            else:
                values = np.asarray([sample_weighted_prevalence(work, p) for p in permissions], dtype=float)
            valid = np.isfinite(full) & np.isfinite(values)
            p, q = full[valid], values[valid]
            pn = p / p.sum() if p.sum() else np.ones_like(p) / max(len(p), 1)
            qn = q / q.sum() if q.sum() else np.ones_like(q) / max(len(q), 1)
            max_shift = float(np.max(np.abs(p - q)) * 100) if len(p) else float("nan")
            spearman = spearman_rank_corr(p, q)
            jsd = float(js_distance(pn, qn)) if len(p) else float("nan")
            if name == "full_sample_weighted":
                robustness = "baseline"
            elif (pd.notna(spearman) and spearman < 0.55) or (pd.notna(jsd) and jsd >= 0.25) or (
                pd.notna(max_shift) and max_shift >= 25.0
            ):
                robustness = "package_concentration_driven"
            elif (pd.notna(spearman) and spearman < 0.85) or (pd.notna(jsd) and jsd >= 0.10) or (
                pd.notna(max_shift) and max_shift >= 10.0
            ):
                robustness = "sample_duplication_sensitive"
            else:
                robustness = "stable_across_weighting"
            rows.append(
                {
                    "analysis_scope": "type" if grouping_field == "type_slug" else "family",
                    "type_slug": typ if grouping_field == "type_slug" else "",
                    "family_canonical": typ if grouping_field == "family_canonical" else "",
                    "scenario": name,
                    "n_samples": int(len(work)),
                    "known_package_count": int(work.loc[~work["is_missing_package"], "package_key"].nunique())
                    if len(work)
                    else 0,
                    "spearman_vs_full_sw": spearman,
                    "js_distance_vs_full_sw": jsd,
                    "max_abs_prevalence_shift_pp": max_shift,
                    "headline_permissions_lost": int(((p >= 0.20) & (q < 0.20)).sum()) if len(p) else 0,
                    "enriched_permissions_lost": int(((p >= 0.05) & (q < 0.05)).sum()) if len(p) else 0,
                    "package_concentration_state": state,
                    "robustness_class": robustness,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    sort_cols = ["analysis_scope", grouping_field, "scenario"]
    return frame.sort_values([c for c in sort_cols if c in frame.columns]).reset_index(drop=True)


def build_source_batch_concentration(labels: pd.DataFrame) -> pd.DataFrame:
    """Measure package concentration by source-batch label."""
    field = "source_batch_label"
    if field not in labels.columns:
        return pd.DataFrame()
    base = _concentration(labels, [field])
    keyed = assign_package_keys(labels) if "package_key" not in labels.columns else labels
    extras: list[dict[str, Any]] = []
    for batch, group in keyed.groupby(field, dropna=False, sort=True):
        label = batch if str(batch).strip() else "(blank)"
        fam = group.get("family_canonical", pd.Series(dtype=str)).fillna("").astype(str)
        typ = group.get("type_slug", pd.Series(dtype=str)).fillna("").astype(str)
        fam_vc = fam[fam.ne("")].value_counts()
        typ_vc = typ[typ.ne("")].value_counts()
        extras.append(
            {
                "source_batch_label": label,
                "largest_family_canonical": str(fam_vc.index[0]) if len(fam_vc) else "",
                "largest_family_share": float(fam_vc.iloc[0] / len(group)) if len(fam_vc) and len(group) else 0.0,
                "largest_type_slug": str(typ_vc.index[0]) if len(typ_vc) else "",
                "largest_type_share": float(typ_vc.iloc[0] / len(group)) if len(typ_vc) and len(group) else 0.0,
            }
        )
    extra = pd.DataFrame(extras)
    if base.empty or extra.empty:
        return base
    # normalize blank batch labels in base
    base = base.copy()
    base["source_batch_label"] = base["source_batch_label"].map(
        lambda v: "(blank)" if str(v).strip() in {"", "nan", "None"} else v
    )
    return base.merge(extra, on="source_batch_label", how="left").sort_values(
        "sample_count", ascending=False
    ).reset_index(drop=True)


def render_interpretation(
    *, family_concentration: pd.DataFrame, type_concentration: pd.DataFrame,
    weighting: pd.DataFrame, sensitivity: pd.DataFrame,
    collisions: pd.DataFrame | None = None, batch_concentration: pd.DataFrame | None = None,
) -> str:
    """Render a package-safe research interpretation (no package values or hashes)."""
    def _fam(name: str) -> pd.Series:
        hit = family_concentration[family_concentration["family_canonical"].astype(str) == name]
        return hit.iloc[0] if not hit.empty else pd.Series(dtype=object)
    clay, god, ars, dev, safer, giga = (_fam(n) for n in ("ClayRat","Godfather","ArsinkRAT","Devixor","SaferRat","Gigabud"))
    sensitive = int((weighting.get("reportability_status", pd.Series(dtype=str)) == "sample_duplication_sensitive").sum())
    conflicted = int((type_concentration.get("concentration_state", pd.Series(dtype=str)) == "package_identity_conflicted").sum())
    cross_family = int((collisions.get("collision_class", pd.Series(dtype=str)) == "cross_family_collision").sum()) if collisions is not None and not collisions.empty else 0
    cross_type = int((collisions.get("collision_class", pd.Series(dtype=str)) == "cross_type_collision").sum()) if collisions is not None and not collisions.empty else 0
    lines = [
        "# Package-balanced permission interpretation", "",
        "This offline analysis compares sample-weighted, package-balanced, family-balanced, and package-within-family balanced descriptive manifest evidence from the frozen completed run.",
        "Package identity is an accounting key, not malware lineage.",
        f"- `{LINEAGE_BALANCE_UNAVAILABLE}`: no governed lineage field exists in run artifacts.",
        f"- Cross-family package collisions: {cross_family}; cross-type: {cross_type}; type groups conflicted: {conflicted}.",
        f"- Permission rows labeled sample_duplication_sensitive: {sensitive}.",
        "",
        "## RAT / ClayRat",
        f"- ClayRat state=`{clay.get('concentration_state','')}`; known packages={clay.get('known_package_count','')}; samples={clay.get('sample_count','')}; largest-package share={clay.get('largest_package_sample_share', clay.get('largest_package_share',''))}; HHI={clay.get('package_hhi','')}.",
        "- Broad package diversity implies ClayRat sample-weighted influence is not explained by repeatedly sampling one package identity; family dominance can still remain.",
        "",
        "## Banker / Godfather",
        f"- Godfather state=`{god.get('concentration_state','')}`; known packages={god.get('known_package_count','')}; samples={god.get('sample_count','')}; largest-package share={god.get('largest_package_sample_share', god.get('largest_package_share',''))}.",
        "- Banker stability should be read with package-within-family balanced prevalences; Godfather package diversity is substantial but not one-to-one.",
        "",
        "## Devixor / ArsinkRAT / Gigabud / SaferRat",
        f"- Devixor state=`{dev.get('concentration_state','')}`; packages={dev.get('known_package_count','')}; largest share={dev.get('largest_package_sample_share', dev.get('largest_package_share',''))}. Broad family claims are package-concentration driven when few packages dominate.",
        f"- ArsinkRAT state=`{ars.get('concentration_state','')}`; packages={ars.get('known_package_count','')} vs samples={ars.get('sample_count','')}.",
        f"- Gigabud (frozen-run only) state=`{giga.get('concentration_state','')}`; packages={giga.get('known_package_count','')}; samples={giga.get('sample_count','')}.",
        f"- SaferRat state=`{safer.get('concentration_state','')}`; known packages={safer.get('known_package_count','')}; missing share={safer.get('missing_package_share','')}. Treat as data-quality / identity-concentration, not a broad banker pattern.",
        "",
        "## Limits",
        "- Do not say many samples prove many lineages, or that one package means one lineage.",
        "- Source-batch concentration is not lineage.",
        "- Static permissions are descriptive manifest evidence only.",
        "",
    ]
    return "\n".join(lines)


def _read_features(path: Path, audit: pd.DataFrame, permissions: set[str]) -> pd.DataFrame:
    mapping = dict(zip(audit["permission_string"].astype(str).str.lower(), audit["feature_column"].astype(str)))
    cols = ["sample_id"] + sorted({mapping[p] for p in permissions if p in mapping})
    features = pd.read_csv(path, compression="gzip", usecols=lambda c: c in cols)
    # Public weighting functions use normalized permission strings, while the
    # feature matrix stores governed feature-column identifiers.
    rename = {feature: permission for permission, feature in mapping.items() if feature in features.columns}
    return features.rename(columns=rename)


def compose_package_balanced_permission_analysis(
    run_root: Path, run_id: str = EXPECTED_RUN_ID, output_dir: Path | None = None,
    repo_root: Path | None = None, load_features: bool = True,
) -> dict[str, Any]:
    """Compose the complete run-local package-balanced analysis package."""
    run_root = Path(run_root)
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]
    out = Path(output_dir) if output_dir else run_root / "diagnostics" / "package_balanced_permission_analysis"
    if out.name in BANNED_OUTPUT_DIRS or any(out.resolve() == (run_root / "diagnostics" / x).resolve() for x in BANNED_OUTPUT_DIRS):
        raise RuntimeError("refusing to write into an existing protected research directory")
    if out.exists():
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    diag, tables = run_root / "diagnostics", run_root / "bundles" / "permission_trends" / "tables"
    labels = pd.read_csv(diag / f"aligned_labels_{run_id}.csv")
    audit = pd.read_csv(diag / "permission_feature_audit.csv")
    type_prev = pd.read_csv(tables / f"permission_prevalence_by_type_{run_id}.csv")
    fam_prev = pd.read_csv(tables / f"permission_prevalence_by_family_{run_id}.csv")
    enrichment_path = diag / "permission_authority_enrichment" / "permission_authority_enrichment.csv"
    lane_lookup = enrichment_lane_lookup(pd.read_csv(enrichment_path)) if enrichment_path.is_file() else {}
    permissions = set(type_prev["permission"].astype(str).str.lower()) | set(
        fam_prev.loc[fam_prev["family_canonical"].isin(DEEP_DIVE_FAMILIES), "permission"].astype(str).str.lower())
    membership = assign_package_keys(labels)
    if load_features:
        features = _read_features(diag / f"aligned_features_{run_id}.csv.gz", audit, permissions)
        membership = membership.merge(features, on="sample_id", how="inner")
    collisions = build_package_collision_audit(membership)
    family_conc, type_conc = build_family_package_concentration(membership), build_type_package_concentration(membership)
    weighting = build_permission_weighting_comparison(
        membership=membership, type_prevalence=type_prev, family_prevalence=fam_prev, lane_lookup=lane_lookup,
        type_concentration=type_conc, family_concentration=family_conc)
    pair_path = diag / "type_permission_protection_enriched" / "type_permission_pairwise_protection.csv"
    if pair_path.is_file() and pair_path.stat().st_size > 0:
        try:
            pairs = pd.read_csv(pair_path)
        except pd.errors.EmptyDataError:
            pairs = pd.DataFrame()
    else:
        pairs = pd.DataFrame()
    if not pairs.empty and load_features:
        # Keep frozen pair universe rows, but only reweight pairs whose permissions
        # were loaded from aligned features (type/family prevalence vocabulary).
        pairs = pairs[
            pairs["permission_a"].astype(str).str.lower().isin(permissions)
            & pairs["permission_b"].astype(str).str.lower().isin(permissions)
        ].copy()
    pair_weighting = build_pairwise_weighting_comparison(
        membership=membership, pairwise=pairs, type_concentration=type_conc
    )
    perms_by_type = {typ: sorted(g["permission"].astype(str).str.lower().unique())
                     for typ, g in type_prev.groupby("type_slug")}
    perms_by_family = {
        family: sorted(group["permission"].astype(str).str.lower().unique())
        for family, group in fam_prev[fam_prev["family_canonical"].isin(DEEP_DIVE_FAMILIES)].groupby("family_canonical")
    }
    sensitivity = pd.concat([
        build_dominant_package_sensitivity(
            membership=membership, permissions_by_type=perms_by_type, pairwise=pairs,
            concentration=type_conc),
        build_dominant_package_sensitivity(
            membership=membership, permissions_by_type=perms_by_family, pairwise=pairs,
            grouping_field="family_canonical", concentration=family_conc),
    ], ignore_index=True)
    batch_conc = build_source_batch_concentration(membership)
    outputs = {
        "identity_grouping_field_contract.csv": build_identity_grouping_field_contract(labels),
        "package_identity_collision_audit.csv": collisions, "family_package_concentration.csv": family_conc,
        "type_package_concentration.csv": type_conc, "permission_weighting_comparison.csv": weighting,
        "pairwise_weighting_comparison.csv": pair_weighting,
        "dominant_package_sensitivity.csv": sensitivity, "source_batch_concentration.csv": batch_conc,
    }
    hashes = {}
    for name, frame in outputs.items():
        path = out / name
        frame.to_csv(path, index=False)
        hashes[name] = sha256_file(path)
    md = out / "package_balanced_permission_interpretation.md"
    md.write_text(render_interpretation(family_concentration=family_conc, type_concentration=type_conc,
                                        weighting=weighting, sensitivity=sensitivity,
                                        collisions=collisions, batch_concentration=batch_conc), encoding="utf-8")
    hashes[md.name] = sha256_file(md)
    input_paths = {
        "run_manifest": run_root / "run_manifest.json",
        "aligned_labels": diag / f"aligned_labels_{run_id}.csv",
        "analysis_snapshot": diag / f"analysis_snapshot_{run_id}.csv",
        "permission_feature_audit": diag / "permission_feature_audit.csv",
        "type_prevalence": tables / f"permission_prevalence_by_type_{run_id}.csv",
        "family_prevalence": tables / f"permission_prevalence_by_family_{run_id}.csv",
    }
    if load_features:
        input_paths["aligned_features"] = diag / f"aligned_features_{run_id}.csv.gz"
    if enrichment_path.is_file():
        input_paths["permission_authority_enrichment"] = enrichment_path
    if pair_path.is_file():
        input_paths["frozen_pair_universe"] = pair_path
    manifest = {
        "composer": "package_balanced_permission_analysis", "composer_version": PACKAGE_BALANCED_COMPOSER_VERSION,
        "package_key_contract_version": PACKAGE_KEY_CONTRACT_VERSION,
        "weighting_contract_version": WEIGHTING_CONTRACT_VERSION,
        "lineage_balance": LINEAGE_BALANCE_UNAVAILABLE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": run_id,
        "profile_id": identity.get("profile_id", ""), "repository_commit_at_run": identity.get("repository_commit", ""),
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "thresholds": {"package_concentration": CONCENTRATION_THRESHOLDS,
                       "pairwise_inherited": dict(DEFAULT_THRESHOLDS)},
        "final_counts": {
            "prepared_samples": identity.get("prepared_sample_count"),
            "permission_bearing_samples": identity.get("permission_bearing_sample_count"),
            "membership_rows": int(len(membership)),
            "known_packages": int(membership.loc[~membership["is_missing_package"], "package_key"].nunique()),
            "missing_package_samples": int(membership["is_missing_package"].sum()),
            "collision_rows": int(len(collisions)),
            "weighting_rows": int(len(weighting)),
            "pairwise_rows": int(len(pair_weighting)),
        },
        "deep_dive_families": list(DEEP_DIVE_FAMILIES), "output_hashes": hashes,
        "input_paths": {key: str(path) for key, path in input_paths.items()},
        "input_hashes": {key: sha256_file(path) for key, path in input_paths.items() if path.is_file()},
        "boundaries": {"database_access": False, "core_access": False, "erebus_access": False,
                       "permission_intel_access": False, "pipeline_execution": False,
                       "source_artifact_mutation": False,
                       "overwrote_prior_research_packages": False},
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes["manifest.json"] = sha256_file(manifest_path)
    manifest["output_hashes"] = hashes
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "SHA256SUMS").write_text("\n".join(f"{h}  {n}" for n, h in sorted(hashes.items())) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "LINEAGE_BALANCE_UNAVAILABLE", "PACKAGE_KEY_CONTRACT_VERSION", "WEIGHTING_CONTRACT_VERSION", "normalize_package_name", "assign_package_keys",
    "classify_package_collision", "compute_hhi", "effective_package_count",
    "classify_package_concentration_state", "sample_weighted_prevalence",
    "package_balanced_prevalence", "family_balanced_prevalence",
    "package_within_family_balanced_prevalence", "build_identity_grouping_field_contract",
    "build_package_collision_audit", "build_family_package_concentration",
    "build_type_package_concentration", "build_permission_weighting_comparison",
    "build_pairwise_weighting_comparison", "build_dominant_package_sensitivity",
    "build_source_batch_concentration", "render_interpretation",
    "compose_package_balanced_permission_analysis",
]
