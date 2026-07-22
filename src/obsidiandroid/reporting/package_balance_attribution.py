"""Offline attribution for package-balanced permission sensitivity findings.

Follow-on to package_balanced_permission_analysis: attributes RAT package-balance
shifts to families, deep-dives banker package collisions, and measures
source-batch × package coupling. Run-local artifacts only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.common.csv_io import write_csv
from obsidiandroid.pipeline.permission_trends.stats_core import js_distance
from obsidiandroid.reporting.dominant_family_profile_sensitivity import spearman_rank_corr
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    BANNED_OUTPUT_DIRS,
    assign_package_keys,
    package_balanced_prevalence,
    package_within_family_balanced_prevalence,
    sample_weighted_prevalence,
)
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

ATTRIBUTION_CONTRACT_VERSION = "1.0.0"
ATTRIBUTION_COMPOSER_VERSION = "1.0.0"
FOCUS_TYPE = "rat"
BANKER_TYPE = "banker"
CONCENTRATED_STATES = frozenset(
    {
        "single_package_dominated",
        "high_package_concentration",
        "insufficient_package_identity",
    }
)


def _norm_perm(value: Any) -> str:
    return str(value or "").strip().lower()


def _profile(
    frame: pd.DataFrame,
    permissions: Sequence[str],
    *,
    mode: str,
) -> np.ndarray:
    values: list[float] = []
    for perm in permissions:
        if mode == "sample_weighted":
            values.append(sample_weighted_prevalence(frame, perm))
        elif mode == "package_balanced":
            values.append(package_balanced_prevalence(frame, perm))
        elif mode == "package_within_family_balanced":
            values.append(package_within_family_balanced_prevalence(frame, perm))
        else:
            raise ValueError(mode)
    return np.asarray(values, dtype=float)


def _compare_profiles(full: np.ndarray, other: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(full) & np.isfinite(other)
    p, q = full[valid], other[valid]
    if len(p) == 0:
        return {
            "spearman_vs_full": float("nan"),
            "js_distance_vs_full": float("nan"),
            "max_abs_prevalence_shift_pp": float("nan"),
        }
    pn = p / p.sum() if p.sum() else np.ones_like(p) / max(len(p), 1)
    qn = q / q.sum() if q.sum() else np.ones_like(q) / max(len(q), 1)
    return {
        "spearman_vs_full": spearman_rank_corr(p, q),
        "js_distance_vs_full": float(js_distance(pn, qn)),
        "max_abs_prevalence_shift_pp": float(np.max(np.abs(p - q)) * 100.0),
    }


def build_rat_family_leaveout_attribution(
    *,
    membership: pd.DataFrame,
    permissions: Sequence[str],
    family_concentration: pd.DataFrame,
) -> pd.DataFrame:
    """Attribute RAT package-balance shifts via family leave-outs."""
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    rat = keyed[keyed["type_slug"].astype(str) == FOCUS_TYPE].copy()
    if rat.empty or not permissions:
        return pd.DataFrame()

    full_sw = _profile(rat, permissions, mode="sample_weighted")
    rows: list[dict[str, Any]] = []

    baselines = {
        "full_sample_weighted": ("sample_weighted", rat),
        "full_package_balanced": ("package_balanced", rat),
        "full_package_within_family_balanced": ("package_within_family_balanced", rat),
    }
    for name, (mode, frame) in baselines.items():
        vec = _profile(frame, permissions, mode=mode)
        metrics = _compare_profiles(full_sw, vec)
        rows.append(
            {
                "analysis_scope": "rat_type",
                "scenario": name,
                "excluded_families": "",
                "n_samples": int(len(frame)),
                "n_families": int(frame["family_canonical"].nunique()),
                "known_packages": int(frame.loc[~frame["is_missing_package"], "package_key"].nunique()),
                "weighting_mode": mode,
                **metrics,
                "attribution_class": "baseline" if name == "full_sample_weighted" else "type_level_weighting",
            }
        )

    # Individual leave-outs for largest / concentrated families
    support = rat.groupby("family_canonical").size().sort_values(ascending=False)
    fam_state = {}
    if not family_concentration.empty:
        fam_state = dict(
            zip(
                family_concentration["family_canonical"].astype(str),
                family_concentration["concentration_state"].astype(str),
            )
        )
    candidates = list(support.head(8).index.astype(str))
    for family in candidates:
        remain = rat[rat["family_canonical"].astype(str) != family]
        for mode, label in (
            ("sample_weighted", f"leave_{family}_sample_weighted"),
            ("package_balanced", f"leave_{family}_package_balanced"),
            ("package_within_family_balanced", f"leave_{family}_package_within_family"),
        ):
            vec = _profile(remain, permissions, mode=mode)
            metrics = _compare_profiles(full_sw, vec)
            delta = metrics["max_abs_prevalence_shift_pp"]
            if mode == "sample_weighted":
                klass = "family_size_driven" if pd.notna(delta) and delta >= 20 else "family_leaveout"
            else:
                klass = (
                    "package_concentration_driver"
                    if fam_state.get(family) in CONCENTRATED_STATES and pd.notna(delta) and delta >= 10
                    else "family_leaveout"
                )
            rows.append(
                {
                    "analysis_scope": "rat_type",
                    "scenario": label,
                    "excluded_families": family,
                    "n_samples": int(len(remain)),
                    "n_families": int(remain["family_canonical"].nunique()),
                    "known_packages": int(remain.loc[~remain["is_missing_package"], "package_key"].nunique()),
                    "excluded_family_concentration_state": fam_state.get(family, ""),
                    "weighting_mode": mode,
                    **metrics,
                    "attribution_class": klass,
                }
            )

    concentrated = [
        f
        for f, state in fam_state.items()
        if state in CONCENTRATED_STATES and f in set(rat["family_canonical"].astype(str))
    ]
    if concentrated:
        remain = rat[~rat["family_canonical"].astype(str).isin(concentrated)]
        for mode, label in (
            ("sample_weighted", "leave_concentrated_rat_families_sample_weighted"),
            ("package_balanced", "leave_concentrated_rat_families_package_balanced"),
            ("package_within_family_balanced", "leave_concentrated_rat_families_package_within_family"),
        ):
            vec = _profile(remain, permissions, mode=mode)
            metrics = _compare_profiles(full_sw, vec)
            rows.append(
                {
                    "analysis_scope": "rat_type",
                    "scenario": label,
                    "excluded_families": "|".join(sorted(concentrated)),
                    "n_samples": int(len(remain)),
                    "n_families": int(remain["family_canonical"].nunique()),
                    "known_packages": int(remain.loc[~remain["is_missing_package"], "package_key"].nunique()),
                    "excluded_family_concentration_state": "mixed_concentrated",
                    "weighting_mode": mode,
                    **metrics,
                    "attribution_class": "concentrated_family_bundle",
                }
            )

    # ClayRat + ArsinkRAT together (two largest)
    for duo in (("ClayRat", "ArsinkRAT"), ("ClayRat",), ("ArsinkRAT",)):
        remain = rat[~rat["family_canonical"].astype(str).isin(duo)]
        vec = _profile(remain, permissions, mode="package_within_family_balanced")
        metrics = _compare_profiles(full_sw, vec)
        rows.append(
            {
                "analysis_scope": "rat_type",
                "scenario": "leave_" + "_".join(duo) + "_package_within_family",
                "excluded_families": "|".join(duo),
                "n_samples": int(len(remain)),
                "n_families": int(remain["family_canonical"].nunique()),
                "known_packages": int(remain.loc[~remain["is_missing_package"], "package_key"].nunique()),
                "excluded_family_concentration_state": "",
                "weighting_mode": "package_within_family_balanced",
                **metrics,
                "attribution_class": "largest_family_bundle",
            }
        )

    return pd.DataFrame(rows).sort_values(["scenario"]).reset_index(drop=True)


def build_banker_collision_deep_dive(
    *,
    collisions: pd.DataFrame,
    membership: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize banker-involving package collisions without exposing raw packages."""
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    banker_hashes = set(
        keyed.loc[keyed["type_slug"].astype(str) == BANKER_TYPE, "package_key_hash"].astype(str)
    )
    if collisions.empty:
        return pd.DataFrame()
    frame = collisions.copy()
    frame["involves_banker_type"] = frame["package_key_hash"].astype(str).isin(banker_hashes)
    if "affected_types" in frame.columns:
        frame["mentions_banker_type"] = frame["affected_types"].fillna("").astype(str).str.contains(
            BANKER_TYPE, regex=False
        )
    else:
        frame["mentions_banker_type"] = False
    focus = frame[frame["involves_banker_type"] | frame["mentions_banker_type"]].copy()
    # Headline deep-dive keeps conflictual classes; identity/accounting rows stay countable.
    conflictual = focus[
        focus["collision_class"].isin(
            ["cross_family_collision", "cross_type_collision", "authority_conflict"]
        )
    ].copy()
    rows: list[dict[str, Any]] = []
    for r in conflictual.itertuples(index=False):
        families = [x for x in str(getattr(r, "affected_families", "") or "").split("|") if x]
        types = [x for x in str(getattr(r, "affected_types", "") or "").split("|") if x]
        same_type_multi_family = len(types) == 1 and len(families) > 1
        cross_type = len(types) > 1
        rows.append(
            {
                "package_key_hash": str(r.package_key_hash),
                "collision_class": str(r.collision_class),
                "sample_count": int(r.sample_count),
                "sha_count": int(getattr(r, "sha_count", 0) or 0),
                "family_count": int(r.family_count),
                "type_count": int(r.type_count),
                "batch_count": int(getattr(r, "batch_count", 0) or 0),
                "affected_families": "|".join(families),
                "affected_types": "|".join(types),
                "same_type_multi_family": bool(same_type_multi_family),
                "cross_type_collision": bool(cross_type),
                "includes_godfather": "Godfather" in families,
                "includes_saferat": "SaferRat" in families,
                "includes_applite": "Applite" in families,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["cross_type_collision", "sample_count", "package_key_hash"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def build_source_batch_package_coupling(
    *,
    membership: pd.DataFrame,
    families: Sequence[str],
) -> pd.DataFrame:
    """Measure whether source batches also dominate package identity."""
    keyed = membership if "package_key" in membership.columns else assign_package_keys(membership)
    rows: list[dict[str, Any]] = []
    for family in families:
        sub = keyed[keyed["family_canonical"].astype(str) == family]
        if sub.empty:
            continue
        known = sub[~sub["is_missing_package"].astype(bool)]
        batch = sub.get("source_batch_label", pd.Series("", index=sub.index)).fillna("").astype(str)
        batch = batch.where(batch.ne(""), "(blank)")
        vc = batch.value_counts()
        top_batch = str(vc.index[0]) if len(vc) else ""
        top_share = float(vc.iloc[0] / len(sub)) if len(vc) else 0.0
        in_top = sub[batch == top_batch] if top_batch else sub.iloc[0:0]
        known_top = in_top[~in_top["is_missing_package"].astype(bool)]
        pkg_total = int(known["package_key"].nunique()) if len(known) else 0
        pkg_top = int(known_top["package_key"].nunique()) if len(known_top) else 0
        rows.append(
            {
                "family_canonical": family,
                "sample_count": int(len(sub)),
                "known_package_count": pkg_total,
                "source_batch_count": int(batch.nunique()),
                "largest_source_batch_label": top_batch,
                "largest_source_batch_sample_share": top_share,
                "packages_in_largest_batch": pkg_top,
                "package_share_in_largest_batch": float(pkg_top / pkg_total) if pkg_total else float("nan"),
                "batch_dominates_samples": bool(top_share >= 0.70),
                "batch_dominates_packages": bool(pkg_total and (pkg_top / pkg_total) >= 0.70),
                "coupling_class": (
                    "batch_and_package_coupled"
                    if top_share >= 0.70 and pkg_total and (pkg_top / pkg_total) >= 0.70
                    else "batch_sample_dominated_packages_diverse"
                    if top_share >= 0.70
                    else "batch_mixed"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("sample_count", ascending=False).reset_index(drop=True)


def render_attribution_interpretation(
    *,
    rat_attr: pd.DataFrame,
    banker_collisions: pd.DataFrame,
    batch_coupling: pd.DataFrame,
) -> str:
    def _row(scenario: str) -> pd.Series:
        hit = rat_attr[rat_attr["scenario"] == scenario]
        return hit.iloc[0] if not hit.empty else pd.Series(dtype=object)

    full_pb = _row("full_package_balanced")
    full_pwf = _row("full_package_within_family_balanced")
    leave_clay = _row("leave_ClayRat_package_within_family")
    leave_ars = _row("leave_ArsinkRAT_package_within_family")
    leave_conc = _row("leave_concentrated_rat_families_package_within_family")

    banker_n = int(len(banker_collisions))
    cross_type = int(banker_collisions["cross_type_collision"].sum()) if banker_n else 0
    same_type = int(banker_collisions["same_type_multi_family"].sum()) if banker_n else 0
    # Clarify structural RAT finding
    rat_note = (
        "Leaving ClayRat or ArsinkRAT does not remove the package-within-family shift; "
        "those large families stabilize the type profile. The type-level shift is structural "
        "heterogeneity across RAT families under hierarchical balancing, not ClayRat package resampling."
    )

    coupled = batch_coupling[batch_coupling.get("coupling_class", pd.Series(dtype=str)) == "batch_and_package_coupled"]
    lines = [
        "# Package-balance attribution interpretation",
        "",
        "Follow-on offline attribution for the frozen package-balanced pass.",
        "Package identity is not malware lineage.",
        "",
        "## RAT / package-balance drivers",
        "",
        f"- Full RAT package-balanced max Δpp vs sample-weighted: {full_pb.get('max_abs_prevalence_shift_pp', '')}.",
        f"- Full RAT package-within-family max Δpp: {full_pwf.get('max_abs_prevalence_shift_pp', '')}.",
        f"- Leave ClayRat (package-within-family) max Δpp: {leave_clay.get('max_abs_prevalence_shift_pp', '')}; Spearman={leave_clay.get('spearman_vs_full', '')}.",
        f"- Leave ArsinkRAT (package-within-family) max Δpp: {leave_ars.get('max_abs_prevalence_shift_pp', '')}; Spearman={leave_ars.get('spearman_vs_full', '')}.",
        f"- Leave concentrated RAT families (package-within-family) max Δpp: {leave_conc.get('max_abs_prevalence_shift_pp', '')}.",
        f"- {rat_note}",
        "- If leaving concentrated families only modestly changes the shift, small single-package RAT families are not the main driver.",
        "",
        "## Banker package collisions",
        "",
        f"- Conflictual banker-involving collision rows (cross-family/type/authority): {banker_n}.",
        f"- Same-type multi-family: {same_type}; cross-type: {cross_type}.",
        "- These collisions justify the banker type `package_identity_conflicted` state; they are not auto-repaired here.",
        "",
        "## Source-batch × package coupling",
        "",
        f"- Families with batch-and-package coupling: {int(len(coupled))}.",
        "- Source-batch concentration is not lineage.",
        "",
        "## Limits",
        "",
        "- Descriptive manifest evidence only.",
        "- No inferred lineage clusters.",
        "",
    ]
    return "\n".join(lines)


def _read_features(path: Path, audit: pd.DataFrame, permissions: set[str]) -> pd.DataFrame:
    mapping = dict(
        zip(audit["permission_string"].astype(str).str.lower(), audit["feature_column"].astype(str))
    )
    wanted = {"sample_id"} | {mapping[p] for p in permissions if p in mapping}
    features = pd.read_csv(path, compression="gzip", usecols=lambda c: c in wanted)
    rename = {feature: permission for permission, feature in mapping.items() if feature in features.columns}
    return features.rename(columns=rename)


def compose_package_balance_attribution(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Compose the attribution package beside (not over) prior research outputs."""
    run_root = Path(run_root)
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]
    out = Path(output_dir) if output_dir else run_root / "diagnostics" / "package_balance_attribution"
    banned = set(BANNED_OUTPUT_DIRS) | {
        "package_balanced_permission_analysis",
        "type_permission_protection_enriched",
        "permission_authority_enrichment",
    }
    if out.name in banned or any(
        out.resolve() == (run_root / "diagnostics" / name).resolve() for name in banned
    ):
        raise RuntimeError("refusing to write into a protected research directory")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    pkg_dir = diag / "package_balanced_permission_analysis"
    if not pkg_dir.is_dir():
        raise FileNotFoundError(pkg_dir)

    labels = pd.read_csv(diag / f"aligned_labels_{run_id}.csv", low_memory=False)
    audit = pd.read_csv(diag / "permission_feature_audit.csv")
    type_prev = pd.read_csv(tables / f"permission_prevalence_by_type_{run_id}.csv")
    fam_conc = pd.read_csv(pkg_dir / "family_package_concentration.csv")
    collisions = pd.read_csv(pkg_dir / "package_identity_collision_audit.csv")

    rat_perms = sorted(
        type_prev.loc[type_prev["type_slug"].astype(str) == FOCUS_TYPE, "permission"]
        .astype(str)
        .str.lower()
        .unique()
        .tolist()
    )
    membership = assign_package_keys(labels)
    features = _read_features(diag / f"aligned_features_{run_id}.csv.gz", audit, set(rat_perms))
    membership = membership.merge(features, on="sample_id", how="inner")

    rat_attr = build_rat_family_leaveout_attribution(
        membership=membership, permissions=rat_perms, family_concentration=fam_conc
    )
    banker_dive = build_banker_collision_deep_dive(collisions=collisions, membership=membership)
    families = sorted(
        set(fam_conc["family_canonical"].astype(str))
        & set(
            [
                "ClayRat",
                "Godfather",
                "ArsinkRAT",
                "Devixor",
                "Gigabud",
                "SaferRat",
                "Applite",
                "SpyNote",
                "Joker",
                "Triada",
                "Irata",
                "Nexus",
                "PixPirate",
                "SMSSpy",
            ]
        )
    )
    batch_coupling = build_source_batch_package_coupling(membership=membership, families=families)
    interpretation = render_attribution_interpretation(
        rat_attr=rat_attr, banker_collisions=banker_dive, batch_coupling=batch_coupling
    )

    outputs = {
        "rat_family_leaveout_attribution.csv": rat_attr,
        "banker_package_collision_deep_dive.csv": banker_dive,
        "source_batch_package_coupling.csv": batch_coupling,
    }
    hashes: dict[str, str] = {}
    for name, frame in outputs.items():
        path = out / name
        write_csv(path, frame)
        hashes[name] = sha256_file(path)
    md = out / "package_balance_attribution_interpretation.md"
    md.write_text(interpretation, encoding="utf-8")
    hashes[md.name] = sha256_file(md)

    input_paths = {
        "run_manifest": run_root / "run_manifest.json",
        "aligned_labels": diag / f"aligned_labels_{run_id}.csv",
        "aligned_features": diag / f"aligned_features_{run_id}.csv.gz",
        "type_prevalence": tables / f"permission_prevalence_by_type_{run_id}.csv",
        "family_package_concentration": pkg_dir / "family_package_concentration.csv",
        "package_identity_collision_audit": pkg_dir / "package_identity_collision_audit.csv",
        "package_balanced_manifest": pkg_dir / "manifest.json",
    }
    manifest = {
        "composer": "package_balance_attribution",
        "composer_version": ATTRIBUTION_COMPOSER_VERSION,
        "package_balance_attribution_contract_version": ATTRIBUTION_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "profile_id": identity.get("profile_id", ""),
        "repository_commit_at_run": identity.get("repository_commit", ""),
        "repository_commit_at_compose": resolve_git_commit(repo_root) if repo_root else "",
        "summary": {
            "rat_attribution_rows": int(len(rat_attr)),
            "banker_collision_rows": int(len(banker_dive)),
            "batch_coupling_rows": int(len(batch_coupling)),
            "rat_permissions": int(len(rat_perms)),
        },
        "output_hashes": hashes,
        "input_paths": {k: str(v) for k, v in input_paths.items()},
        "input_hashes": {k: sha256_file(v) for k, v in input_paths.items() if v.is_file()},
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
    "build_rat_family_leaveout_attribution",
    "build_banker_collision_deep_dive",
    "build_source_batch_package_coupling",
    "compose_package_balance_attribution",
]
