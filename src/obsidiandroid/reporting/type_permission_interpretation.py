"""Evidence-qualified interpretation of family-balanced permission findings.

Read-only. Consumes already-generated type-permission and pairwise diagnostics
for a completed run. Does not query databases or mutate source run artifacts.
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
    contract_metadata,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    COMPOSER_VERSION as TYPE_COMPOSER_VERSION,
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)
from obsidiandroid.reporting.type_permission_pairwise import (
    PAIRWISE_COMPOSER_VERSION,
)

INTERPRETATION_COMPOSER_VERSION = "1.0.0"
MAIN_TYPES = ("banker", "rat", "spyware", "adware")
EXPLORATORY_TYPES = ("backdoor", "dropper", "sms-trojan")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def compose_type_permission_interpretation(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write a concise Markdown interpretation under diagnostics."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_status = detect_source_run_status(run_root)
    type_dir = run_root / "diagnostics" / "type_permission_pattern_report"
    pair_dir = run_root / "diagnostics" / "type_permission_pairwise"
    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "type_permission_interpretation"
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory = _read_csv(type_dir / f"type_inventory_{run_id}.csv")
    lane_table = _read_csv(type_dir / f"lane_stratified_type_permissions_{run_id}.csv")
    coverage = _read_csv(type_dir / f"type_lane_coverage_matrix_{run_id}.csv")
    banker_dropper = _read_csv(type_dir / f"banker_dropper_comparison_{run_id}.csv")
    pairs = _read_csv(pair_dir / f"pairwise_all_{run_id}.csv")
    headline_pairs = _read_csv(pair_dir / f"pairwise_headline_strong_{run_id}.csv")
    if headline_pairs.empty:
        headline_pairs = _read_csv(pair_dir / f"pairwise_headline_{run_id}.csv")
    moderate = _read_csv(pair_dir / f"pairwise_headline_moderate_{run_id}.csv")
    if not moderate.empty:
        headline_pairs = pd.concat([headline_pairs, moderate], ignore_index=True)

    type_manifest_path = type_dir / f"type_permission_pattern_report_manifest_{run_id}.json"
    pair_manifest_path = pair_dir / f"type_permission_pairwise_manifest_{run_id}.json"
    type_manifest = json.loads(type_manifest_path.read_text(encoding="utf-8")) if type_manifest_path.is_file() else {}
    pair_manifest = json.loads(pair_manifest_path.read_text(encoding="utf-8")) if pair_manifest_path.is_file() else {}

    md = _render_interpretation(
        run_id=run_id,
        report_status=str(run_status["report_status"]),
        inventory=inventory,
        lane_table=lane_table,
        coverage=coverage,
        banker_dropper=banker_dropper,
        pairs=pairs,
        headline_pairs=headline_pairs,
        type_manifest=type_manifest,
        pair_manifest=pair_manifest,
        thresholds=dict(DEFAULT_THRESHOLDS),
    )
    report_path = out_dir / f"type_permission_interpretation_{run_id}.md"
    report_path.write_text(md, encoding="utf-8")
    (out_dir / "type_permission_interpretation.latest.md").write_text(md, encoding="utf-8")

    input_paths = {
        "type_inventory": type_dir / f"type_inventory_{run_id}.csv",
        "lane_stratified": type_dir / f"lane_stratified_type_permissions_{run_id}.csv",
        "pairwise_all": pair_dir / f"pairwise_all_{run_id}.csv",
        "pairwise_headline": pair_dir / f"pairwise_headline_{run_id}.csv",
    }
    input_hashes = {k: sha256_file(p) for k, p in input_paths.items() if p.is_file()}
    output_hashes = {report_path.name: sha256_file(report_path)}
    manifest = {
        "composer_version": INTERPRETATION_COMPOSER_VERSION,
        "type_composer_version": TYPE_COMPOSER_VERSION,
        "pairwise_composer_version": PAIRWISE_COMPOSER_VERSION,
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "generated_at_utc": generated_at,
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
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
        },
    }
    manifest_path = out_dir / f"type_permission_interpretation_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / f"type_permission_interpretation_manifest_{run_id}.sha256").write_text(
        sha256_file(manifest_path) + "\n", encoding="utf-8"
    )
    return manifest


def _type_meta(inventory: pd.DataFrame, type_slug: str) -> dict[str, Any]:
    if inventory.empty:
        return {}
    rows = inventory[inventory["type_slug"].astype(str) == type_slug]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    return row.to_dict()


def _top_lane_rows(
    lane_table: pd.DataFrame,
    *,
    type_slug: str,
    lane: str,
    status_allow: set[str] | None = None,
    n: int = 5,
) -> pd.DataFrame:
    if lane_table.empty:
        return lane_table
    frame = lane_table[
        (lane_table["type_slug"].astype(str) == type_slug)
        & (lane_table["protection_governance_lane"].astype(str) == lane)
    ].copy()
    if status_allow:
        frame = frame[frame["reportability_status"].isin(status_allow)]
    if frame.empty:
        return frame
    return frame.sort_values(
        ["family_balanced_prevalence_pct", "prevalence_pct", "odds_ratio"],
        ascending=[False, False, False],
    ).head(n)


def _fmt_perm_list(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_none under current gates_"
    parts = []
    for row in frame.itertuples(index=False):
        fb = getattr(row, "family_balanced_prevalence_pct", float("nan"))
        sw = getattr(row, "prevalence_pct", float("nan"))
        status = getattr(row, "reportability_status", "")
        parts.append(
            f"`{row.permission}` (SW {float(sw):.1f}% / FB {float(fb) if pd.notna(fb) else float('nan'):.1f}%; `{status}`)"
        )
    return "; ".join(parts)


def _render_interpretation(
    *,
    run_id: str,
    report_status: str,
    inventory: pd.DataFrame,
    lane_table: pd.DataFrame,
    coverage: pd.DataFrame,
    banker_dropper: pd.DataFrame,
    pairs: pd.DataFrame,
    headline_pairs: pd.DataFrame,
    type_manifest: dict[str, Any],
    pair_manifest: dict[str, Any],
    thresholds: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Live-corpus type permission interpretation (`{run_id}`)")
    lines.append("")
    lines.append(f"- Report status: **{report_status}**")
    lines.append(f"- Interpretation composer: `{INTERPRETATION_COMPOSER_VERSION}`")
    lines.append(f"- Protection-lane contract: `{PROTECTION_LANE_CONTRACT_VERSION}`")
    lines.append(
        "- Scope: declared-manifest permission evidence in this live dataset only; "
        "not runtime behavior; not a frozen-paper reproduction."
    )
    lines.append("")
    recon = type_manifest.get("type_accounting_reconciliation") or {}
    lines.append("## Dataset framing")
    lines.append("")
    lines.append(
        f"In this live dataset, prepared samples reconcile at "
        f"**{int(recon.get('prepared_sample_count', 0)):,}** "
        f"(inventory sum {int(recon.get('inventory_sample_sum', 0)):,}; "
        f"reconciles={bool(recon.get('reconciles'))}). "
        f"Permission-evidence sample count recorded by the type report: "
        f"**{int(type_manifest.get('permission_evidence_sample_count', 0)):,}**. "
        f"Known governed types: **{int(type_manifest.get('governed_known_type_count', type_manifest.get('represented_type_count', 0)))}**; "
        f"observed `type_slug` values: "
        f"**{int(type_manifest.get('observed_type_slug_count_including_unknown', type_manifest.get('represented_type_count', 0)))}** "
        f"including `unknown`."
    )
    lines.append("")
    lines.append(
        "Headline eligibility uses explicit thresholds "
        f"(min samples={thresholds['min_sample_support']}, "
        f"min families={thresholds['min_family_support']}, "
        f"min family-balanced prevalence={thresholds['min_family_balanced_prevalence']}, "
        f"min odds={thresholds['min_effect_odds']}, "
        f"dominance ceiling={thresholds['dominance_threshold']}, "
        f"FDR α={thresholds['fdr_alpha']})."
    )
    lines.append("")

    for type_slug in MAIN_TYPES:
        meta = _type_meta(inventory, type_slug)
        lines.append(f"## `{type_slug}`")
        lines.append("")
        if not meta:
            lines.append("Type not present in the inventory for this run.")
            lines.append("")
            continue
        lines.append(
            f"Among represented families in this live dataset: "
            f"**{int(meta.get('sample_count', 0)):,}** samples, "
            f"**{int(meta.get('active_families', 0))}** families, "
            f"largest family `{meta.get('largest_family_canonical', '')}` "
            f"({100.0 * float(meta.get('largest_family_share', 0)):.1f}% sample share), "
            f"main-comparison inclusion=`{meta.get('suppression_or_inclusion_reason', '')}`."
        )
        lines.append("")
        common = _top_lane_rows(
            lane_table,
            type_slug=type_slug,
            lane="aosp_normal",
            status_allow={"descriptive_common", "descriptive_type_enriched", "family_balanced_supported"},
        )
        # Prefer high sample-weighted common normals
        if not lane_table.empty:
            common = lane_table[
                (lane_table.type_slug == type_slug)
                & (lane_table.protection_governance_lane == "aosp_normal")
                & (lane_table.reportability_status == "descriptive_common")
            ].sort_values("prevalence_pct", ascending=False).head(5)
        dang = _top_lane_rows(
            lane_table,
            type_slug=type_slug,
            lane="aosp_dangerous",
            status_allow={"family_balanced_supported", "descriptive_type_enriched"},
        )
        unresolved = _top_lane_rows(
            lane_table, type_slug=type_slug, lane="aosp_protection_unresolved", n=3
        )
        oem = _top_lane_rows(lane_table, type_slug=type_slug, lane="oem_or_google", n=3)
        lines.append(f"1. Common, non-discriminative normals: {_fmt_perm_list(common)}")
        lines.append(
            f"2. Type-enriched normals: {_fmt_perm_list(_top_lane_rows(lane_table, type_slug=type_slug, lane='aosp_normal', status_allow={'family_balanced_supported', 'descriptive_type_enriched'}))}"
        )
        lines.append(f"3. Type-enriched dangerous: {_fmt_perm_list(dang)}")
        lines.append(
            f"4. Signature/privileged patterns: descriptive unresolved AOSP only — {_fmt_perm_list(unresolved)}. "
            "This is descriptive manifest evidence; structured signature/privileged flags are absent offline."
        )
        lines.append(f"5. OEM/Google patterns: {_fmt_perm_list(oem)}")
        if not headline_pairs.empty:
            hp = headline_pairs[headline_pairs.type_slug == type_slug].copy()
            if "headline_strength" in hp.columns:
                hp = hp[hp.headline_strength.isin(["strong", "moderate"])]
            hp = hp.head(5)
            if hp.empty:
                lines.append("6. Strong family-balanced pairs: _none reached strong/moderate tiers for this type_.")
            else:
                bits = [
                    f"`{r.permission_a}`+`{r.permission_b}` "
                    f"({getattr(r, 'headline_strength', '')}; {r.lane_pair_class}; "
                    f"FB {float(r.family_balanced_prevalence_pct):.1f}%; "
                    f"OR {float(r.odds_ratio_type_vs_rest):.2f})"
                    for r in hp.itertuples(index=False)
                ]
                lines.append("6. Strong/moderate family-balanced pairs: " + "; ".join(bits))
        else:
            lines.append("6. Strong family-balanced pairs: _pairwise table unavailable_.")
        # collapses
        if not lane_table.empty:
            cand = lane_table[
                (lane_table.type_slug == type_slug)
                & (lane_table.protection_governance_lane.isin(["aosp_normal", "aosp_dangerous"]))
            ].copy()
            cand["sw"] = pd.to_numeric(cand["prevalence_pct"], errors="coerce")
            cand["fb"] = pd.to_numeric(cand["family_balanced_prevalence_pct"], errors="coerce")
            cand["gap"] = cand["sw"] - cand["fb"]
            collapses = cand.sort_values("gap", ascending=False).head(3)
            if collapses.empty:
                lines.append("7. Sample-weighted patterns that collapse under family balance: _none highlighted_.")
            else:
                bits = [
                    f"`{r.permission}` (SW {float(r.sw):.1f}% → FB {float(r.fb) if pd.notna(r.fb) else float('nan'):.1f}%)"
                    for r in collapses.itertuples(index=False)
                ]
                lines.append(
                    "7. Sample-weighted patterns that collapse under family balance: " + "; ".join(bits)
                )
        else:
            lines.append("7. Sample-weighted patterns that collapse under family balance: _n/a_.")
        lines.append(
            f"8. Dominant-family caution: largest family contributes "
            f"{100.0 * float(meta.get('largest_family_share', 0)):.1f}% of `{type_slug}` samples "
            f"(`{meta.get('largest_family_canonical', '')}`)."
        )
        lines.append(
            "9. Evidence-coverage limits: permission-trends type tables cover the retained "
            "permission-trends vocabulary (not the full app-defined audit cardinality); "
            "unresolved AOSP protection tokens are not capability headlines."
        )
        lines.append("")

    lines.append("## Exploratory / family-dominated types")
    lines.append("")
    for type_slug in EXPLORATORY_TYPES:
        meta = _type_meta(inventory, type_slug)
        if not meta:
            continue
        lines.append(
            f"- `{type_slug}`: {int(meta.get('sample_count', 0)):,} samples, "
            f"{int(meta.get('active_families', 0))} families, "
            f"largest `{meta.get('largest_family_canonical', '')}` "
            f"({100.0 * float(meta.get('largest_family_share', 0)):.1f}%); "
            f"status=`{meta.get('suppression_or_inclusion_reason', '')}`. "
            "Treat findings as exploratory or family-dominated, not broad type behavior."
        )
    lines.append("")

    lines.append("## Banker versus dropper")
    lines.append("")
    b = _type_meta(inventory, "banker")
    d = _type_meta(inventory, "dropper")
    lines.append(
        "Both `banker` and `dropper` are exclusive top-level `type_slug` values in this taxonomy. "
        "In this live dataset the comparison is severely imbalanced: "
        f"banker n={int(b.get('sample_count', 0)):,} / families={int(b.get('active_families', 0))}; "
        f"dropper n={int(d.get('sample_count', 0)):,} / families={int(d.get('active_families', 0))}, "
        f"dominated by `{d.get('largest_family_canonical', '')}` "
        f"({100.0 * float(d.get('largest_family_share', 0)):.1f}%)."
    )
    lines.append("")
    lines.append(
        "Distinguish a dropper **type** finding from a Necro-dominated finding. "
        "Do not claim dual-role delivery behavior, and do not generalize from two dropper families."
    )
    if not banker_dropper.empty:
        top = banker_dropper.head(5)
        bits = []
        for row in top.itertuples(index=False):
            bits.append(
                f"`{row.permission}` (banker SW {float(row.banker_sample_weighted_pct):.1f}% vs "
                f"dropper SW {float(row.dropper_sample_weighted_pct):.1f}%)"
            )
        lines.append("Largest sample-weighted gaps (descriptive): " + "; ".join(bits))
    lines.append("")

    lines.append("## Family-balance collapses and suppressed results")
    lines.append("")
    if not pairs.empty and "reportability_status" in pairs.columns:
        counts = pairs["reportability_status"].value_counts()
        lines.append("Pairwise reportability in this live dataset:")
        lines.append("")
        for status, count in counts.items():
            lines.append(f"- `{status}`: {int(count):,}")
        lines.append("")
        dominated = pairs[pairs.reportability_status == "single_family_dominated"]
        lines.append(
            f"Single-family-dominated pairs remain visible (n={len(dominated):,}) but are not "
            "interpreted as broad type behavior."
        )
    if not lane_table.empty and "reportability_status" in lane_table.columns:
        lines.append("")
        lines.append("Type×permission lane-stratified reportability:")
        lines.append("")
        for status, count in lane_table["reportability_status"].value_counts().items():
            lines.append(f"- `{status}`: {int(count):,}")
    lines.append("")
    lines.append(
        f"Pairwise headline count (`family_balanced_supported`): "
        f"**{int(pair_manifest.get('pair_count_headline', 0)):,}** / "
        f"{int(pair_manifest.get('pair_count_total', 0)):,} mined pairs."
    )
    lines.append("")
    lines.append("## Language discipline")
    lines.append("")
    lines.append(
        "All claims above are scoped as: *In this live dataset…*, *Among represented families…*, "
        "*The sample-weighted pattern…*, *The family-balanced result…*, *This result is dominated by…*, "
        "*This is descriptive manifest evidence…*."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "INTERPRETATION_COMPOSER_VERSION",
    "compose_type_permission_interpretation",
]
