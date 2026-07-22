"""Joint offline sensitivity: authority lanes × package weighting × leave-family.

Synthesizes frozen enrichment lanes with package/family hierarchical weighting
and leave-largest-family checks for RAT/banker headline claims.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.common.csv_io import optional_csv
from obsidiandroid.pipeline.permission_trends.stats_core import js_distance
from obsidiandroid.reporting.dominant_family_profile_sensitivity import spearman_rank_corr
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    BANNED_OUTPUT_DIRS as PKG_BANNED,
    LINEAGE_BALANCE_UNAVAILABLE,
    assign_package_keys,
    family_balanced_prevalence,
    package_balanced_prevalence,
    package_within_family_balanced_prevalence,
    sample_weighted_prevalence,
)
from obsidiandroid.reporting.permission_authority_enrichment import enrichment_lane_lookup
from obsidiandroid.reporting.permission_governance_lanes import CANONICAL_PROTECTION_LANES
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

JOINT_CONTRACT_VERSION = "1.0.0"
JOINT_COMPOSER_VERSION = "1.0.0"
FOCUS_TYPES = ("rat", "banker")
HEADLINE_LANES = (
    "aosp_normal",
    "aosp_dangerous",
    "aosp_signature",
    "aosp_signature_privileged",
    "oem_platform",
    "google_platform",
    "unknown_unresolved",
)
# Absolute prevalence floors for "headline" permissions in a type×lane profile.
HEADLINE_SW_FLOOR = 0.20
SURVIVAL_DELTA_PP = 15.0
SURVIVAL_SPEARMAN = 0.85

BANNED_OUTPUT_DIRS = set(PKG_BANNED) | {
    "package_balanced_permission_analysis",
    "package_balance_attribution",
    "permission_authority_enrichment",
    "type_permission_protection_enriched",
    "live_corpus_family_context",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _indicator(frame: pd.DataFrame, permission: str) -> pd.Series:
    return (
        pd.to_numeric(frame.get(permission, pd.Series(0, index=frame.index)), errors="coerce")
        .fillna(0)
        .gt(0)
    )


def _profile(frame: pd.DataFrame, permissions: Sequence[str], mode: str) -> np.ndarray:
    out: list[float] = []
    for perm in permissions:
        if mode == "sample_weighted":
            out.append(sample_weighted_prevalence(frame, perm))
        elif mode == "package_balanced":
            out.append(package_balanced_prevalence(frame, perm))
        elif mode == "family_balanced":
            out.append(family_balanced_prevalence(frame, perm))
        elif mode == "package_within_family_balanced":
            out.append(package_within_family_balanced_prevalence(frame, perm))
        else:
            raise ValueError(mode)
    return np.asarray(out, dtype=float)


def _compare(full: np.ndarray, other: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(full) & np.isfinite(other)
    p, q = full[valid], other[valid]
    if len(p) == 0:
        return {
            "spearman_vs_full_sw": float("nan"),
            "js_distance_vs_full_sw": float("nan"),
            "max_abs_prevalence_shift_pp": float("nan"),
            "headline_permissions_lost": 0.0,
        }
    pn = p / p.sum() if p.sum() else np.ones_like(p) / max(len(p), 1)
    qn = q / q.sum() if q.sum() else np.ones_like(q) / max(len(q), 1)
    return {
        "spearman_vs_full_sw": spearman_rank_corr(p, q),
        "js_distance_vs_full_sw": float(js_distance(pn, qn)),
        "max_abs_prevalence_shift_pp": float(np.max(np.abs(p - q)) * 100.0),
        "headline_permissions_lost": float(((p >= HEADLINE_SW_FLOOR) & (q < HEADLINE_SW_FLOOR)).sum()),
    }


def classify_joint_survival(
    *,
    identity_gate: str,
    sw: float,
    pwf: float,
    leave_pwf: float,
    package_delta_pp: float,
    family_leave_delta_pp: float,
) -> str:
    if identity_gate == "package_identity_conflicted":
        return "identity_gated"
    if pd.isna(sw) or sw < 0.05:
        return "exploratory_only"
    pkg_fragile = pd.notna(package_delta_pp) and package_delta_pp >= SURVIVAL_DELTA_PP
    fam_fragile = pd.notna(family_leave_delta_pp) and family_leave_delta_pp >= SURVIVAL_DELTA_PP
    if pkg_fragile and fam_fragile:
        return "jointly_fragile"
    if pkg_fragile:
        return "package_balance_fragile"
    if fam_fragile:
        return "dominant_family_fragile"
    # Also require leave-largest PWF still near SW for survivors
    if pd.notna(leave_pwf) and abs(float(sw) - float(leave_pwf)) * 100 >= SURVIVAL_DELTA_PP:
        return "dominant_family_fragile"
    if pd.notna(pwf) and abs(float(sw) - float(pwf)) * 100 >= SURVIVAL_DELTA_PP:
        return "package_balance_fragile"
    return "survives_joint_sensitivity"


def build_identity_gate(
    *,
    type_concentration: pd.DataFrame,
    family_concentration: pd.DataFrame,
    focus_types: Sequence[str] = FOCUS_TYPES,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for typ in focus_types:
        hit = type_concentration[type_concentration["type_slug"].astype(str) == typ]
        state = str(hit.iloc[0]["concentration_state"]) if not hit.empty else "insufficient_package_identity"
        rows.append(
            {
                "analysis_scope": "type",
                "type_slug": typ,
                "family_canonical": "",
                "concentration_state": state,
                "identity_gate": state if state == "package_identity_conflicted" else "eligible",
                "eligible_for_package_balanced_claims": state != "package_identity_conflicted",
            }
        )
    for fam in ("ClayRat", "Godfather", "ArsinkRAT", "Devixor", "SaferRat", "Applite"):
        hit = family_concentration[family_concentration["family_canonical"].astype(str) == fam]
        if hit.empty:
            continue
        state = str(hit.iloc[0]["concentration_state"])
        typ = ""
        # Devixor is banker in this corpus
        if fam in {"Godfather", "Devixor", "SaferRat", "Applite"}:
            typ = "banker"
        elif fam in {"ClayRat", "ArsinkRAT"}:
            typ = "rat"
        rows.append(
            {
                "analysis_scope": "family",
                "type_slug": typ,
                "family_canonical": fam,
                "concentration_state": state,
                "identity_gate": "eligible",
                "eligible_for_package_balanced_claims": state
                not in {"package_identity_conflicted", "insufficient_package_identity"},
            }
        )
    return pd.DataFrame(rows)


def build_type_lane_joint_weighting(
    *,
    membership: pd.DataFrame,
    permissions_by_type_lane: Mapping[tuple[str, str], Sequence[str]],
    largest_family_by_type: Mapping[str, str],
    identity_gate_by_type: Mapping[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    type_cache = {str(k): v for k, v in keyed.groupby(keyed["type_slug"].astype(str), sort=False)}

    for (typ, lane), permissions in sorted(permissions_by_type_lane.items()):
        sub = type_cache.get(typ, pd.DataFrame())
        if sub.empty:
            continue
        largest = largest_family_by_type.get(typ, "")
        leave = sub[sub["family_canonical"].astype(str) != largest] if largest else sub
        gate = identity_gate_by_type.get(typ, "eligible")
        for perm in permissions:
            if perm not in keyed.columns:
                continue
            sw = sample_weighted_prevalence(sub, perm)
            pb = package_balanced_prevalence(sub, perm)
            fb = family_balanced_prevalence(sub, perm)
            pwf = package_within_family_balanced_prevalence(sub, perm)
            leave_sw = sample_weighted_prevalence(leave, perm)
            leave_pwf = package_within_family_balanced_prevalence(leave, perm)
            pkg_delta = abs(float(sw) - float(pb)) * 100 if pd.notna(sw) and pd.notna(pb) else float("nan")
            pwf_delta = abs(float(sw) - float(pwf)) * 100 if pd.notna(sw) and pd.notna(pwf) else float("nan")
            fam_delta = abs(float(sw) - float(leave_sw)) * 100 if pd.notna(sw) and pd.notna(leave_sw) else float("nan")
            leave_pwf_delta = (
                abs(float(sw) - float(leave_pwf)) * 100 if pd.notna(sw) and pd.notna(leave_pwf) else float("nan")
            )
            status = classify_joint_survival(
                identity_gate=gate,
                sw=float(sw) if pd.notna(sw) else float("nan"),
                pwf=float(pwf) if pd.notna(pwf) else float("nan"),
                leave_pwf=float(leave_pwf) if pd.notna(leave_pwf) else float("nan"),
                package_delta_pp=float(pwf_delta) if pd.notna(pwf_delta) else float("nan"),
                family_leave_delta_pp=float(fam_delta) if pd.notna(fam_delta) else float("nan"),
            )
            rows.append(
                {
                    "type_slug": typ,
                    "headline_lane": lane,
                    "permission": perm,
                    "largest_family": largest,
                    "identity_gate": gate,
                    "sample_weighted_prevalence": sw,
                    "package_balanced_prevalence": pb,
                    "family_balanced_prevalence": fb,
                    "package_within_family_balanced_prevalence": pwf,
                    "leave_largest_family_sample_weighted": leave_sw,
                    "leave_largest_family_package_within_family": leave_pwf,
                    "delta_sw_vs_package_balanced_pp": pkg_delta,
                    "delta_sw_vs_package_within_family_pp": pwf_delta,
                    "delta_sw_vs_leave_family_sw_pp": fam_delta,
                    "delta_sw_vs_leave_family_pwf_pp": leave_pwf_delta,
                    "supporting_samples": int(_indicator(sub, perm).sum()),
                    "joint_survival_status": status,
                }
            )
    return pd.DataFrame(rows).sort_values(["type_slug", "headline_lane", "permission"]).reset_index(drop=True)


def build_family_joint_weighting(
    *,
    membership: pd.DataFrame,
    permissions_by_family_lane: Mapping[tuple[str, str], Sequence[str]],
    family_types: Mapping[str, str],
) -> pd.DataFrame:
    """Family-scoped joint weighting (eligible even when type is identity-gated)."""
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    fam_cache = {
        str(k): v for k, v in keyed.groupby(keyed["family_canonical"].astype(str), sort=False)
    }
    rows: list[dict[str, Any]] = []
    for (family, lane), permissions in sorted(permissions_by_family_lane.items()):
        sub = fam_cache.get(family, pd.DataFrame())
        if sub.empty:
            continue
        # Exclude largest package within family
        known = sub[~sub["is_missing_package"].astype(bool)]
        counts = known["package_key"].value_counts()
        largest_pkg = str(counts.index[0]) if len(counts) else ""
        leave_pkg = sub[sub["package_key"].astype(str) != largest_pkg] if largest_pkg else sub
        for perm in permissions:
            if perm not in keyed.columns:
                continue
            sw = sample_weighted_prevalence(sub, perm)
            pb = package_balanced_prevalence(sub, perm)
            leave_sw = sample_weighted_prevalence(leave_pkg, perm)
            pkg_delta = abs(float(sw) - float(pb)) * 100 if pd.notna(sw) and pd.notna(pb) else float("nan")
            leave_delta = (
                abs(float(sw) - float(leave_sw)) * 100 if pd.notna(sw) and pd.notna(leave_sw) else float("nan")
            )
            status = classify_joint_survival(
                identity_gate="eligible",
                sw=float(sw) if pd.notna(sw) else float("nan"),
                pwf=float(pb) if pd.notna(pb) else float("nan"),
                leave_pwf=float(leave_sw) if pd.notna(leave_sw) else float("nan"),
                package_delta_pp=float(pkg_delta) if pd.notna(pkg_delta) else float("nan"),
                family_leave_delta_pp=float(leave_delta) if pd.notna(leave_delta) else float("nan"),
            )
            rows.append(
                {
                    "analysis_scope": "family",
                    "family_canonical": family,
                    "type_slug": family_types.get(family, ""),
                    "headline_lane": lane,
                    "permission": perm,
                    "sample_weighted_prevalence": sw,
                    "package_balanced_prevalence": pb,
                    "leave_largest_package_sample_weighted": leave_sw,
                    "delta_sw_vs_package_balanced_pp": pkg_delta,
                    "delta_sw_vs_leave_package_pp": leave_delta,
                    "joint_survival_status": status,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["family_canonical", "headline_lane", "permission"]
    ).reset_index(drop=True)


def build_headline_joint_survival(weighting: pd.DataFrame) -> pd.DataFrame:
    """Narrow claim-facing table: high SW permissions in focus types/lanes."""
    if weighting.empty:
        return weighting
    frame = weighting[
        (weighting["sample_weighted_prevalence"] >= HEADLINE_SW_FLOOR)
        & (weighting["headline_lane"].isin(HEADLINE_LANES))
    ].copy()
    if frame.empty:
        return frame
    frame["survives_joint_sensitivity"] = frame["joint_survival_status"] == "survives_joint_sensitivity"
    return frame.sort_values(
        ["type_slug", "headline_lane", "sample_weighted_prevalence"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def build_type_lane_joint_profile_sensitivity(
    *,
    membership: pd.DataFrame,
    permissions_by_type_lane: Mapping[tuple[str, str], Sequence[str]],
    largest_family_by_type: Mapping[str, str],
    identity_gate_by_type: Mapping[str, str],
) -> pd.DataFrame:
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    type_cache = {str(k): v for k, v in keyed.groupby(keyed["type_slug"].astype(str), sort=False)}
    rows: list[dict[str, Any]] = []
    for (typ, lane), permissions in sorted(permissions_by_type_lane.items()):
        perms = [p for p in permissions if p in keyed.columns]
        if not perms:
            continue
        sub = type_cache.get(typ, pd.DataFrame())
        if sub.empty:
            continue
        gate = identity_gate_by_type.get(typ, "eligible")
        largest = largest_family_by_type.get(typ, "")
        leave = sub[sub["family_canonical"].astype(str) != largest] if largest else sub
        full = _profile(sub, perms, "sample_weighted")
        scenarios = {
            "full_sample_weighted": ("sample_weighted", sub),
            "package_balanced": ("package_balanced", sub),
            "family_balanced": ("family_balanced", sub),
            "package_within_family_balanced": ("package_within_family_balanced", sub),
            "leave_largest_family_sample_weighted": ("sample_weighted", leave),
            "leave_largest_family_package_within_family": ("package_within_family_balanced", leave),
        }
        for name, (mode, frame) in scenarios.items():
            if gate == "package_identity_conflicted" and "package" in name:
                rows.append(
                    {
                        "type_slug": typ,
                        "headline_lane": lane,
                        "scenario": name,
                        "largest_family": largest,
                        "identity_gate": gate,
                        "n_samples": int(len(frame)),
                        "n_permissions": int(len(perms)),
                        "robustness_class": "identity_gated",
                    }
                )
                continue
            vec = _profile(frame, perms, mode)
            metrics = _compare(full, vec)
            spearman = metrics["spearman_vs_full_sw"]
            max_shift = metrics["max_abs_prevalence_shift_pp"]
            if name == "full_sample_weighted":
                klass = "baseline"
            elif gate == "package_identity_conflicted":
                klass = "identity_gated"
            elif (pd.notna(spearman) and spearman < 0.55) or (pd.notna(max_shift) and max_shift >= 25):
                klass = "jointly_fragile" if "leave" in name and "package" in name else (
                    "dominant_family_fragile" if "leave" in name else "package_balance_fragile"
                )
            elif (pd.notna(spearman) and spearman < SURVIVAL_SPEARMAN) or (
                pd.notna(max_shift) and max_shift >= SURVIVAL_DELTA_PP
            ):
                klass = "moderately_sensitive"
            else:
                klass = "survives_joint_sensitivity"
            rows.append(
                {
                    "type_slug": typ,
                    "headline_lane": lane,
                    "scenario": name,
                    "largest_family": largest,
                    "identity_gate": gate,
                    "n_samples": int(len(frame)),
                    "n_permissions": int(len(perms)),
                    **metrics,
                    "robustness_class": klass,
                }
            )
    return pd.DataFrame(rows).sort_values(["type_slug", "headline_lane", "scenario"]).reset_index(drop=True)


def build_joint_pairwise_sensitivity(
    *,
    membership: pd.DataFrame,
    pairwise: pd.DataFrame,
    identity_gate_by_type: Mapping[str, str],
    largest_family_by_type: Mapping[str, str],
) -> pd.DataFrame:
    """Reweight frozen enriched pairs only (no new mining)."""
    if pairwise.empty:
        return pd.DataFrame()
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    # Keep pairs for focus types with both endpoints present.
    focus = pairwise[pairwise["type_slug"].astype(str).isin(FOCUS_TYPES)].copy()
    type_cache = {str(k): v for k, v in keyed.groupby(keyed["type_slug"].astype(str), sort=False)}
    rows: list[dict[str, Any]] = []
    for pair in focus.itertuples(index=False):
        typ = str(getattr(pair, "type_slug", ""))
        a, b = _norm(getattr(pair, "permission_a", "")), _norm(getattr(pair, "permission_b", ""))
        gate = identity_gate_by_type.get(typ, "eligible")
        base = {
            "type_slug": typ,
            "permission_a": a,
            "permission_b": b,
            "permission_a_lane": str(getattr(pair, "permission_a_lane", "")),
            "permission_b_lane": str(getattr(pair, "permission_b_lane", "")),
            "artifact_reportability_status": str(getattr(pair, "reportability_status", "")),
            "artifact_leave_largest_family_result": str(getattr(pair, "leave_largest_family_result", "")),
            "identity_gate": gate,
        }
        sub = type_cache.get(typ)
        if sub is None or a not in keyed.columns or b not in keyed.columns:
            base["joint_pair_status"] = "insufficient_features"
            rows.append(base)
            continue
        if gate == "package_identity_conflicted":
            base["joint_pair_status"] = "identity_gated"
            rows.append(base)
            continue
        both = (_indicator(sub, a) & _indicator(sub, b)).astype(int)
        work = sub.copy()
        work["__pair__"] = both
        sw = float(both.mean()) if len(sub) else float("nan")
        known = work[~work["is_missing_package"].astype(bool)]
        pb = float(work.loc[known.index, "__pair__"].groupby(known["package_key"]).mean().mean()) if len(known) else float("nan")
        pwf = package_within_family_balanced_prevalence(work, "__pair__")
        largest = largest_family_by_type.get(typ, "")
        leave = work[work["family_canonical"].astype(str) != largest] if largest else work
        leave_pwf = package_within_family_balanced_prevalence(leave, "__pair__")
        pkg_delta = abs(sw - pb) * 100 if pd.notna(pb) else float("nan")
        pwf_delta = abs(sw - float(pwf)) * 100 if pd.notna(pwf) else float("nan")
        leave_delta = abs(sw - float(leave_pwf)) * 100 if pd.notna(leave_pwf) else float("nan")
        status = classify_joint_survival(
            identity_gate=gate,
            sw=sw,
            pwf=float(pwf) if pd.notna(pwf) else float("nan"),
            leave_pwf=float(leave_pwf) if pd.notna(leave_pwf) else float("nan"),
            package_delta_pp=float(pwf_delta) if pd.notna(pwf_delta) else float("nan"),
            family_leave_delta_pp=float(leave_delta) if pd.notna(leave_delta) else float("nan"),
        )
        rows.append(
            {
                **base,
                "sample_weighted_pair_prevalence": sw,
                "package_balanced_pair_prevalence": pb,
                "package_within_family_pair_prevalence": pwf,
                "leave_largest_family_package_within_family_pair": leave_pwf,
                "delta_sw_vs_pwf_pp": pwf_delta,
                "delta_sw_vs_leave_pwf_pp": leave_delta,
                "delta_sw_vs_package_balanced_pp": pkg_delta,
                "joint_pair_status": status,
            }
        )
    return pd.DataFrame(rows).sort_values(["type_slug", "permission_a", "permission_b"]).reset_index(drop=True)


def _fmt_pp(value: object) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "n/a"
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "n/a"


def render_joint_interpretation(
    *,
    profile: pd.DataFrame,
    headlines: pd.DataFrame,
    gate: pd.DataFrame,
    family_headlines: pd.DataFrame | None = None,
) -> str:
    def _prof(typ: str, lane: str, scenario: str) -> pd.Series:
        hit = profile[
            (profile.type_slug == typ)
            & (profile.headline_lane == lane)
            & (profile.scenario == scenario)
        ]
        return hit.iloc[0] if not hit.empty else pd.Series(dtype=object)

    banker_gate = gate[(gate.analysis_scope == "type") & (gate.type_slug == "banker")]
    banker_state = str(banker_gate.iloc[0]["identity_gate"]) if not banker_gate.empty else ""

    lines = [
        "# Enriched package–family joint sensitivity interpretation",
        "",
        "Joint offline check: authority-enriched lanes × package/family weighting × leave-largest family.",
        f"Lineage balancing remains `{LINEAGE_BALANCE_UNAVAILABLE}`.",
        f"Banker type identity gate: `{banker_state}`.",
        "Devixor is treated as governed banker, not RAT.",
        "",
        "## RAT / ClayRat",
        "",
    ]
    for lane in ("aosp_normal", "aosp_dangerous", "aosp_signature", "aosp_signature_privileged", "unknown_unresolved"):
        pwf = _prof("rat", lane, "package_within_family_balanced")
        leave = _prof("rat", lane, "leave_largest_family_package_within_family")
        if pwf.empty and leave.empty:
            continue
        lines.append(
            f"- `{lane}`: PWF maxΔpp={_fmt_pp(pwf.get('max_abs_prevalence_shift_pp', None))}, "
            f"class=`{pwf.get('robustness_class', '')}`; "
            f"leave-ClayRat PWF maxΔpp={_fmt_pp(leave.get('max_abs_prevalence_shift_pp', None))}, "
            f"class=`{leave.get('robustness_class', '')}`."
        )
    lines.extend(["", "## Banker / Godfather", ""])
    for lane in ("aosp_normal", "aosp_dangerous", "aosp_signature", "aosp_signature_privileged", "unknown_unresolved"):
        pwf = _prof("banker", lane, "package_within_family_balanced")
        leave = _prof("banker", lane, "leave_largest_family_package_within_family")
        if pwf.empty and leave.empty:
            continue
        lines.append(
            f"- `{lane}`: PWF maxΔpp={_fmt_pp(pwf.get('max_abs_prevalence_shift_pp', None))}, "
            f"class=`{pwf.get('robustness_class', '')}`; "
            f"leave-Godfather PWF maxΔpp={_fmt_pp(leave.get('max_abs_prevalence_shift_pp', None))}, "
            f"class=`{leave.get('robustness_class', '')}`."
        )

    if not headlines.empty:
        surv = int((headlines["joint_survival_status"] == "survives_joint_sensitivity").sum())
        frag = int(headlines["joint_survival_status"].isin(
            ["package_balance_fragile", "dominant_family_fragile", "jointly_fragile"]
        ).sum())
        gated = int((headlines["joint_survival_status"] == "identity_gated").sum())
        lines.extend(
            [
                "",
                "## Headline permission survival",
                "",
                f"- Headline rows (SW≥{HEADLINE_SW_FLOOR:.0%}): {len(headlines)}.",
                f"- Survive joint sensitivity: {surv}.",
                f"- Fragile on package and/or family axis: {frag}.",
                f"- Identity-gated: {gated}.",
                "",
            ]
        )
    if family_headlines is not None and not family_headlines.empty:
        lines.extend(["## Family-scoped survival (ClayRat / Godfather / …)", ""])
        for fam in ("ClayRat", "Godfather", "ArsinkRAT", "Devixor"):
            sub = family_headlines[family_headlines["family_canonical"] == fam]
            if sub.empty:
                continue
            surv = int((sub["joint_survival_status"] == "survives_joint_sensitivity").sum())
            lines.append(
                f"- `{fam}` headline rows={len(sub)}; survive package/leave-largest-package={surv}."
            )
        lines.append("")
    lines.extend(
        [
            "## Limits",
            "",
            "- Static declarations only; not runtime behavior.",
            "- Do not equate package identity with malware lineage.",
            "- Banker package-balanced type claims remain gated when conflicted; family-scoped Godfather rows remain informative.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_features(path: Path, audit: pd.DataFrame, permissions: set[str]) -> pd.DataFrame:
    mapping = dict(
        zip(audit["permission_string"].astype(str).str.lower(), audit["feature_column"].astype(str))
    )
    wanted = {"sample_id"} | {mapping[p] for p in permissions if p in mapping}
    features = pd.read_csv(path, compression="gzip", usecols=lambda c: c in wanted)
    rename = {feature: permission for permission, feature in mapping.items() if feature in features.columns}
    return features.rename(columns=rename)


def compose_enriched_package_family_sensitivity(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    focus_types: Sequence[str] = FOCUS_TYPES,
) -> dict[str, Any]:
    """Compose the joint sensitivity package."""
    run_root = Path(run_root)
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]
    out = (
        Path(output_dir)
        if output_dir
        else run_root / "diagnostics" / "enriched_package_family_sensitivity"
    )
    if out.name in BANNED_OUTPUT_DIRS or any(
        out.resolve() == (run_root / "diagnostics" / name).resolve() for name in BANNED_OUTPUT_DIRS
    ):
        raise RuntimeError("refusing to write into a protected research directory")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    enrich_path = diag / "permission_authority_enrichment" / "permission_authority_enrichment.csv"
    pkg_dir = diag / "package_balanced_permission_analysis"
    pair_path = diag / "type_permission_protection_enriched" / "type_permission_pairwise_protection.csv"

    labels = pd.read_csv(diag / f"aligned_labels_{run_id}.csv", low_memory=False)
    audit = pd.read_csv(diag / "permission_feature_audit.csv")
    type_prev = pd.read_csv(tables / f"permission_prevalence_by_type_{run_id}.csv")
    enrichment = pd.read_csv(enrich_path)
    lane_lookup = enrichment_lane_lookup(enrichment)
    type_conc = pd.read_csv(pkg_dir / "type_package_concentration.csv")
    fam_conc = pd.read_csv(pkg_dir / "family_package_concentration.csv")
    pairs = optional_csv(pair_path)
    # Candidate permissions: type prevalence for focus types, labeled by enrichment lane.
    type_prev = type_prev[type_prev["type_slug"].astype(str).isin(list(focus_types))].copy()
    type_prev["permission"] = type_prev["permission"].map(_norm)
    type_prev["headline_lane"] = type_prev["permission"].map(
        lambda p: lane_lookup.get(p, "unknown_unresolved")
    )

    permissions_by_type_lane: dict[tuple[str, str], list[str]] = {}
    all_perms: set[str] = set()
    for (typ, lane), group in type_prev.groupby(["type_slug", "headline_lane"], sort=True):
        perms = sorted(group["permission"].unique().tolist())
        permissions_by_type_lane[(str(typ), str(lane))] = perms
        all_perms.update(perms)

    # Include pairwise endpoints for focus types.
    if not pairs.empty:
        fp = pairs[pairs["type_slug"].astype(str).isin(list(focus_types))]
        all_perms.update(fp["permission_a"].map(_norm))
        all_perms.update(fp["permission_b"].map(_norm))

    membership = assign_package_keys(labels)
    features = _read_features(diag / f"aligned_features_{run_id}.csv.gz", audit, all_perms)
    membership = membership.merge(features, on="sample_id", how="inner")

    # Largest family by type (sample count).
    largest_family_by_type = (
        membership[membership["type_slug"].astype(str).isin(list(focus_types))]
        .groupby(["type_slug", "family_canonical"])
        .size()
        .reset_index(name="n")
        .sort_values(["type_slug", "n"], ascending=[True, False])
        .groupby("type_slug")
        .first()["family_canonical"]
        .astype(str)
        .to_dict()
    )

    gate = build_identity_gate(type_concentration=type_conc, family_concentration=fam_conc)
    identity_gate_by_type = {
        str(r.type_slug): str(r.identity_gate)
        for r in gate[gate.analysis_scope == "type"].itertuples(index=False)
    }

    weighting = build_type_lane_joint_weighting(
        membership=membership,
        permissions_by_type_lane=permissions_by_type_lane,
        largest_family_by_type=largest_family_by_type,
        identity_gate_by_type=identity_gate_by_type,
    )
    headlines = build_headline_joint_survival(weighting)
    profile = build_type_lane_joint_profile_sensitivity(
        membership=membership,
        permissions_by_type_lane=permissions_by_type_lane,
        largest_family_by_type=largest_family_by_type,
        identity_gate_by_type=identity_gate_by_type,
    )

    # Family-scoped joint check for dominant families (bypasses type identity gate).
    fam_prev = pd.read_csv(tables / f"permission_prevalence_by_family_{run_id}.csv")
    focus_families = ("ClayRat", "Godfather", "ArsinkRAT", "Devixor")
    family_types = {"ClayRat": "rat", "ArsinkRAT": "rat", "Godfather": "banker", "Devixor": "banker"}
    fam_prev = fam_prev[fam_prev["family_canonical"].astype(str).isin(focus_families)].copy()
    fam_prev["permission"] = fam_prev["permission"].map(_norm)
    fam_prev["headline_lane"] = fam_prev["permission"].map(lambda p: lane_lookup.get(p, "unknown_unresolved"))
    permissions_by_family_lane: dict[tuple[str, str], list[str]] = {}
    for (family, lane), group in fam_prev.groupby(["family_canonical", "headline_lane"], sort=True):
        perms = sorted(group["permission"].unique().tolist())
        permissions_by_family_lane[(str(family), str(lane))] = perms
        all_perms.update(perms)
    # Reload features if family perms added new columns (usually already covered).
    missing = [p for p in all_perms if p not in membership.columns]
    if missing:
        extra = _read_features(diag / f"aligned_features_{run_id}.csv.gz", audit, set(missing))
        membership = membership.merge(extra, on="sample_id", how="left")
    family_weighting = build_family_joint_weighting(
        membership=membership,
        permissions_by_family_lane=permissions_by_family_lane,
        family_types=family_types,
    )
    family_headlines = family_weighting[
        family_weighting["sample_weighted_prevalence"] >= HEADLINE_SW_FLOOR
    ].copy() if not family_weighting.empty else family_weighting

    # Limit pairwise to previously reportable / interesting statuses for tractability.
    if not pairs.empty and "reportability_status" in pairs.columns:
        interesting = {
            "family_balanced_supported",
            "dominant_family_sensitive",
            "single_family_dominated",
            "descriptive_type_enriched",
        }
        pair_focus = pairs[
            pairs["type_slug"].astype(str).isin(list(focus_types))
            & pairs["reportability_status"].astype(str).isin(interesting)
        ].copy()
    else:
        pair_focus = pairs
    joint_pairs = build_joint_pairwise_sensitivity(
        membership=membership,
        pairwise=pair_focus,
        identity_gate_by_type=identity_gate_by_type,
        largest_family_by_type=largest_family_by_type,
    )
    interpretation = render_joint_interpretation(
        profile=profile, headlines=headlines, gate=gate, family_headlines=family_headlines
    )

    outputs = {
        "joint_concentration_and_identity_gate.csv": gate,
        "type_lane_joint_weighting.csv": weighting,
        "headline_joint_survival.csv": headlines,
        "type_lane_joint_profile_sensitivity.csv": profile,
        "family_lane_joint_weighting.csv": family_weighting,
        "family_headline_joint_survival.csv": family_headlines,
        "joint_pairwise_sensitivity.csv": joint_pairs,
    }
    hashes: dict[str, str] = {}
    for name, frame in outputs.items():
        path = out / name
        frame.to_csv(path, index=False)
        hashes[name] = sha256_file(path)
    md = out / "enriched_package_family_sensitivity_interpretation.md"
    md.write_text(interpretation, encoding="utf-8")
    hashes[md.name] = sha256_file(md)

    input_paths = {
        "run_manifest": run_root / "run_manifest.json",
        "aligned_labels": diag / f"aligned_labels_{run_id}.csv",
        "aligned_features": diag / f"aligned_features_{run_id}.csv.gz",
        "permission_authority_enrichment": enrich_path,
        "type_prevalence": tables / f"permission_prevalence_by_type_{run_id}.csv",
        "type_package_concentration": pkg_dir / "type_package_concentration.csv",
        "family_package_concentration": pkg_dir / "family_package_concentration.csv",
        "enriched_pairwise": pair_path,
    }
    surv_counts = (
        headlines["joint_survival_status"].value_counts().to_dict() if not headlines.empty else {}
    )
    manifest = {
        "composer": "enriched_package_family_sensitivity",
        "composer_version": JOINT_COMPOSER_VERSION,
        "joint_sensitivity_contract_version": JOINT_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "profile_id": identity.get("profile_id", ""),
        "repository_commit_at_run": identity.get("repository_commit", ""),
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "focus_types": list(focus_types),
        "lineage_balance": LINEAGE_BALANCE_UNAVAILABLE,
        "thresholds": {
            "headline_sw_floor": HEADLINE_SW_FLOOR,
            "survival_delta_pp": SURVIVAL_DELTA_PP,
            "survival_spearman": SURVIVAL_SPEARMAN,
        },
        "summary": {
            "permissions_loaded": int(len(all_perms)),
            "weighting_rows": int(len(weighting)),
            "headline_rows": int(len(headlines)),
            "profile_rows": int(len(profile)),
            "pairwise_rows": int(len(joint_pairs)),
            "headline_survival_counts": {str(k): int(v) for k, v in surv_counts.items()},
            "family_headline_rows": int(len(family_headlines)),
            "largest_family_by_type": largest_family_by_type,
            "identity_gate_by_type": identity_gate_by_type,
        },
        "output_hashes": hashes,
        "input_paths": {k: str(v) for k, v in input_paths.items()},
        "input_hashes": {k: sha256_file(v) for k, v in input_paths.items() if Path(v).is_file()},
        "boundaries": {
            "database_access": False,
            "core_access": False,
            "permission_intel_access": False,
            "pipeline_execution": False,
            "taxonomy_mutation": False,
            "overwrote_prior_research_packages": False,
        },
    }
    man_path = out / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes["manifest.json"] = sha256_file(man_path)
    manifest["output_hashes"] = hashes
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "SHA256SUMS").write_text(
        "\n".join(f"{digest}  {name}" for name, digest in sorted(hashes.items())) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "classify_joint_survival",
    "compose_enriched_package_family_sensitivity",
    "build_type_lane_joint_weighting",
    "build_family_joint_weighting",
    "build_headline_joint_survival",
    "build_type_lane_joint_profile_sensitivity",
    "build_joint_pairwise_sensitivity",
    "render_joint_interpretation",
]
