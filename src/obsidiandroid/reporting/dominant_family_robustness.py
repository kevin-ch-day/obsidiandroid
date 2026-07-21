"""Dominant-family robustness audit for live-corpus type permissions.

Offline. Uses permission-trends family prevalence tables already present on a
completed run. Answers: does a type-level permission finding survive after
excluding the largest family (e.g. ClayRat for RAT, Godfather for banker)?

Does not query databases, does not enable Core persistence, and does not run
the pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import (
    DEFAULT_THRESHOLDS,
    PROTECTION_LANE_CONTRACT_VERSION,
    permission_lane_lookup,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

ROBUSTNESS_COMPOSER_VERSION = "1.0.0"
MAIN_TYPES = ("banker", "rat", "spyware", "adware")
CONTRAST_TYPES = ("banker", "rat")
FOCUS_LANES = ("aosp_normal", "aosp_dangerous")


def _trends_table(run_root: Path, stem: str, run_id: str) -> Path:
    return run_root / "bundles" / "permission_trends" / "tables" / f"{stem}_{run_id}.csv"


def _require_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def resolve_robustness_inputs(run_root: Path, run_id: str) -> dict[str, Path]:
    run_root = Path(run_root)
    paths = {
        "prevalence_by_family": _trends_table(run_root, "permission_prevalence_by_family", run_id),
        "family_support": _trends_table(run_root, "family_support_distribution", run_id),
        "prevalence_by_type": _trends_table(run_root, "permission_prevalence_by_type", run_id),
        "type_inventory": (
            run_root
            / "diagnostics"
            / "type_permission_pattern_report"
            / f"type_inventory_{run_id}.csv"
        ),
        "permission_feature_audit": run_root / "diagnostics" / "permission_feature_audit.csv",
    }
    return paths


def _family_means(frame: pd.DataFrame) -> tuple[float, int, int]:
    """Return (family_balanced_prevalence_pct, families_used, families_with_perm)."""
    if frame.empty:
        return float("nan"), 0, 0
    prev = pd.to_numeric(frame["prevalence_pct"], errors="coerce").fillna(0.0)
    return float(prev.mean()), int(len(frame)), int((prev > 0).sum())


def _sample_weighted(frame: pd.DataFrame) -> float:
    if frame.empty:
        return float("nan")
    support = pd.to_numeric(frame["family_support"], errors="coerce").fillna(0.0)
    prev = pd.to_numeric(frame["prevalence_pct"], errors="coerce").fillna(0.0) / 100.0
    total = float(support.sum())
    if total <= 0:
        return float("nan")
    return 100.0 * float((prev * support).sum() / total)


def classify_robustness(
    *,
    families_used_all: int,
    families_used_ex: int,
    family_balanced_all: float,
    family_balanced_ex: float,
    sample_weighted_all: float,
    sample_weighted_ex: float,
    dominant_share_of_positives: float,
    min_family_support: int = 3,
    collapse_fb_floor: float = 10.0,
    collapse_gap_pp: float = 20.0,
    dominant_positive_share: float = 0.70,
) -> str:
    """Explicit robustness class for a type×permission row."""
    if families_used_all < min_family_support:
        return "insufficient_family_support"
    if families_used_ex < min_family_support:
        return "insufficient_remainder_families"
    if dominant_share_of_positives >= dominant_positive_share:
        # Still compute remainder metrics, but label concentration.
        if pd.isna(family_balanced_ex) or float(family_balanced_ex) < collapse_fb_floor:
            return "dominant_family_driven"
    if pd.isna(family_balanced_all) or pd.isna(family_balanced_ex):
        return "insufficient_remainder_families"
    fb_gap = float(family_balanced_all) - float(family_balanced_ex)
    sw_gap = (
        float(sample_weighted_all) - float(sample_weighted_ex)
        if pd.notna(sample_weighted_all) and pd.notna(sample_weighted_ex)
        else 0.0
    )
    if float(family_balanced_ex) < collapse_fb_floor and fb_gap >= collapse_gap_pp:
        return "collapses_without_dominant"
    if fb_gap >= collapse_gap_pp or sw_gap >= collapse_gap_pp:
        return "weakens_without_dominant"
    if float(family_balanced_ex) >= collapse_fb_floor and fb_gap < collapse_gap_pp:
        return "robust_without_dominant"
    return "descriptive_remainder"


def build_dominant_family_robustness_table(
    prevalence_by_family: pd.DataFrame,
    type_inventory: pd.DataFrame,
    lane_lookup: dict[str, str],
    *,
    types: tuple[str, ...] = MAIN_TYPES,
    min_family_support: int = 3,
    focus_lanes: tuple[str, ...] | None = FOCUS_LANES,
) -> pd.DataFrame:
    """Per type×permission robustness metrics with/without largest family."""
    inv = type_inventory.copy()
    inv["type_slug"] = inv["type_slug"].astype(str)
    inv = inv[inv["type_slug"].isin(types)].copy()
    dominant_map = {
        str(r.type_slug): str(r.largest_family_canonical)
        for r in inv.itertuples(index=False)
        if str(getattr(r, "largest_family_canonical", "") or "").strip()
    }

    frame = prevalence_by_family.copy()
    frame["type_slug"] = frame["type_slug"].astype(str)
    frame["family_canonical"] = frame["family_canonical"].astype(str)
    frame["permission"] = frame["permission"].astype(str)
    frame["family_support"] = pd.to_numeric(frame["family_support"], errors="coerce").fillna(0)
    frame["positive_count"] = pd.to_numeric(frame["positive_count"], errors="coerce").fillna(0)
    frame["prevalence_pct"] = pd.to_numeric(frame["prevalence_pct"], errors="coerce").fillna(0.0)
    frame = frame[frame["type_slug"].isin(types)].copy()
    frame = frame[frame["family_support"] >= int(min_family_support)].copy()
    frame["protection_governance_lane"] = (
        frame["permission"].str.strip().str.lower().map(lane_lookup).fillna("unknown_unresolved")
    )
    if focus_lanes:
        frame = frame[frame["protection_governance_lane"].isin(focus_lanes)].copy()

    rows: list[dict[str, Any]] = []
    for (type_slug, permission), group in frame.groupby(["type_slug", "permission"], dropna=False):
        dominant = dominant_map.get(str(type_slug), "")
        all_fams = group
        ex = group[group["family_canonical"] != dominant] if dominant else group
        dom_rows = group[group["family_canonical"] == dominant] if dominant else group.iloc[0:0]

        sw_all = _sample_weighted(all_fams)
        sw_ex = _sample_weighted(ex)
        fb_all, n_all, n_pos_all = _family_means(all_fams)
        fb_ex, n_ex, n_pos_ex = _family_means(ex)

        total_pos = float(all_fams["positive_count"].sum())
        dom_pos = float(dom_rows["positive_count"].sum()) if not dom_rows.empty else 0.0
        dom_share = (dom_pos / total_pos) if total_pos > 0 else 0.0
        dom_prev = float(dom_rows.iloc[0]["prevalence_pct"]) if not dom_rows.empty else float("nan")
        dom_support = int(dom_rows.iloc[0]["family_support"]) if not dom_rows.empty else 0

        status = classify_robustness(
            families_used_all=n_all,
            families_used_ex=n_ex,
            family_balanced_all=fb_all,
            family_balanced_ex=fb_ex,
            sample_weighted_all=sw_all,
            sample_weighted_ex=sw_ex,
            dominant_share_of_positives=dom_share,
            min_family_support=min_family_support,
        )
        lane = str(all_fams.iloc[0]["protection_governance_lane"])
        rows.append(
            {
                "type_slug": type_slug,
                "permission": permission,
                "protection_governance_lane": lane,
                "dominant_family_canonical": dominant,
                "dominant_family_support": dom_support,
                "dominant_family_prevalence_pct": dom_prev,
                "dominant_share_of_positives": dom_share,
                "families_used_all": n_all,
                "families_with_permission_all": n_pos_all,
                "families_used_ex_dominant": n_ex,
                "families_with_permission_ex_dominant": n_pos_ex,
                "sample_weighted_prevalence_pct": sw_all,
                "sample_weighted_ex_dominant_pct": sw_ex,
                "family_balanced_prevalence_pct": fb_all,
                "family_balanced_ex_dominant_pct": fb_ex,
                "sw_collapse_gap_pct": (
                    sw_all - sw_ex if pd.notna(sw_all) and pd.notna(sw_ex) else float("nan")
                ),
                "fb_collapse_gap_pct": (
                    fb_all - fb_ex if pd.notna(fb_all) and pd.notna(fb_ex) else float("nan")
                ),
                "robustness_status": status,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["type_slug", "protection_governance_lane", "fb_collapse_gap_pct", "family_balanced_prevalence_pct"],
        ascending=[True, True, False, False],
    ).reset_index(drop=True)


def build_banker_rat_dangerous_contrast(robustness: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side banker vs RAT robustness for dangerous permissions."""
    if robustness.empty:
        return pd.DataFrame()
    dang = robustness[
        (robustness["protection_governance_lane"] == "aosp_dangerous")
        & (robustness["type_slug"].isin(CONTRAST_TYPES))
    ].copy()
    if dang.empty:
        return dang
    keep = [
        "permission",
        "dominant_family_canonical",
        "sample_weighted_prevalence_pct",
        "family_balanced_prevalence_pct",
        "family_balanced_ex_dominant_pct",
        "sw_collapse_gap_pct",
        "fb_collapse_gap_pct",
        "dominant_share_of_positives",
        "families_used_ex_dominant",
        "robustness_status",
    ]
    banker = dang[dang.type_slug == "banker"][keep].add_prefix("banker_")
    banker = banker.rename(columns={"banker_permission": "permission"})
    rat = dang[dang.type_slug == "rat"][keep].add_prefix("rat_")
    rat = rat.rename(columns={"rat_permission": "permission"})
    merged = banker.merge(rat, on="permission", how="outer")
    merged["fb_gap_banker_minus_rat"] = (
        pd.to_numeric(merged["banker_family_balanced_prevalence_pct"], errors="coerce")
        - pd.to_numeric(merged["rat_family_balanced_prevalence_pct"], errors="coerce")
    )
    merged["fb_ex_gap_banker_minus_rat"] = (
        pd.to_numeric(merged["banker_family_balanced_ex_dominant_pct"], errors="coerce")
        - pd.to_numeric(merged["rat_family_balanced_ex_dominant_pct"], errors="coerce")
    )
    merged["abs_fb_ex_gap"] = merged["fb_ex_gap_banker_minus_rat"].abs()
    return merged.sort_values("abs_fb_ex_gap", ascending=False).reset_index(drop=True)


