"""Compact taxonomy/support tuning helpers for Data Diagnostics and review menus."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.cli.ui import display as du
from obsidiandroid.cli.menu import run_locator
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict


def _taxonomy_split_json_path(*, output_root: Path, diagnostics_dir: Path, run_id: str, first_existing_path_fn) -> Path | None:
    """Resolve the run-scoped taxonomy split JSON with global latest fallback."""
    return first_existing_path_fn(
        [
            diagnostics_dir / f"taxonomy_authority_split_{run_id}.json",
            output_root / "diagnostics" / "taxonomy_authority_split.latest.json",
        ]
    )


def _taxonomy_split_md_path(*, output_root: Path, diagnostics_dir: Path, run_id: str, first_existing_path_fn) -> Path | None:
    """Resolve the run-scoped taxonomy split Markdown with global latest fallback."""
    return first_existing_path_fn(
        [
            diagnostics_dir / f"taxonomy_authority_split_{run_id}.md",
            output_root / "diagnostics" / "taxonomy_authority_split.latest.md",
        ]
    )


def _taxonomy_target_surfaces_json_path(
    *,
    output_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    first_existing_path_fn,
) -> Path | None:
    """Resolve taxonomy target-surface JSON with global latest fallback."""
    return first_existing_path_fn(
        [
            diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json",
            output_root / "diagnostics" / "taxonomy_target_surfaces.latest.json",
        ]
    )


def _read_json_payload(path: Path | None) -> dict[str, object]:
    """Read a JSON payload when present and shaped like a mapping."""
    if path is None:
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _authority_gap_row_count(scope_blob: dict[str, object]) -> int:
    """Estimate authority-gap backlog rows from one authority scope."""
    if not isinstance(scope_blob, dict) or not scope_blob:
        return 0
    bucket_counts = scope_blob.get("bucket_counts")
    if not isinstance(bucket_counts, dict):
        return 0
    return sum(
        int(bucket_counts.get(key, 0) or 0)
        for key in (
            "resolved_but_no_authority_family",
            "generic_label_candidate",
            "authority_family_unknown_type",
            "resolved_unknown",
        )
    )


def _taxonomy_split_summary(
    *,
    output_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    first_existing_path_fn,
) -> tuple[dict[str, object], Path | None, Path | None]:
    """Resolve taxonomy split JSON/Markdown and derive compact menu counts."""
    split_json_path = _taxonomy_split_json_path(
        output_root=output_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        first_existing_path_fn=first_existing_path_fn,
    )
    split_md_path = _taxonomy_split_md_path(
        output_root=output_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        first_existing_path_fn=first_existing_path_fn,
    )
    payload = _read_json_payload(split_json_path)
    split = payload.get("taxonomy_split") if isinstance(payload.get("taxonomy_split"), dict) else {}
    rendering = (
        split.get("type_authority_vs_rendering_mismatch")
        if isinstance(split.get("type_authority_vs_rendering_mismatch"), dict)
        else {}
    )
    rendering_counts = rendering.get("counts") if isinstance(rendering.get("counts"), dict) else {}
    authority_scopes = payload.get("authority_scopes") if isinstance(payload.get("authority_scopes"), dict) else {}
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
    type_rendering_issue_count = sum(
        int(rendering_counts.get(key, 0) or 0)
        for key in (
            "type_mapping_mismatch",
            "type_label_missing",
            "type_label_noncanonical",
            "label_family_mismatch",
        )
    )
    prediction_blob = split.get("model_prediction_error") if isinstance(split.get("model_prediction_error"), dict) else {}
    return (
        {
            "payload": payload,
            "type_rendering_issue_count": type_rendering_issue_count,
            "model_prediction_error_count": int(prediction_blob.get("count", 0) or 0),
            "authority_gap_run_count": _authority_gap_row_count(run_scope),
            "authority_gap_global_count": _authority_gap_row_count(global_scope),
            "run_scope_available": bool(run_scope.get("available", False)) if isinstance(run_scope, dict) else False,
            "source_mode": str(payload.get("source_mode", "") or ""),
            "split_json_origin": oh.classify_artifact_origin(split_json_path, diagnostics_dir),
            "split_md_origin": oh.classify_artifact_origin(split_md_path, diagnostics_dir),
        },
        split_json_path,
        split_md_path,
    )


def launch_taxonomy_support_tuning_compact_menu(
    *,
    read_latest_run_id,
    output_root: Path,
    first_existing_path_fn,
    resolve_display_mode_fn,
) -> None:
    """Compact taxonomy/support tuning screen for next-run decisions."""
    du.print_section("Taxonomy & support tuning")
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    split_summary, split_json_path, split_md_path = _taxonomy_split_summary(
        output_root=output_root,
        diagnostics_dir=rdiag,
        run_id=rid,
        first_existing_path_fn=first_existing_path_fn,
    )
    taxonomy_path = first_existing_path_fn([oh.resolve_taxonomy_consistency_summary_path(rdiag, rid)])
    taxonomy = read_json_dict(taxonomy_path) if taxonomy_path else {}
    target_surfaces_path = _taxonomy_target_surfaces_json_path(
        output_root=output_root,
        diagnostics_dir=rdiag,
        run_id=rid,
        first_existing_path_fn=first_existing_path_fn,
    )
    target_surfaces = read_json_dict(target_surfaces_path) if target_surfaces_path else {}
    label_strategy = target_surfaces.get("label_strategy") if isinstance(target_surfaces.get("label_strategy"), dict) else {}
    fam_audit_path = first_existing_path_fn(
        [rdiag / "sql_governed_family_label_taxonomy_audit.csv", rdiag / "family_label_taxonomy_audit.csv"]
    )
    support_preview_path = first_existing_path_fn(
        [rdiag / "sql_governed_support_threshold_preview.csv", rdiag / "support_threshold_preview.csv"]
    )
    low_support_path = first_existing_path_fn([rdiag / "low_support_families.csv"])
    trained_registry_path = first_existing_path_fn([rdiag / f"trained_family_registry_{rid}.csv"])
    family_distribution_path = first_existing_path_fn([rdiag / "family_distribution.csv"])
    authority_review_path = first_existing_path_fn([oh.resolve_taxonomy_type_authority_review_path(rdiag, rid)])
    rendering_csv_path = first_existing_path_fn(
        [
            oh.resolve_taxonomy_consistency_mismatches_path(rdiag, rid),
            rdiag / f"taxonomy_rendering_mismatches_{rid}.csv",
            output_root / "diagnostics" / "taxonomy_rendering_mismatches.latest.csv",
        ]
    )
    model_error_csv_path = first_existing_path_fn(
        [
            oh.resolve_prediction_errors_path(rdiag, rid),
            rdiag / f"taxonomy_model_prediction_errors_{rid}.csv",
            output_root / "diagnostics" / "taxonomy_model_prediction_errors.latest.csv",
        ]
    )
    authority_gap_csv_path = first_existing_path_fn(
        [
            rdiag / f"taxonomy_authority_gap_summary_{rid}.csv",
            output_root / "diagnostics" / "taxonomy_authority_gap_summary.latest.csv",
        ]
    )

    tax_total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) if taxonomy else 0
    claim_facing_tax_total = int(
        taxonomy.get("paper_facing_taxonomy_mismatch_count", tax_total) or 0
    ) if taxonomy else 0
    type_issues = int(split_summary.get("type_rendering_issue_count", 0) or 0) if split_summary else (
        int(taxonomy.get("type_mismatch_count", 0) or 0)
        + int(taxonomy.get("type_noncanonical_count", 0) or 0)
        + int(taxonomy.get("type_missing_label_count", 0) or 0)
    ) if taxonomy else 0
    model_prediction_errors = int(split_summary.get("model_prediction_error_count", 0) or 0) if split_summary else int(
        taxonomy.get("prediction_error_count", 0) or 0
    ) if taxonomy else 0
    authority_gap_run_count = int(split_summary.get("authority_gap_run_count", 0) or 0) if split_summary else 0
    authority_gap_global_count = int(split_summary.get("authority_gap_global_count", 0) or 0) if split_summary else 0
    taxonomy_ready = bool(split_json_path or taxonomy_path)
    du.print_stat("Taxonomy health", "YELLOW" if (tax_total > 0 or model_prediction_errors > 0) else ("GREEN" if taxonomy_ready else "RED"))
    du.print_stat("Model prediction errors", model_prediction_errors if taxonomy_ready else "—")
    du.print_stat("Authority gap rows (run/global)", f"{authority_gap_run_count} / {authority_gap_global_count}" if split_json_path else "—")
    du.print_stat("Rendering / claim mismatch", f"{type_issues} rendering | {claim_facing_tax_total if taxonomy else '—'} claim-facing")
    split_json_origin = str(split_summary.get("split_json_origin", "") or "")
    split_md_origin = str(split_summary.get("split_md_origin", "") or "")
    target_surfaces_origin = oh.classify_artifact_origin(target_surfaces_path, rdiag)
    taxonomy_origin = oh.classify_artifact_origin(taxonomy_path, rdiag)
    if split_json_origin or taxonomy_origin:
        du.print_stat(
            "Artifact provenance",
            ", ".join(
                part
                for part in (
                    f"split_json={split_json_origin}" if split_json_origin else "",
                    f"split_md={split_md_origin}" if split_md_origin else "",
                    f"taxonomy_summary={taxonomy_origin}" if taxonomy_origin else "",
                    f"target_surfaces={target_surfaces_origin}" if target_surfaces_origin != "missing" else "",
                )
                if part
            )
            or "—",
        )
    if "global_latest_mirror" in {split_json_origin, split_md_origin, taxonomy_origin, target_surfaces_origin}:
        du.print_warning(
            "[MENU] One or more taxonomy tuning artifacts came from the global latest mirror, not this run's diagnostics directory."
        )
    if label_strategy:
        du.print_subheader("Target surface")
        du.print_stat("Preferred family target", str(label_strategy.get("preferred_family_target", "—") or "—"))
        du.print_stat("Preferred type target", str(label_strategy.get("preferred_type_target", "—") or "—"))
        du.print_stat("Avoid for primary claims", ", ".join(label_strategy.get("avoid_for_primary_claims", [])) or "—")

    min_support = "—"
    families_before = retained = dropped = dropped_samples = near_threshold = "—"
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty:
            if "configured_min_samples_per_family" in fam_df.columns:
                min_support = int(pd.to_numeric(fam_df["configured_min_samples_per_family"], errors="coerce").dropna().iloc[0])
            families_before = int(len(fam_df))
            if "support_status" in fam_df.columns:
                retained = int((fam_df["support_status"].astype(str) == "retained").sum())
                dropped = int((fam_df["support_status"].astype(str).str.contains("dropped", na=False)).sum())
            if "aligned_rows" in fam_df.columns and "support_status" in fam_df.columns:
                dropped_samples = int(pd.to_numeric(fam_df.loc[fam_df["support_status"].astype(str).str.contains("dropped", na=False), "aligned_rows"], errors="coerce").fillna(0).sum())
            if isinstance(min_support, int) and "aligned_rows" in fam_df.columns:
                counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0)
                near_threshold = int(((counts >= max(0, min_support - 2)) & (counts < min_support)).sum())
    du.print_subheader("Support gate")
    du.print_stat("Support threshold", f"n>={min_support}" if min_support != "—" else "—")
    du.print_stat("Families before / retained / dropped", f"{families_before} / {retained} / {dropped}")
    du.print_stat("Dropped samples (estimate)", dropped_samples)
    du.print_stat("Families near threshold", near_threshold)

    du.print_subheader("Tune next")
    if tax_total > 0:
        print("1. Review taxonomy authority split first; keep rendering mismatches separate from model prediction errors.")
    if authority_gap_run_count > 0 or authority_gap_global_count > 0:
        print("2. Use authority-gap queues for DB/type curation; do not treat them as model-family errors.")
    if isinstance(near_threshold, int) and near_threshold > 0:
        print("3. Review families just below threshold before changing cohort/profile support settings.")
    if label_strategy:
        print("4. Train on authoritative family_id/type_slug surfaces; keep raw category_primary as audit-only.")
    print("5. Cross-check retained/dropped families with trained_family_registry and support_threshold_preview.")

    du.print_subheader("Diagnostics")
    du.print_stat("Start here", du.format_console_path(split_md_path) if split_md_path else "missing")
    du.print_stat("Split JSON", du.format_console_path(split_json_path) if split_json_path else "missing")
    du.print_stat("Model errors", du.format_console_path(model_error_csv_path) if model_error_csv_path else "missing")
    du.print_stat("Authority gaps", du.format_console_path(authority_gap_csv_path) if authority_gap_csv_path else "missing")
    du.print_stat("Support preview", du.format_console_path(support_preview_path) if support_preview_path else "missing")
    du.print_stat("Family audit", du.format_console_path(fam_audit_path) if fam_audit_path else "missing")
    if resolve_display_mode_fn() != "compact":
        du.print_stat("Low-support families", du.format_console_path(low_support_path) if low_support_path else "missing")
        du.print_stat("Trained registry", du.format_console_path(trained_registry_path) if trained_registry_path else "missing")
        du.print_stat("Family distribution", du.format_console_path(family_distribution_path) if family_distribution_path else "missing")
    print("")


def build_taxonomy_support_tuning_snapshot(*, run_id: str, output_root: Path, first_existing_path_fn) -> dict[str, object]:
    """Build compact taxonomy/support tuning snapshot from existing diagnostics artifacts."""
    rdiag = run_locator.resolve_run_root_for_run_id(run_id, output_base=output_root) / "diagnostics"
    split_summary, split_json_path, split_md_path = _taxonomy_split_summary(
        output_root=output_root,
        diagnostics_dir=rdiag,
        run_id=run_id,
        first_existing_path_fn=first_existing_path_fn,
    )
    taxonomy_path = first_existing_path_fn([oh.resolve_taxonomy_consistency_summary_path(rdiag, run_id)])
    taxonomy = read_json_dict(taxonomy_path) if taxonomy_path else {}
    target_surfaces_path = _taxonomy_target_surfaces_json_path(
        output_root=output_root,
        diagnostics_dir=rdiag,
        run_id=run_id,
        first_existing_path_fn=first_existing_path_fn,
    )
    target_surfaces = read_json_dict(target_surfaces_path) if target_surfaces_path else {}
    label_strategy = target_surfaces.get("label_strategy") if isinstance(target_surfaces.get("label_strategy"), dict) else {}
    fam_audit_path = first_existing_path_fn(
        [rdiag / "sql_governed_family_label_taxonomy_audit.csv", rdiag / "family_label_taxonomy_audit.csv"]
    )
    support_preview_path = first_existing_path_fn(
        [rdiag / "sql_governed_support_threshold_preview.csv", rdiag / "support_threshold_preview.csv"]
    )

    tax_total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) if taxonomy else 0
    claim_facing_tax_total = int(
        taxonomy.get("paper_facing_taxonomy_mismatch_count", tax_total) or 0
    ) if taxonomy else 0
    type_issues = int(split_summary.get("type_rendering_issue_count", 0) or 0) if split_summary else (
        int(taxonomy.get("type_mismatch_count", 0) or 0)
        + int(taxonomy.get("type_noncanonical_count", 0) or 0)
        + int(taxonomy.get("type_missing_label_count", 0) or 0)
    ) if taxonomy else 0
    model_prediction_errors = int(split_summary.get("model_prediction_error_count", 0) or 0) if split_summary else int(
        taxonomy.get("prediction_error_count", 0) or 0
    ) if taxonomy else 0
    authority_gap_run_count = int(split_summary.get("authority_gap_run_count", 0) or 0) if split_summary else 0
    authority_gap_global_count = int(split_summary.get("authority_gap_global_count", 0) or 0) if split_summary else 0
    taxonomy_ready = bool(split_json_path or taxonomy_path)

    min_support: int | str = "—"
    families_before: int | str = "—"
    retained: int | str = "—"
    dropped: int | str = "—"
    dropped_samples: int | str = "—"
    near_threshold: int | str = "—"
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty:
            if "configured_min_samples_per_family" in fam_df.columns:
                vals = pd.to_numeric(fam_df["configured_min_samples_per_family"], errors="coerce").dropna()
                if not vals.empty:
                    min_support = int(vals.iloc[0])
            families_before = int(len(fam_df))
            if "support_status" in fam_df.columns:
                retained = int((fam_df["support_status"].astype(str) == "retained").sum())
                dropped = int((fam_df["support_status"].astype(str).str.contains("dropped", na=False)).sum())
            if "aligned_rows" in fam_df.columns and "support_status" in fam_df.columns:
                dropped_samples = int(
                    pd.to_numeric(
                        fam_df.loc[fam_df["support_status"].astype(str).str.contains("dropped", na=False), "aligned_rows"],
                        errors="coerce",
                    ).fillna(0).sum()
                )
            if isinstance(min_support, int) and "aligned_rows" in fam_df.columns:
                counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0)
                near_threshold = int(((counts >= max(0, min_support - 2)) & (counts < min_support)).sum())

    threshold_sensitivity: list[dict[str, int]] = []
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty and "aligned_rows" in fam_df.columns:
            counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0).astype(int)
            for t in (5, 10, 15, 20, 25):
                retained_mask = counts >= t
                retained_families = int(retained_mask.sum())
                dropped_families = int((~retained_mask).sum())
                retained_samples = int(counts[retained_mask].sum())
                dropped_samples_t = int(counts[~retained_mask].sum())
                threshold_sensitivity.append(
                    {
                        "threshold": int(t),
                        "retained_families": retained_families,
                        "dropped_families": dropped_families,
                        "retained_samples": retained_samples,
                        "dropped_samples": dropped_samples_t,
                    }
                )

    return {
        "taxonomy_health": "YELLOW" if (tax_total > 0 or model_prediction_errors > 0) else ("GREEN" if taxonomy_ready else "RED"),
        "taxonomy_mismatch_total": tax_total if taxonomy_ready else "—",
        "claim_facing_taxonomy_mismatch_total": claim_facing_tax_total if taxonomy else "—",
        "paper_facing_taxonomy_mismatch_total": claim_facing_tax_total if taxonomy else "—",
        "type_rendering_issue_count": type_issues if taxonomy_ready else "—",
        "model_prediction_error_count": model_prediction_errors if taxonomy_ready else "—",
        "family_mismatch_count": model_prediction_errors if taxonomy_ready else "—",
        "authority_gap_run_count": authority_gap_run_count if split_json_path else "—",
        "authority_gap_global_count": authority_gap_global_count if split_json_path else "—",
        "min_samples_per_family": min_support,
        "families_before_threshold": families_before,
        "families_retained": retained,
        "families_dropped": dropped,
        "samples_dropped_estimate": dropped_samples,
        "families_just_below_threshold": near_threshold,
        "taxonomy_authority_split_path": str(split_md_path.resolve()) if split_md_path else "missing",
        "taxonomy_authority_split_json_path": str(split_json_path.resolve()) if split_json_path else "missing",
        "taxonomy_authority_split_origin": str(split_summary.get("split_md_origin", "") or "missing"),
        "taxonomy_authority_split_json_origin": str(split_summary.get("split_json_origin", "") or "missing"),
        "taxonomy_consistency_summary_path": str(taxonomy_path.resolve()) if taxonomy_path else "missing",
        "taxonomy_consistency_summary_origin": oh.classify_artifact_origin(taxonomy_path, rdiag),
        "taxonomy_target_surfaces_path": str(target_surfaces_path.resolve()) if target_surfaces_path else "missing",
        "taxonomy_target_surfaces_origin": oh.classify_artifact_origin(target_surfaces_path, rdiag),
        "family_label_taxonomy_audit_path": str(fam_audit_path.resolve()) if fam_audit_path else "missing",
        "support_threshold_preview_path": str(support_preview_path.resolve()) if support_preview_path else "missing",
        "preferred_family_target": str(label_strategy.get("preferred_family_target", "") or "—"),
        "preferred_family_reporting_surface": str(label_strategy.get("preferred_family_reporting_surface", "") or "—"),
        "preferred_type_target": str(label_strategy.get("preferred_type_target", "") or "—"),
        "preferred_hierarchical_target": str(label_strategy.get("preferred_hierarchical_target", "") or "—"),
        "avoid_for_primary_claims": list(label_strategy.get("avoid_for_primary_claims", []))
        if isinstance(label_strategy.get("avoid_for_primary_claims"), list)
        else [],
        "alignment_interpretation": str(label_strategy.get("alignment_interpretation", "") or ""),
        "threshold_sensitivity": threshold_sensitivity,
    }


def build_permission_coverage_tuning_snapshot(*, run_id: str, output_root: Path, first_existing_path_fn) -> dict[str, object]:
    """Build compact permission-coverage tuning snapshot from existing artifacts."""
    rdiag = run_locator.resolve_run_root_for_run_id(run_id, output_base=output_root) / "diagnostics"
    gdiag = output_root / "diagnostics"
    q2_path = first_existing_path_fn([rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"])
    q2 = read_json_dict(q2_path) if q2_path else {}
    perm_cov_path = first_existing_path_fn([rdiag / "permission_coverage_summary.csv", gdiag / "permission_coverage_summary.csv"])
    feature_group_path = first_existing_path_fn([rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"])
    ablation_path = first_existing_path_fn([rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"])

    weak_types = weak_families = 0
    if perm_cov_path is not None:
        df = pd.read_csv(perm_cov_path)
        if not df.empty:
            cols = {str(c).lower(): c for c in df.columns}
            bucket_col = cols.get("group_kind") or cols.get("scope") or cols.get("bucket_type")
            cov_col = cols.get("coverage_pct") or cols.get("coverage")
            if bucket_col and cov_col:
                work = df.copy()
                work[cov_col] = pd.to_numeric(work[cov_col], errors="coerce").fillna(0.0)
                b = work[bucket_col].astype(str).str.lower()
                weak_types = int(((b.str.contains("type")) & (work[cov_col] <= 1.0)).sum())
                weak_families = int(((b.str.contains("famil")) & (work[cov_col] <= 1.0)).sum())

    permission_feature_survival = "n/a"
    if feature_group_path is not None:
        fg = pd.read_csv(feature_group_path)
        if not fg.empty:
            text = fg.to_string(index=False).lower()
            permission_feature_survival = "present" if "permission" in text else "not_explicit"

    permission_only_ablation = "n/a"
    if ablation_path is not None:
        ab = pd.read_csv(ablation_path)
        if not ab.empty:
            txt = ab.to_string(index=False).lower()
            permission_only_ablation = "present" if "permission" in txt else "not_found"

    return {
        "global_permission_signal_pct": q2.get("permission_signal_pct", "—") if q2 else "—",
        "global_permission_signal_n": q2.get("permission_signal_n", "—") if q2 else "—",
        "weak_or_zero_coverage_types": weak_types,
        "weak_or_zero_coverage_families": weak_families,
        "permission_feature_survival": permission_feature_survival,
        "permission_only_ablation_signal": permission_only_ablation,
    }


__all__ = [
    "build_permission_coverage_tuning_snapshot",
    "build_taxonomy_support_tuning_snapshot",
    "launch_taxonomy_support_tuning_compact_menu",
]
