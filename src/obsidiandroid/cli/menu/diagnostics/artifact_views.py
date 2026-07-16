"""Artifact-oriented read-only views for the Data Diagnostics menu."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.cli.menu import diagnostics_banners
from obsidiandroid.cli.ui import display as du
from obsidiandroid.cli.menu.diagnostics.authority_coverage import (
    launch_family_type_authority_coverage_menu,
)
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict


def _read_json_payload(path: Path | None) -> dict[str, object]:
    """Read a JSON payload when present and shaped like a mapping."""
    if path is None:
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _format_artifact_stat(*, label: str, path: Path | None, run_diag: Path) -> tuple[str, str]:
    """Render an artifact path plus provenance in one stable stat line."""
    if path is None:
        return label, "missing"
    origin = oh.classify_artifact_origin(path, run_diag)
    return label, f"{du.format_console_path(path)} [{origin}]"


def launch_permission_intelligence_coverage_menu(
    *,
    read_latest_run_id,
    output_root: Path,
    first_existing_path_fn,
    governed_cohort_n_for_q2_fn,
) -> None:
    """Launch the permission intelligence coverage view."""
    du.print_section("Permission intelligence coverage")
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"

    rows: list[tuple[str, list[Path]]] = [
        ("Permission coverage summary", [rdiag / "permission_coverage_summary.csv", gdiag / "permission_coverage_summary.csv"]),
        ("Dataset foundation (JSON)", [rdiag / "dataset_foundation_summary.json", gdiag / "dataset_foundation_summary.json"]),
        ("Dataset foundation (gates + cohort)", [rdiag / "dataset_foundation_summary.md", gdiag / "dataset_foundation_summary.md"]),
        ("Modality contribution (Markdown)", [rdiag / "modality_contribution_summary.md", gdiag / "modality_contribution_summary.md"]),
        ("Modality contribution (JSON, Q2 metrics)", [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"]),
        ("Feature-set ablation (CSV)", [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"]),
        ("Feature-set ablation (Markdown)", [rdiag / "feature_set_ablation_summary.md", gdiag / "feature_set_ablation_summary.md"]),
        ("Vendor feature coverage summary", [rdiag / "vendor_feature_coverage_summary.csv", gdiag / "vendor_feature_coverage_summary.csv"]),
        ("Feature group survival (from column survival)", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
        (
            "Permission feature audit",
            [rdiag / "permission_feature_audit.csv", rdiag / f"permission_feature_audit_{rid}.csv"],
        ),
        ("Vendor leakage safety audit", [rdiag / "vendor_leakage_safety_audit.csv", gdiag / "vendor_leakage_safety_audit.csv"]),
        ("Permission signal quality (CSV)", [rdiag / "permission_signal_quality.csv", gdiag / "permission_signal_quality.csv"]),
        (
            "Permission signal quality (report)",
            [rdiag / "permission_signal_quality_report.md", gdiag / "permission_signal_quality_report.md"],
        ),
    ]
    used_global_mirror = False
    for label, candidates in rows:
        hit = first_existing_path_fn(candidates)
        stat_label, stat_value = _format_artifact_stat(label=label, path=hit, run_diag=rdiag)
        du.print_stat(stat_label, stat_value)
        if hit is not None and oh.classify_artifact_origin(hit, rdiag) == "global_latest_mirror":
            used_global_mirror = True

    q2 = read_json_dict(rdiag / "modality_contribution_summary.json") or read_json_dict(
        gdiag / "modality_contribution_summary.json"
    )
    if isinstance(q2, dict) and q2:
        du.print_subheader("Q2 snapshot (modality contribution)")
        gov_n = governed_cohort_n_for_q2_fn(rdiag=rdiag, gdiag=gdiag, q2=q2)
        du.print_stat("Governed cohort (denominator)", str(gov_n) if gov_n is not None else "—")
        du.print_stat(
            "Permission signal",
            f"{q2.get('permission_signal_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('permission_signal_pct'))})",
        )
        du.print_stat(
            "Vendor weak-support coverage",
            f"{q2.get('vendor_merge_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('vendor_merge_pct'))})",
        )
        pcols = q2.get("permission_feature_columns")
        du.print_stat(
            "Permission columns (fused / contract)",
            "—" if pcols is None or pcols == "" else str(pcols),
        )
        du.print_stat(
            "AV engines (observed / included in contract)",
            f"{q2.get('av_engines_observed', '—')} / {q2.get('av_engines_included', '—')}",
        )
        notes = q2.get("interpretation_notes")
        if isinstance(notes, list) and notes:
            du.print_subheader("Q2 interpretation (from JSON)")
            for line in notes[:5]:
                if isinstance(line, str) and line.strip():
                    du.print_note(line.strip())
        du.print_note(
            "Definitions: `permission_signal_pct` = cohort rows with permission-bag signal ÷ governed cohort; "
            "`vendor_merge_pct` = rows with parsed vendor weak-support metadata ÷ the same denominator."
        )
    else:
        du.print_note(
            "No modality_contribution_summary.json found for this run (or global mirror). "
            "Generate Q1–Q3 diagnostics for the run to populate Q2 permission intelligence."
        )

    if used_global_mirror:
        du.print_warning(
            "[MENU] Permission intelligence coverage is using at least one global latest mirror artifact rather than a run-scoped file."
        )

    du.print_info(
        "[MENU] Prefer run paths above; global output/diagnostics/ holds .latest mirrors when hygiene mode omits duplicates inside runs/. "
        "Per-column survival lives under Data Diagnostics → Feature matrix / modality coverage."
    )
    print("")


def launch_feature_matrix_modality_menu(
    *,
    read_latest_run_id,
    output_root: Path,
    first_existing_path_fn,
) -> None:
    """Launch the feature matrix/modality coverage view."""
    du.print_section("Feature matrix / modality coverage")
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    entries: list[tuple[str, list[Path]]] = [
        ("Feature contract", [oh.resolve_feature_contract_path(rdiag, rid)]),
        (
            "Modality contribution (JSON)",
            [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"],
        ),
        (
            "Feature-set ablation summary",
            [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"],
        ),
        (
            "Feature column survival",
            [
                rdiag / f"feature_column_survival_{rid}.csv",
                rdiag / "feature_column_survival.latest.csv",
                gdiag / "feature_column_survival.latest.csv",
            ],
        ),
        ("Feature group survival", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
    ]
    used_global_mirror = False
    for label, candidates in entries:
        hit = first_existing_path_fn(candidates)
        stat_label, stat_value = _format_artifact_stat(label=label, path=hit, run_diag=rdiag)
        du.print_stat(stat_label, stat_value)
        if hit is not None and oh.classify_artifact_origin(hit, rdiag) == "global_latest_mirror":
            used_global_mirror = True
    if used_global_mirror:
        du.print_warning(
            "[MENU] Feature matrix / modality coverage is using at least one global latest mirror artifact rather than a run-scoped file."
        )
    print("")


def launch_taxonomy_consistency_review_menu(
    *,
    read_latest_run_id,
    output_root: Path,
    first_existing_path_fn,
) -> None:
    """Launch the taxonomy consistency review view."""
    du.print_section("Taxonomy consistency review")
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    split_md_path = first_existing_path_fn(
        [
            rdiag / f"taxonomy_authority_split_{rid}.md",
            output_root / "diagnostics" / "taxonomy_authority_split.latest.md",
        ]
    )
    split_json_path = first_existing_path_fn(
        [
            rdiag / f"taxonomy_authority_split_{rid}.json",
            output_root / "diagnostics" / "taxonomy_authority_split.latest.json",
        ]
    )
    split_payload = _read_json_payload(split_json_path)
    split_json_origin = oh.classify_artifact_origin(split_json_path, rdiag)
    split_md_origin = oh.classify_artifact_origin(split_md_path, rdiag)
    split_blob = (
        split_payload.get("taxonomy_split")
        if isinstance(split_payload.get("taxonomy_split"), dict)
        else {}
    )
    summary_path = first_existing_path_fn([oh.resolve_taxonomy_consistency_summary_path(rdiag, rid)])
    summary_origin = oh.classify_artifact_origin(summary_path, rdiag)
    summary = read_json_dict(summary_path) if summary_path else {}
    if split_blob:
        rendering = (
            split_blob.get("type_authority_vs_rendering_mismatch")
            if isinstance(split_blob.get("type_authority_vs_rendering_mismatch"), dict)
            else {}
        )
        rendering_counts = rendering.get("counts") if isinstance(rendering.get("counts"), dict) else {}
        model_prediction = (
            split_blob.get("model_prediction_error")
            if isinstance(split_blob.get("model_prediction_error"), dict)
            else {}
        )
        authority_scopes = (
            split_payload.get("authority_scopes")
            if isinstance(split_payload.get("authority_scopes"), dict)
            else {}
        )
        global_scope = (
            authority_scopes.get("global_authority_catalog")
            if isinstance(authority_scopes.get("global_authority_catalog"), dict)
            else {}
        )
        run_scope = (
            authority_scopes.get("run_cohort_authority")
            if isinstance(authority_scopes.get("run_cohort_authority"), dict)
            else {}
        )
        du.print_subheader("Compact summary")
        du.print_stat("Authority split source mode", str(split_payload.get("source_mode", "—") or "—"))
        du.print_stat(
            "Artifact provenance",
            ", ".join(
                part
                for part in (
                    f"split_json={split_json_origin}" if split_json_origin != "missing" else "",
                    f"split_md={split_md_origin}" if split_md_origin != "missing" else "",
                    f"taxonomy_summary={summary_origin}" if summary_origin != "missing" else "",
                )
                if part
            )
            or "—",
        )
        du.print_stat(
            "Run-cohort authority scope",
            "available" if bool(run_scope.get("available", False)) else "unavailable",
        )
        du.print_stat(
            "Type/rendering mismatches",
            str(
                sum(
                    int(rendering_counts.get(key, 0) or 0)
                    for key in (
                        "type_mapping_mismatch",
                        "type_label_missing",
                        "type_label_noncanonical",
                        "label_family_mismatch",
                    )
                )
            ),
        )
        du.print_stat(
            "Type-guard suppressions",
            str(summary.get("type_guard_family_suppressed_count", "—")) if isinstance(summary, dict) else "—",
        )
        du.print_stat("Model prediction errors", str(model_prediction.get("count", "—")))
        du.print_stat(
            "Run authority-gap rows",
            str(
                sum(
                    int((run_scope.get("bucket_counts") or {}).get(key, 0) or 0)
                    for key in (
                        "resolved_but_no_authority_family",
                        "generic_label_candidate",
                        "authority_family_unknown_type",
                        "resolved_unknown",
                    )
                )
            ),
        )
        du.print_stat(
            "Global generic/coarse label rows",
            str((split_blob.get("generic_or_coarse_label_issue") or {}).get("global_row_count", "—")),
        )
        du.print_stat(
            "Global unknown-type family rows",
            str((split_blob.get("unknown_type_family_issue") or {}).get("global_row_count", "—")),
        )
        note = str(run_scope.get("note", "") or global_scope.get("note", "") or "").strip()
        if note:
            print(f"  Cohort source: {note}")
        if "global_latest_mirror" in {split_json_origin, split_md_origin, summary_origin}:
            du.print_warning(
                "[MENU] Taxonomy consistency review is using at least one global latest mirror artifact rather than a run-scoped file."
            )
        print("")
    elif summary:
        du.print_subheader("Compact summary")
        du.print_stat("Artifact provenance", summary_origin if summary_origin != "missing" else "—")
        du.print_stat("Rows evaluated", str(summary.get("rows_evaluated", "—")))
        du.print_stat("Taxonomy mismatches", str(summary.get("taxonomy_mismatch_count", "—")))
        du.print_stat("Claim-facing mismatches", str(summary.get("paper_facing_taxonomy_mismatch_count", "—")))
        du.print_stat("Type mismatches", str(summary.get("type_mismatch_count", "—")))
        du.print_stat("Type-guard suppressions", str(summary.get("type_guard_family_suppressed_count", "—")))
        du.print_stat("Missing type labels", str(summary.get("type_missing_label_count", "—")))
        du.print_stat("Family label mismatches", str(summary.get("family_label_mismatch_count", "—")))
        if summary_origin == "global_latest_mirror":
            du.print_warning(
                "[MENU] Taxonomy consistency summary came from the global latest mirror rather than this run's diagnostics directory."
            )
        print("")
    rows: list[tuple[str, list[Path]]] = [
        (
            "Start here",
            [rdiag / f"taxonomy_authority_split_{rid}.md", output_root / "diagnostics" / "taxonomy_authority_split.latest.md"],
        ),
        (
            "Split JSON",
            [rdiag / f"taxonomy_authority_split_{rid}.json", output_root / "diagnostics" / "taxonomy_authority_split.latest.json"],
        ),
        (
            "Authority gap summary",
            [rdiag / f"taxonomy_authority_gap_summary_{rid}.csv", output_root / "diagnostics" / "taxonomy_authority_gap_summary.latest.csv"],
        ),
        (
            "Consistency summary",
            [oh.resolve_taxonomy_consistency_summary_path(rdiag, rid)],
        ),
        (
            "Rendering mismatch rows",
            [oh.resolve_taxonomy_consistency_mismatches_path(rdiag, rid)],
        ),
        ("Model prediction-error rows", [oh.resolve_prediction_errors_path(rdiag, rid)]),
    ]
    du.print_subheader("Diagnostics")
    for label, candidates in rows:
        hit = first_existing_path_fn(candidates)
        stat_label, stat_value = _format_artifact_stat(label=label, path=hit, run_diag=rdiag)
        du.print_stat(stat_label, stat_value)
    print("  Prefer run-scoped names; global *.latest.* under output/diagnostics/ are mirrors only.")
    print("")


__all__ = [
    "launch_family_type_authority_coverage_menu",
    "launch_feature_matrix_modality_menu",
    "launch_permission_intelligence_coverage_menu",
    "launch_taxonomy_consistency_review_menu",
]