def compose_dominant_family_robustness_report(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    min_family_support: int = 3,
) -> dict[str, Any]:
    """Write robustness tables + banker/RAT contrast markdown."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_status = detect_source_run_status(run_root)
    paths = resolve_robustness_inputs(run_root, run_id)

    prevalence_by_family = _require_csv(paths["prevalence_by_family"])
    type_inventory = _require_csv(paths["type_inventory"])
    audit = _require_csv(paths["permission_feature_audit"])
    lane_lookup = permission_lane_lookup(audit)

    robustness = build_dominant_family_robustness_table(
        prevalence_by_family,
        type_inventory,
        lane_lookup,
        min_family_support=min_family_support,
    )
    contrast = build_banker_rat_dangerous_contrast(robustness)
    status_summary = (
        robustness["robustness_status"]
        .value_counts()
        .rename_axis("robustness_status")
        .reset_index(name="row_count")
        if not robustness.empty
        else pd.DataFrame(columns=["robustness_status", "row_count"])
    )
    collapses = (
        robustness[robustness["robustness_status"].isin(
            ["collapses_without_dominant", "dominant_family_driven", "weakens_without_dominant"]
        )]
        .sort_values(["type_slug", "fb_collapse_gap_pct"], ascending=[True, False])
        if not robustness.empty
        else robustness
    )

    out_dir = (
        Path(output_dir)
        if output_dir
        else run_root / "diagnostics" / "dominant_family_robustness"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    derived = {
        "dominant_family_robustness": robustness,
        "banker_rat_dangerous_contrast": contrast,
        "robustness_status_summary": status_summary,
        "robustness_attention_rows": collapses,
    }
    output_hashes: dict[str, str] = {}
    for name, frame in derived.items():
        path = out_dir / f"{name}_{run_id}.csv"
        frame.to_csv(path, index=False)
        frame.to_csv(out_dir / f"{name}.latest.csv", index=False)
        output_hashes[path.name] = sha256_file(path)

    md = _render_markdown(
        run_id=run_id,
        report_status=str(run_status["report_status"]),
        type_inventory=type_inventory,
        status_summary=status_summary,
        contrast=contrast,
        collapses=collapses,
        min_family_support=min_family_support,
    )
    report_path = out_dir / f"dominant_family_robustness_report_{run_id}.md"
    report_path.write_text(md, encoding="utf-8")
    (out_dir / "dominant_family_robustness_report.latest.md").write_text(md, encoding="utf-8")
    output_hashes[report_path.name] = sha256_file(report_path)

    input_hashes = {k: sha256_file(p) for k, p in paths.items() if p.is_file()}
    manifest = {
        "composer_version": ROBUSTNESS_COMPOSER_VERSION,
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "generated_at_utc": generated_at,
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "main_types": list(MAIN_TYPES),
        "thresholds": {
            **dict(DEFAULT_THRESHOLDS),
            "min_family_support": min_family_support,
            "collapse_fb_floor": 10.0,
            "collapse_gap_pp": 20.0,
            "dominant_positive_share": 0.70,
        },
        "robustness_status_counts": {
            str(r.robustness_status): int(r.row_count) for r in status_summary.itertuples(index=False)
        }
        if not status_summary.empty
        else {},
        "input_sha256": input_hashes,
        "output_sha256": output_hashes,
        "report_markdown": str(report_path),
        "source_tables": {k: str(v) for k, v in paths.items()},
        "controls": {
            "no_database_access": True,
            "no_core_connection": True,
            "permissions_are_declared_capabilities_not_runtime_behavior": True,
            "generated_outputs_must_not_be_committed": True,
            "three_way_mining": False,
            "dual_role_modeling": False,
            "leave_dominant_family_only": True,
        },
    }
    manifest_path = out_dir / f"dominant_family_robustness_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / f"dominant_family_robustness_manifest_{run_id}.sha256").write_text(
        sha256_file(manifest_path) + "\n", encoding="utf-8"
    )
    return manifest


def _render_markdown(
    *,
    run_id: str,
    report_status: str,
    type_inventory: pd.DataFrame,
    status_summary: pd.DataFrame,
    contrast: pd.DataFrame,
    collapses: pd.DataFrame,
    min_family_support: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Dominant-family robustness audit (`{run_id}`)")
    lines.append("")
    lines.append(f"- Report status: **{report_status}**")
    lines.append(f"- Composer: `{ROBUSTNESS_COMPOSER_VERSION}`")
    lines.append(
        "- Method: recompute sample-weighted and family-balanced prevalence after "
        f"excluding each type's largest family (min family support ≥ {min_family_support})."
    )
    lines.append(
        "- Scope: declared-manifest permissions; offline completed-run artifacts only."
    )
    lines.append("")
    lines.append("## Dominant families in this live dataset")
    lines.append("")
    inv = type_inventory[type_inventory["type_slug"].astype(str).isin(MAIN_TYPES)].copy()
    if inv.empty:
        lines.append("Type inventory unavailable.")
    else:
        lines.append("| type | samples | families | dominant family | share |")
        lines.append("|---|---:|---:|---|---:|")
        for row in inv.sort_values("sample_count", ascending=False).itertuples(index=False):
            lines.append(
                f"| `{row.type_slug}` | {int(row.sample_count):,} | {int(row.active_families)} | "
                f"`{row.largest_family_canonical}` | {100.0 * float(row.largest_family_share):.1f}% |"
            )
    lines.append("")
    lines.append("## Robustness status summary")
    lines.append("")
    if status_summary.empty:
        lines.append("No rows.")
    else:
        lines.append("| robustness_status | rows |")
        lines.append("|---|---:|")
        for row in status_summary.itertuples(index=False):
            lines.append(f"| `{row.robustness_status}` | {int(row.row_count):,} |")
    lines.append("")
    lines.append("## Banker vs RAT dangerous contrast (family-balanced, with leave-dominant)")
    lines.append("")
    if contrast.empty:
        lines.append("No contrast rows.")
    else:
        lines.append(
            "| permission | banker FB | banker FB ex-dom | banker status | "
            "rat FB | rat FB ex-dom | rat status | ex-dom gap |"
        )
        lines.append("|---|---:|---:|---|---:|---:|---|---:|")
        for row in contrast.head(25).itertuples(index=False):
            lines.append(
                f"| `{row.permission}` | "
                f"{float(row.banker_family_balanced_prevalence_pct) if pd.notna(row.banker_family_balanced_prevalence_pct) else float('nan'):.1f} | "
                f"{float(row.banker_family_balanced_ex_dominant_pct) if pd.notna(row.banker_family_balanced_ex_dominant_pct) else float('nan'):.1f} | "
                f"`{row.banker_robustness_status}` | "
                f"{float(row.rat_family_balanced_prevalence_pct) if pd.notna(row.rat_family_balanced_prevalence_pct) else float('nan'):.1f} | "
                f"{float(row.rat_family_balanced_ex_dominant_pct) if pd.notna(row.rat_family_balanced_ex_dominant_pct) else float('nan'):.1f} | "
                f"`{row.rat_robustness_status}` | "
                f"{float(row.fb_ex_gap_banker_minus_rat) if pd.notna(row.fb_ex_gap_banker_minus_rat) else float('nan'):.1f} |"
            )
    lines.append("")
    lines.append("## Attention rows (weakens / collapses / dominant-driven)")
    lines.append("")
    if collapses.empty:
        lines.append("No attention rows.")
    else:
        lines.append("| type | lane | permission | FB | FB ex-dom | gap | dominant | status |")
        lines.append("|---|---|---|---:|---:|---:|---|---|")
        for row in collapses.head(30).itertuples(index=False):
            lines.append(
                f"| `{row.type_slug}` | `{row.protection_governance_lane}` | `{row.permission}` | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{float(row.family_balanced_ex_dominant_pct) if pd.notna(row.family_balanced_ex_dominant_pct) else float('nan'):.1f} | "
                f"{float(row.fb_collapse_gap_pct) if pd.notna(row.fb_collapse_gap_pct) else float('nan'):.1f} | "
                f"`{row.dominant_family_canonical}` | `{row.robustness_status}` |"
            )
    lines.append("")
    lines.append("## Reading guide")
    lines.append("")
    lines.append(
        "In this live dataset, a finding labeled `robust_without_dominant` survives after "
        "removing the largest family. `weakens_without_dominant` remains visible but shrinks. "
        "`collapses_without_dominant` / `dominant_family_driven` should be read as "
        "family-dominated, not broad type behavior. This is descriptive manifest evidence."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ROBUSTNESS_COMPOSER_VERSION",
    "build_dominant_family_robustness_table",
    "build_banker_rat_dangerous_contrast",
    "classify_robustness",
    "compose_dominant_family_robustness_report",
]
