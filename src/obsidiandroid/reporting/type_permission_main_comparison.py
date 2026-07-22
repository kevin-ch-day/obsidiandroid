"""Main-type differential permission comparison (high-ROI research surface).

Compares banker / RAT / spyware / adware side-by-side using already-generated
lane-stratified and pairwise diagnostics. Offline only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common.csv_io import optional_csv as _read
from obsidiandroid.reporting.permission_governance_lanes import (
    DEFAULT_THRESHOLDS,
    PROTECTION_LANE_CONTRACT_VERSION,
    classify_headline_strength,
    contract_metadata,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

MAIN_COMPARISON_COMPOSER_VERSION = "1.0.0"
MAIN_TYPES = ("banker", "rat", "spyware", "adware")
FOCUS_LANES = ("aosp_normal", "aosp_dangerous", "oem_platform", "google_platform")


def build_sw_fb_collapse_ledger(
    lane_table: pd.DataFrame,
    *,
    types: tuple[str, ...] = MAIN_TYPES,
    lanes: tuple[str, ...] = FOCUS_LANES,
    top_n: int = 25,
) -> pd.DataFrame:
    """Largest sample-weighted → family-balanced prevalence collapses."""
    if lane_table.empty:
        return pd.DataFrame()
    frame = lane_table[
        lane_table["type_slug"].astype(str).isin(types)
        & lane_table["protection_governance_lane"].astype(str).isin(lanes)
    ].copy()
    frame["sample_weighted_prevalence_pct"] = pd.to_numeric(frame["prevalence_pct"], errors="coerce")
    frame["family_balanced_prevalence_pct"] = pd.to_numeric(
        frame["family_balanced_prevalence_pct"], errors="coerce"
    )
    frame["collapse_gap_pct"] = (
        frame["sample_weighted_prevalence_pct"] - frame["family_balanced_prevalence_pct"]
    )
    frame = frame[frame["collapse_gap_pct"].notna() & (frame["collapse_gap_pct"] > 0)]
    frame = frame.sort_values(
        ["collapse_gap_pct", "sample_weighted_prevalence_pct"],
        ascending=[False, False],
    )
    cols = [
        "type_slug",
        "permission",
        "protection_governance_lane",
        "sample_weighted_prevalence_pct",
        "family_balanced_prevalence_pct",
        "collapse_gap_pct",
        "odds_ratio",
        "supporting_family_count",
        "reportability_status",
        "largest_family_canonical",
    ]
    return frame[[c for c in cols if c in frame.columns]].head(int(top_n)).reset_index(drop=True)


def build_main_type_permission_diff(
    lane_table: pd.DataFrame,
    *,
    types: tuple[str, ...] = MAIN_TYPES,
    lanes: tuple[str, ...] = ("aosp_normal", "aosp_dangerous"),
) -> pd.DataFrame:
    """Wide permission×lane table with SW/FB/OR columns per main type."""
    if lane_table.empty:
        return pd.DataFrame()
    frame = lane_table[
        lane_table["type_slug"].astype(str).isin(types)
        & lane_table["protection_governance_lane"].astype(str).isin(lanes)
    ].copy()
    if frame.empty:
        return frame
    frame["sw"] = pd.to_numeric(frame["prevalence_pct"], errors="coerce")
    frame["fb"] = pd.to_numeric(frame["family_balanced_prevalence_pct"], errors="coerce")
    frame["odds"] = pd.to_numeric(frame["odds_ratio"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for (permission, lane), group in frame.groupby(
        ["permission", "protection_governance_lane"], dropna=False
    ):
        row: dict[str, Any] = {
            "permission": permission,
            "protection_governance_lane": lane,
        }
        for type_slug in types:
            sub = group[group["type_slug"].astype(str) == type_slug]
            if sub.empty:
                row[f"{type_slug}_sw_pct"] = float("nan")
                row[f"{type_slug}_fb_pct"] = float("nan")
                row[f"{type_slug}_odds"] = float("nan")
                row[f"{type_slug}_reportability"] = ""
                continue
            r = sub.iloc[0]
            row[f"{type_slug}_sw_pct"] = float(r["sw"]) if pd.notna(r["sw"]) else float("nan")
            row[f"{type_slug}_fb_pct"] = float(r["fb"]) if pd.notna(r["fb"]) else float("nan")
            row[f"{type_slug}_odds"] = float(r["odds"]) if pd.notna(r["odds"]) else float("nan")
            row[f"{type_slug}_reportability"] = str(r.get("reportability_status") or "")
        # Discriminative score: max FB among types minus median FB (simple).
        fb_vals = [row[f"{t}_fb_pct"] for t in types if pd.notna(row[f"{t}_fb_pct"])]
        if fb_vals:
            row["max_fb_pct"] = float(max(fb_vals))
            row["fb_range_pct"] = float(max(fb_vals) - min(fb_vals))
        else:
            row["max_fb_pct"] = float("nan")
            row["fb_range_pct"] = float("nan")
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["protection_governance_lane", "fb_range_pct"], ascending=[True, False]).reset_index(
        drop=True
    )


def build_main_type_pair_spotlight(
    pairs: pd.DataFrame,
    *,
    types: tuple[str, ...] = MAIN_TYPES,
    strengths: tuple[str, ...] = ("strong", "moderate"),
    top_n_per_type: int = 8,
) -> pd.DataFrame:
    """Strong/moderate family-balanced pairs for main types only."""
    if pairs.empty:
        return pd.DataFrame()
    frame = pairs.copy()
    if "headline_strength" not in frame.columns and "reportability_status" in frame.columns:
        frame["headline_strength"] = [
            classify_headline_strength(
                reportability_status=str(r.reportability_status),
                family_balanced_prevalence=(
                    float(r.family_balanced_prevalence)
                    if "family_balanced_prevalence" in frame.columns and pd.notna(r.family_balanced_prevalence)
                    else None
                ),
            )
            for r in frame.itertuples(index=False)
        ]
    frame = frame[
        frame["type_slug"].astype(str).isin(types)
        & frame["headline_strength"].astype(str).isin(strengths)
    ].copy()
    if frame.empty:
        return frame
    frame = frame.sort_values(
        ["type_slug", "headline_strength", "odds_ratio_type_vs_rest", "family_balanced_prevalence_pct"],
        ascending=[True, True, False, False],
    )
    return frame.groupby("type_slug", as_index=False).head(int(top_n_per_type)).reset_index(drop=True)


def compose_main_type_permission_comparison(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write main-type differential tables + markdown brief."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_status = detect_source_run_status(run_root)
    type_dir = run_root / "diagnostics" / "type_permission_pattern_report"
    pair_dir = run_root / "diagnostics" / "type_permission_pairwise"
    out_dir = (
        Path(output_dir)
        if output_dir
        else run_root / "diagnostics" / "type_permission_main_comparison"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory = _read(type_dir / f"type_inventory_{run_id}.csv")
    lane_table = _read(type_dir / f"lane_stratified_type_permissions_{run_id}.csv")
    coverage = _read(type_dir / f"type_lane_coverage_matrix_{run_id}.csv")
    pairs = _read(pair_dir / f"pairwise_all_{run_id}.csv")
    if pairs.empty:
        pairs = _read(pair_dir / f"pairwise_headline_{run_id}.csv")

    profile = inventory[inventory["type_slug"].astype(str).isin(MAIN_TYPES)].copy() if not inventory.empty else inventory
    collapse = build_sw_fb_collapse_ledger(lane_table)
    perm_diff = build_main_type_permission_diff(lane_table)
    pair_spotlight = build_main_type_pair_spotlight(pairs)

    # Discriminators: high FB range dangerous/normal with at least one enriched status.
    discriminators = pd.DataFrame()
    if not perm_diff.empty:
        discriminators = perm_diff[
            perm_diff["fb_range_pct"].fillna(0) >= 15.0
        ].head(40).copy()

    derived = {
        "main_type_profile": profile,
        "main_type_permission_diff": perm_diff,
        "main_type_discriminators": discriminators,
        "main_type_pair_spotlight": pair_spotlight,
        "sw_fb_collapse_ledger": collapse,
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
        profile=profile,
        discriminators=discriminators,
        collapse=collapse,
        pair_spotlight=pair_spotlight,
        coverage=coverage,
    )
    report_path = out_dir / f"type_permission_main_comparison_{run_id}.md"
    report_path.write_text(md, encoding="utf-8")
    (out_dir / "type_permission_main_comparison.latest.md").write_text(md, encoding="utf-8")
    output_hashes[report_path.name] = sha256_file(report_path)

    input_paths = {
        "type_inventory": type_dir / f"type_inventory_{run_id}.csv",
        "lane_stratified": type_dir / f"lane_stratified_type_permissions_{run_id}.csv",
        "pairwise_all": pair_dir / f"pairwise_all_{run_id}.csv",
    }
    input_hashes = {k: sha256_file(p) for k, p in input_paths.items() if p.is_file()}
    manifest = {
        "composer_version": MAIN_COMPARISON_COMPOSER_VERSION,
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "generated_at_utc": generated_at,
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "main_types": list(MAIN_TYPES),
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "protection_lane_contract": contract_metadata(),
        "input_sha256": input_hashes,
        "output_sha256": output_hashes,
        "report_markdown": str(report_path),
        "controls": {
            "no_database_access": True,
            "no_core_connection": True,
            "permissions_are_declared_capabilities_not_runtime_behavior": True,
            "generated_outputs_must_not_be_committed": True,
            "three_way_mining": False,
            "dual_role_modeling": False,
        },
    }
    manifest_path = out_dir / f"type_permission_main_comparison_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / f"type_permission_main_comparison_manifest_{run_id}.sha256").write_text(
        sha256_file(manifest_path) + "\n", encoding="utf-8"
    )
    return manifest


def _render_markdown(
    *,
    run_id: str,
    report_status: str,
    profile: pd.DataFrame,
    discriminators: pd.DataFrame,
    collapse: pd.DataFrame,
    pair_spotlight: pd.DataFrame,
    coverage: pd.DataFrame,
) -> str:
    lines: list[str] = []
    lines.append(f"# Main-type permission differential (`{run_id}`)")
    lines.append("")
    lines.append(f"- Report status: **{report_status}**")
    lines.append(f"- Composer: `{MAIN_COMPARISON_COMPOSER_VERSION}`")
    lines.append(f"- Protection-lane contract: `{PROTECTION_LANE_CONTRACT_VERSION}`")
    lines.append(
        "- High-ROI surface for the live-corpus question: how declared permission patterns "
        "differ across banker / RAT / spyware / adware after family balance and governance lanes."
    )
    lines.append("")
    lines.append("## Type profiles")
    lines.append("")
    if profile.empty:
        lines.append("Inventory unavailable.")
    else:
        lines.append("| type | samples | families | largest family | share | inclusion |")
        lines.append("|---|---:|---:|---|---:|---|")
        for row in profile.sort_values("sample_count", ascending=False).itertuples(index=False):
            lines.append(
                f"| `{row.type_slug}` | {int(row.sample_count):,} | {int(row.active_families)} | "
                f"{row.largest_family_canonical} | {100.0 * float(row.largest_family_share):.1f}% | "
                f"`{row.suppression_or_inclusion_reason}` |"
            )
    lines.append("")
    lines.append("## Highest family-balanced discriminators (FB range ≥ 15pp)")
    lines.append("")
    if discriminators.empty:
        lines.append("No discriminators crossed the FB-range floor.")
    else:
        lines.append(
            "| lane | permission | banker FB | rat FB | spyware FB | adware FB | range |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for row in discriminators.head(20).itertuples(index=False):
            lines.append(
                f"| `{row.protection_governance_lane}` | `{row.permission}` | "
                f"{float(row.banker_fb_pct) if pd.notna(row.banker_fb_pct) else float('nan'):.1f} | "
                f"{float(row.rat_fb_pct) if pd.notna(row.rat_fb_pct) else float('nan'):.1f} | "
                f"{float(row.spyware_fb_pct) if pd.notna(row.spyware_fb_pct) else float('nan'):.1f} | "
                f"{float(row.adware_fb_pct) if pd.notna(row.adware_fb_pct) else float('nan'):.1f} | "
                f"{float(row.fb_range_pct) if pd.notna(row.fb_range_pct) else float('nan'):.1f} |"
            )
    lines.append("")
    lines.append("## Strong/moderate family-balanced pairs")
    lines.append("")
    if pair_spotlight.empty:
        lines.append("No strong/moderate pairs for main types.")
    else:
        lines.append("| type | strength | permission_a | permission_b | lanes | FB% | OR |")
        lines.append("|---|---|---|---|---|---:|---:|")
        for row in pair_spotlight.itertuples(index=False):
            lines.append(
                f"| `{row.type_slug}` | `{row.headline_strength}` | `{row.permission_a}` | "
                f"`{row.permission_b}` | `{row.permission_a_lane}`/`{row.permission_b_lane}` | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{float(row.odds_ratio_type_vs_rest):.2f} |"
            )
    lines.append("")
    lines.append("## Sample-weighted → family-balanced collapses")
    lines.append("")
    if collapse.empty:
        lines.append("No positive collapse gaps.")
    else:
        lines.append("| type | lane | permission | SW% | FB% | gap | status |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for row in collapse.head(20).itertuples(index=False):
            lines.append(
                f"| `{row.type_slug}` | `{row.protection_governance_lane}` | `{row.permission}` | "
                f"{float(row.sample_weighted_prevalence_pct):.1f} | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{float(row.collapse_gap_pct):.1f} | `{row.reportability_status}` |"
            )
    lines.append("")
    lines.append("## Reading guide")
    lines.append("")
    lines.append(
        "In this live dataset, prefer discriminators and `strong`/`moderate` pairs. "
        "Marginal FB headlines (5–10%) remain in pairwise tables but should not lead claims. "
        "This is descriptive manifest evidence among represented families — not runtime behavior."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MAIN_COMPARISON_COMPOSER_VERSION",
    "build_main_type_permission_diff",
    "build_main_type_pair_spotlight",
    "build_sw_fb_collapse_ledger",
    "compose_main_type_permission_comparison",
]
