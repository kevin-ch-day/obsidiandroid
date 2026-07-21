"""Robust type-contrast under joint package/family weighting.

Follow-on to enriched_package_family_sensitivity: tests whether permissions that
survive prevalence sensitivity also discriminate malware types under the same
weighting axes.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.reporting.enriched_package_family_sensitivity import BANNED_OUTPUT_DIRS as JOINT_BANNED
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    LINEAGE_BALANCE_UNAVAILABLE,
    assign_package_keys,
    package_balanced_prevalence,
    package_within_family_balanced_prevalence,
    sample_weighted_prevalence,
)
from obsidiandroid.reporting.permission_authority_enrichment import enrichment_lane_lookup
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

CONTRAST_CONTRACT_VERSION = "1.0.0"
CONTRAST_COMPOSER_VERSION = "1.0.0"
FOCUS_TYPES = ("rat", "banker", "spyware", "adware", "trojan")
CONTRAST_PAIRS = (
    "rat_vs_banker",
    "rat_vs_rest",
    "banker_vs_rest",
    "clayrat_vs_godfather",
)
CANDIDATE_SW_FLOOR = 0.15
CONTRAST_FLOOR_PP = 15.0
SHARED_BOTH_FLOOR = 0.70
BANNED_OUTPUT_DIRS = set(JOINT_BANNED) | {"enriched_package_family_sensitivity"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _indicator(frame: pd.DataFrame, permission: str) -> pd.Series:
    return (
        pd.to_numeric(frame.get(permission, pd.Series(0, index=frame.index)), errors="coerce")
        .fillna(0)
        .gt(0)
    )


def prevalence(frame: pd.DataFrame, permission: str, *, mode: str) -> float:
    """Return prevalence under the named weighting mode."""
    if mode == "sample_weighted":
        return sample_weighted_prevalence(frame, permission)
    if mode == "package_within_family_balanced":
        return package_within_family_balanced_prevalence(frame, permission)
    raise ValueError(mode)


def same_sign(a: float, b: float, *, eps: float = 1e-9) -> bool:
    """True when both deltas share a non-zero sign (or both near zero)."""
    if abs(a) < eps and abs(b) < eps:
        return True
    return (a > 0 and b > 0) or (a < 0 and b < 0)


def classify_contrast(
    *,
    sw_delta_pp: float,
    pwf_delta_pp: float,
    leave_delta_pp: float,
    sw_a: float,
    sw_b: float,
) -> str:
    """Classify whether a contrast survives package/leave sensitivity."""
    if pd.isna(sw_delta_pp) or pd.isna(pwf_delta_pp) or pd.isna(leave_delta_pp):
        return "exploratory_only"

    if (
        abs(sw_delta_pp) < CONTRAST_FLOOR_PP
        and abs(pwf_delta_pp) < CONTRAST_FLOOR_PP
        and abs(leave_delta_pp) < CONTRAST_FLOOR_PP
    ):
        if min(sw_a, sw_b) >= SHARED_BOTH_FLOOR:
            return "shared_background"
        return "exploratory_only"

    if (
        abs(sw_delta_pp) >= CONTRAST_FLOOR_PP
        and abs(pwf_delta_pp) >= CONTRAST_FLOOR_PP
        and abs(leave_delta_pp) >= CONTRAST_FLOOR_PP
        and same_sign(sw_delta_pp, pwf_delta_pp)
        and same_sign(sw_delta_pp, leave_delta_pp)
    ):
        return "robust_discriminator"

    if abs(sw_delta_pp) >= CONTRAST_FLOOR_PP and (
        abs(pwf_delta_pp) < CONTRAST_FLOOR_PP
        or abs(leave_delta_pp) < CONTRAST_FLOOR_PP
        or not same_sign(sw_delta_pp, pwf_delta_pp)
        or not same_sign(sw_delta_pp, leave_delta_pp)
    ):
        return "contrast_fragile"

    return "exploratory_only"


def _scope_frame(
    membership: pd.DataFrame,
    *,
    side: str,
    largest_by_type: dict[str, str],
) -> pd.DataFrame:
    if side == "rat":
        return membership[membership["type_slug"].astype(str) == "rat"]
    if side == "banker":
        return membership[membership["type_slug"].astype(str) == "banker"]
    if side == "rest_of_rat":
        return membership[membership["type_slug"].astype(str) != "rat"]
    if side == "rest_of_banker":
        return membership[membership["type_slug"].astype(str) != "banker"]
    if side == "clayrat":
        return membership[membership["family_canonical"].astype(str) == "ClayRat"]
    if side == "godfather":
        return membership[membership["family_canonical"].astype(str) == "Godfather"]
    if side == "rat_leave_largest":
        largest = largest_by_type.get("rat", "")
        return membership[
            (membership["type_slug"].astype(str) == "rat")
            & (membership["family_canonical"].astype(str) != largest)
        ]
    if side == "banker_leave_largest":
        largest = largest_by_type.get("banker", "")
        return membership[
            (membership["type_slug"].astype(str) == "banker")
            & (membership["family_canonical"].astype(str) != largest)
        ]
    if side == "rest_leave_rat_largest":
        largest = largest_by_type.get("rat", "")
        return membership[
            ~(
                (membership["type_slug"].astype(str) == "rat")
                & (membership["family_canonical"].astype(str) == largest)
            )
        ]
    if side == "rest_leave_banker_largest":
        largest = largest_by_type.get("banker", "")
        return membership[
            ~(
                (membership["type_slug"].astype(str) == "banker")
                & (membership["family_canonical"].astype(str) == largest)
            )
        ]
    raise ValueError(side)


def _pair_sides(contrast_pair: str) -> tuple[str, str, str, str]:
    """Return (side_a, side_b, leave_a, leave_b) scope names."""
    if contrast_pair == "rat_vs_banker":
        return "rat", "banker", "rat_leave_largest", "banker_leave_largest"
    if contrast_pair == "rat_vs_rest":
        return "rat", "rest_of_rat", "rat_leave_largest", "rest_leave_rat_largest"
    if contrast_pair == "banker_vs_rest":
        return "banker", "rest_of_banker", "banker_leave_largest", "rest_leave_banker_largest"
    if contrast_pair == "clayrat_vs_godfather":
        return "clayrat", "godfather", "clayrat", "godfather"
    raise ValueError(contrast_pair)


def build_type_prevalence(
    membership: pd.DataFrame,
    permissions: Sequence[str],
    lane_lookup: dict[str, str],
    largest_by_type: dict[str, str],
) -> pd.DataFrame:
    """Prevalence table for focus types under SW / PWF / leave-largest PWF."""
    rows: list[dict[str, Any]] = []
    for typ in FOCUS_TYPES:
        full = membership[membership["type_slug"].astype(str) == typ]
        leave = membership[
            (membership["type_slug"].astype(str) == typ)
            & (membership["family_canonical"].astype(str) != largest_by_type.get(typ, ""))
        ]
        for perm in permissions:
            rows.append(
                {
                    "type_slug": typ,
                    "permission": perm,
                    "headline_lane": lane_lookup.get(perm, "unknown_unresolved"),
                    "largest_family": largest_by_type.get(typ, ""),
                    "n_samples": int(len(full)),
                    "sample_weighted_prevalence": prevalence(full, perm, mode="sample_weighted"),
                    "package_within_family_prevalence": prevalence(
                        full, perm, mode="package_within_family_balanced"
                    ),
                    "leave_largest_family_pwf_prevalence": prevalence(
                        leave, perm, mode="package_within_family_balanced"
                    ),
                    "supporting_samples": int(_indicator(full, perm).sum()),
                }
            )
    return pd.DataFrame(rows)


def build_contrast_table(
    membership: pd.DataFrame,
    permissions: Sequence[str],
    *,
    lane_lookup: dict[str, str],
    largest_by_type: dict[str, str],
    identity_gate_by_type: dict[str, str],
    joint_survival: dict[str, str],
) -> pd.DataFrame:
    """Build contrast deltas and robustness classes for each permission × pair."""
    rows: list[dict[str, Any]] = []
    banker_gate = identity_gate_by_type.get("banker", "eligible")
    for contrast_pair in CONTRAST_PAIRS:
        side_a, side_b, leave_a, leave_b = _pair_sides(contrast_pair)
        frame_a = _scope_frame(membership, side=side_a, largest_by_type=largest_by_type)
        frame_b = _scope_frame(membership, side=side_b, largest_by_type=largest_by_type)
        leave_frame_a = _scope_frame(membership, side=leave_a, largest_by_type=largest_by_type)
        leave_frame_b = _scope_frame(membership, side=leave_b, largest_by_type=largest_by_type)
        for perm in permissions:
            sw_a = prevalence(frame_a, perm, mode="sample_weighted")
            sw_b = prevalence(frame_b, perm, mode="sample_weighted")
            pwf_a = prevalence(frame_a, perm, mode="package_within_family_balanced")
            pwf_b = prevalence(frame_b, perm, mode="package_within_family_balanced")
            leave_a_v = prevalence(leave_frame_a, perm, mode="package_within_family_balanced")
            leave_b_v = prevalence(leave_frame_b, perm, mode="package_within_family_balanced")
            sw_delta = (sw_a - sw_b) * 100.0
            pwf_delta = (pwf_a - pwf_b) * 100.0
            leave_delta = (leave_a_v - leave_b_v) * 100.0
            status = classify_contrast(
                sw_delta_pp=sw_delta,
                pwf_delta_pp=pwf_delta,
                leave_delta_pp=leave_delta,
                sw_a=sw_a,
                sw_b=sw_b,
            )
            banker_involved = contrast_pair in {"rat_vs_banker", "banker_vs_rest"}
            type_claim_eligible = not (
                banker_involved and banker_gate == "package_identity_conflicted"
            )
            rows.append(
                {
                    "contrast_pair": contrast_pair,
                    "permission": perm,
                    "headline_lane": lane_lookup.get(perm, "unknown_unresolved"),
                    "joint_survival_status_rat": joint_survival.get(perm, ""),
                    "side_a": side_a,
                    "side_b": side_b,
                    "n_side_a": int(len(frame_a)),
                    "n_side_b": int(len(frame_b)),
                    "sw_prevalence_a": sw_a,
                    "sw_prevalence_b": sw_b,
                    "pwf_prevalence_a": pwf_a,
                    "pwf_prevalence_b": pwf_b,
                    "leave_pwf_prevalence_a": leave_a_v,
                    "leave_pwf_prevalence_b": leave_b_v,
                    "sw_delta_pp": sw_delta,
                    "pwf_delta_pp": pwf_delta,
                    "leave_pwf_delta_pp": leave_delta,
                    "contrast_status": status,
                    "is_robust_discriminator": status == "robust_discriminator",
                    "banker_identity_gate": banker_gate if banker_involved else "n/a",
                    "type_claim_eligible": bool(type_claim_eligible),
                }
            )
    return pd.DataFrame(rows)


def build_survivor_family_consistency(
    membership: pd.DataFrame,
    survivor_permissions: Sequence[str],
    lane_lookup: dict[str, str],
) -> pd.DataFrame:
    """Per-RAT-family prevalence for type-level joint survivors."""
    rows: list[dict[str, Any]] = []
    rat = membership[membership["type_slug"].astype(str) == "rat"]
    for fam, group in rat.groupby("family_canonical", sort=True):
        for perm in survivor_permissions:
            rows.append(
                {
                    "family_canonical": str(fam),
                    "permission": perm,
                    "headline_lane": lane_lookup.get(perm, "unknown_unresolved"),
                    "n_samples": int(len(group)),
                    "sample_weighted_prevalence": prevalence(group, perm, mode="sample_weighted"),
                    "package_balanced_prevalence": package_balanced_prevalence(group, perm),
                }
            )
    return pd.DataFrame(rows)


def render_interpretation(
    *,
    contrasts: pd.DataFrame,
    survivors: Sequence[str],
    banker_gate: str,
) -> str:
    """Markdown interpretation of robust type contrasts."""
    lines = [
        "# Robust type-contrast interpretation",
        "",
        "Question: do joint prevalence survivors also discriminate types under PWF / leave-family?",
        f"Lineage balancing remains `{LINEAGE_BALANCE_UNAVAILABLE}`.",
        f"Banker type identity gate: `{banker_gate}`.",
        f"Contrast floor: {CONTRAST_FLOOR_PP:.0f} pp.",
        "",
        "## Joint survivors as discriminators (rat_vs_banker)",
        "",
    ]
    rvb = contrasts[contrasts["contrast_pair"] == "rat_vs_banker"]
    for perm in survivors:
        hit = rvb[rvb["permission"] == perm]
        if hit.empty:
            continue
        row = hit.iloc[0]
        lines.append(
            f"- `{perm}`: status=`{row.contrast_status}` "
            f"(type_claim_eligible={bool(row.type_claim_eligible)}); "
            f"SW Δpp={float(row.sw_delta_pp):.1f}, PWF Δpp={float(row.pwf_delta_pp):.1f}, "
            f"leave Δpp={float(row.leave_pwf_delta_pp):.1f} "
            f"(RAT {float(row.sw_prevalence_a):.0%} vs banker {float(row.sw_prevalence_b):.0%} SW)."
        )
    lines.extend(["", "## Robust discriminators by contrast pair", ""])
    for pair in CONTRAST_PAIRS:
        sub = contrasts[
            (contrasts["contrast_pair"] == pair)
            & (contrasts["contrast_status"] == "robust_discriminator")
        ].sort_values("pwf_delta_pp", key=lambda s: s.abs(), ascending=False)
        lines.append(f"- `{pair}`: {len(sub)} robust discriminators.")
        for _, row in sub.head(8).iterrows():
            lines.append(
                f"  - `{row.permission}` ({row.headline_lane}): "
                f"PWF Δpp={float(row.pwf_delta_pp):.1f}, leave Δpp={float(row.leave_pwf_delta_pp):.1f}."
            )
    frag = contrasts[
        (contrasts["contrast_pair"] == "rat_vs_banker")
        & (contrasts["contrast_status"] == "contrast_fragile")
    ]
    shared = contrasts[
        (contrasts["contrast_pair"] == "rat_vs_banker")
        & (contrasts["contrast_status"] == "shared_background")
    ]
    lines.extend(
        [
            "",
            "## rat_vs_banker fragility / shared background",
            "",
            f"- Contrast-fragile: {len(frag)}.",
            f"- Shared background: {len(shared)}.",
            "",
            "## Limits",
            "",
            "- Static declarations only.",
            "- Prevalence survival ≠ type discrimination.",
            "- Banker type package claims remain identity-gated (`type_claim_eligible=false`); "
            "use `clayrat_vs_godfather` as the family proxy for publishable banker contrast.",
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


def compose_robust_type_contrast(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Compose the robust type-contrast research package."""
    run_root = Path(run_root)
    identity = verify_completed_run(run_root, expected_run_id=run_id)
    run_id = identity["run_id"]
    out = Path(output_dir) if output_dir else run_root / "diagnostics" / "robust_type_contrast"
    if out.name in BANNED_OUTPUT_DIRS or any(
        out.resolve() == (run_root / "diagnostics" / name).resolve() for name in BANNED_OUTPUT_DIRS
    ):
        raise RuntimeError("refusing to write into a protected research directory")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    diag = run_root / "diagnostics"
    joint_dir = diag / "enriched_package_family_sensitivity"
    enrich = pd.read_csv(diag / "permission_authority_enrichment" / "permission_authority_enrichment.csv")
    lane_lookup = enrichment_lane_lookup(enrich)
    weighting = pd.read_csv(joint_dir / "type_lane_joint_weighting.csv")
    headlines = pd.read_csv(joint_dir / "headline_joint_survival.csv")
    gate = pd.read_csv(joint_dir / "joint_concentration_and_identity_gate.csv")
    pkg_type = pd.read_csv(diag / "package_balanced_permission_analysis" / "type_package_concentration.csv")

    survivors = (
        headlines[
            (headlines["type_slug"].astype(str) == "rat")
            & (headlines["joint_survival_status"].astype(str) == "survives_joint_sensitivity")
        ]["permission"]
        .map(_norm)
        .tolist()
    )
    joint_survival = {
        _norm(r.permission): str(r.joint_survival_status)
        for r in headlines[headlines["type_slug"].astype(str) == "rat"].itertuples(index=False)
    }

    sw_col = (
        "sample_weighted_prevalence"
        if "sample_weighted_prevalence" in weighting.columns
        else "prevalence"
    )
    cand = weighting[
        (weighting["type_slug"].astype(str).isin(["rat", "banker"]))
        & (pd.to_numeric(weighting[sw_col], errors="coerce") >= CANDIDATE_SW_FLOOR)
    ].copy()
    permissions = sorted(set(cand["permission"].map(_norm)) | set(survivors))

    type_gate = gate[gate["analysis_scope"].astype(str) == "type"]
    identity_gate_by_type = {
        str(r.type_slug): str(r.identity_gate)
        for r in type_gate.itertuples(index=False)
        if hasattr(r, "identity_gate")
    }
    if not identity_gate_by_type and "package_concentration_state" in pkg_type.columns:
        identity_gate_by_type = {
            str(r.type_slug): (
                "package_identity_conflicted"
                if str(r.package_concentration_state) == "package_identity_conflicted"
                else "eligible"
            )
            for r in pkg_type.itertuples(index=False)
        }

    labels = pd.read_csv(diag / f"aligned_labels_{run_id}.csv", low_memory=False)
    audit = pd.read_csv(diag / "permission_feature_audit.csv")
    membership = assign_package_keys(labels)
    features = _read_features(diag / f"aligned_features_{run_id}.csv.gz", audit, set(permissions))
    membership = membership.merge(features, on="sample_id", how="inner")

    largest_by_type = (
        membership[membership["type_slug"].astype(str).isin(list(FOCUS_TYPES))]
        .groupby(["type_slug", "family_canonical"])
        .size()
        .reset_index(name="n")
        .sort_values(["type_slug", "n", "family_canonical"], ascending=[True, False, True])
        .groupby("type_slug", sort=True)
        .first()["family_canonical"]
        .astype(str)
        .to_dict()
    )

    type_prev = build_type_prevalence(membership, permissions, lane_lookup, largest_by_type)
    contrasts = build_contrast_table(
        membership,
        permissions,
        lane_lookup=lane_lookup,
        largest_by_type=largest_by_type,
        identity_gate_by_type=identity_gate_by_type,
        joint_survival=joint_survival,
    )
    family_consistency = build_survivor_family_consistency(membership, survivors, lane_lookup)
    summary = (
        contrasts.groupby(["contrast_pair", "contrast_status"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["contrast_pair", "n"], ascending=[True, False])
    )
    banker_gate = identity_gate_by_type.get("banker", "")
    interpretation = render_interpretation(
        contrasts=contrasts, survivors=survivors, banker_gate=banker_gate
    )

    tables = {
        "permission_type_prevalence_weighted.csv": type_prev,
        "type_contrast_weighted.csv": contrasts,
        "contrast_status_summary.csv": summary,
        "survivor_family_consistency.csv": family_consistency,
    }
    hashes: dict[str, str] = {}
    for name, frame in tables.items():
        path = out / name
        frame.to_csv(path, index=False)
        hashes[name] = sha256_file(path)
    interp_path = out / "robust_type_contrast_interpretation.md"
    interp_path.write_text(interpretation + "\n", encoding="utf-8")
    hashes[interp_path.name] = sha256_file(interp_path)

    input_paths = {
        "joint_weighting": str(joint_dir / "type_lane_joint_weighting.csv"),
        "joint_headlines": str(joint_dir / "headline_joint_survival.csv"),
        "enrichment": str(diag / "permission_authority_enrichment" / "permission_authority_enrichment.csv"),
        "labels": str(diag / f"aligned_labels_{run_id}.csv"),
        "features": str(diag / f"aligned_features_{run_id}.csv.gz"),
    }
    manifest = {
        "robust_type_contrast_contract_version": CONTRAST_CONTRACT_VERSION,
        "composer_version": CONTRAST_COMPOSER_VERSION,
        "composer": "obsidiandroid.reporting.robust_type_contrast",
        "run_id": run_id,
        "profile_id": identity.get("profile_id", ""),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_commit_at_compose": resolve_git_commit(repo_root or Path.cwd()),
        "repository_commit_at_run": identity.get("git_commit", ""),
        "lineage_balance": LINEAGE_BALANCE_UNAVAILABLE,
        "thresholds": {
            "candidate_sw_floor": CANDIDATE_SW_FLOOR,
            "contrast_floor_pp": CONTRAST_FLOOR_PP,
            "shared_both_floor": SHARED_BOTH_FLOOR,
        },
        "boundaries": {
            "no_pipeline": True,
            "no_db": True,
            "no_core_writes": True,
            "prior_packages_immutable": True,
        },
        "input_paths": input_paths,
        "input_hashes": {k: sha256_file(Path(v)) for k, v in input_paths.items() if Path(v).is_file()},
        "summary": {
            "candidate_permissions": int(len(permissions)),
            "joint_survivor_permissions": int(len(survivors)),
            "contrast_rows": int(len(contrasts)),
            "robust_discriminator_counts": {
                pair: int(
                    (
                        (contrasts["contrast_pair"] == pair)
                        & (contrasts["contrast_status"] == "robust_discriminator")
                    ).sum()
                )
                for pair in CONTRAST_PAIRS
            },
            "banker_identity_gate": banker_gate,
            "largest_family_by_type": largest_by_type,
            "joint_survivors": survivors,
        },
        "output_hashes": hashes,
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
    "classify_contrast",
    "compose_robust_type_contrast",
    "build_contrast_table",
    "build_type_prevalence",
    "render_interpretation",
]
