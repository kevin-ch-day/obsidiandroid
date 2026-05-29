"""Run summary, hygiene finalization, and contract snapshot writers for the manifest stage.

Extracted from ``obsidiandroid.pipeline.stage_manifest`` to keep the stage orchestrator smaller.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.publication_readiness import (
    evaluate_publication_ready_status,
    publication_ready_alias_payload,
)
from obsidiandroid.common.cv_fold_config import (
    coerce_stratified_cv_folds_config,
    safe_int_config_value,
)
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode

_AUTHORITY_VIEW_SQL_PATH = Path("database/sql/view_android_sample_family_type_authority.sql")


def _safe_config_int(attr: str, *, default: int) -> int:
    """Parse ``app_config`` integer settings without ``int(None)`` crashes."""
    return safe_int_config_value(getattr(app_config, attr, default), default=default)


def emit_run_authority_coverage_bundle(
    *,
    diagnostics_dir: Path,
    run_id: str,
    artifact_list: list[str],
    manifest_context: dict[str, Any],
) -> dict[str, Any]:
    """Generate run-scoped authority coverage artifacts or a stub when the live view is unavailable."""
    from obsidiandroid.diagnostics.family_type_authority_coverage import (
        LIVE_VIEW_MISSING_WARNING,
        generate_authority_coverage_artifacts,
    )

    md_path = diagnostics_dir / f"family_type_authority_coverage_{run_id}.md"
    missing_out = diagnostics_dir / f"family_type_authority_missing_candidates_{run_id}.csv"
    unknown_type_out = diagnostics_dir / f"family_type_authority_unknown_type_{run_id}.csv"
    year_type_out = diagnostics_dir / f"family_type_authority_year_type_{run_id}.csv"

    bundle = generate_authority_coverage_artifacts(
        md_path=md_path,
        missing_out=missing_out,
        unknown_type_out=unknown_type_out,
        year_type_out=year_type_out,
        require_live_view=True,
    )
    source_mode = str(bundle.get("source_mode") or "unknown")
    manifest_context["authority_coverage_artifact"] = str(md_path)
    manifest_context["authority_coverage_source_mode"] = source_mode

    if bool(bundle.get("ok", False)):
        for path_key in ("md_path", "missing_out", "unknown_type_out", "year_type_out"):
            path_obj = bundle.get(path_key)
            if path_obj:
                path_str = str(path_obj)
                if path_str not in artifact_list:
                    artifact_list.append(path_str)
        return bundle

    warning = str(bundle.get("warning") or LIVE_VIEW_MISSING_WARNING).strip() or LIVE_VIEW_MISSING_WARNING
    stub_lines = [
        "# Family/Type Authority Coverage Report",
        "",
        "- Status: `unavailable`",
        f"- Source mode: `{source_mode}`",
        f"- Warning: {warning}",
        "- Advisory only: pipeline outputs are unchanged; this report did not participate in cohort gates or training.",
        f"- Apply SQL first: `{_AUTHORITY_VIEW_SQL_PATH.as_posix()}`",
        "",
        "No authority coverage rows were materialized for this run because the live authority view was unavailable.",
    ]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(stub_lines) + "\n", encoding="utf-8")
    if str(md_path) not in artifact_list:
        artifact_list.append(str(md_path))
    return {
        "ok": False,
        "source_mode": source_mode,
        "warning": warning,
        "md_path": md_path,
    }


def write_run_summary_json(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    result_code: int,
) -> Path | None:
    """Write canonical run-summary JSON for operator history and health views."""
    try:
        run_id = str(manifest.get("run_id", manifest_context.get("run_id", "unknown")))
        profile = manifest.get("profile_params", {}) if isinstance(manifest.get("profile_params"), dict) else {}
        model_summary = manifest.get("model_summary", {}) if isinstance(manifest.get("model_summary"), dict) else {}
        configured_status = str(manifest_context.get("run_status", "") or "").strip().lower()
        failure_reason = str(
            manifest_context.get("failure_reason", "") or manifest_context.get("integrity_error", "")
        ).strip()
        if configured_status in {"complete", "partial", "failed"}:
            run_status = configured_status
        elif failure_reason or int(result_code) != 0:
            run_status = "failed"
        elif str(manifest_context.get("completed_stage", "") or "").strip().lower() not in {"", "manifest"}:
            run_status = "partial"
        else:
            run_status = "complete"

        completed_stage = str(manifest_context.get("completed_stage", "") or "").strip()
        if not completed_stage:
            completed_stage = "manifest" if run_status == "complete" else str(
                manifest_context.get("current_stage", "") or "unknown"
            ).strip()

        split_blob = manifest.get("split", {}) if isinstance(manifest.get("split"), dict) else {}
        comp_rep: dict[str, Any] = {}
        comp_path_str = str(manifest.get("paper_mode_compliance_report", "") or "").strip()
        if comp_path_str:
            try:
                comp_rep = json.loads(Path(comp_path_str).read_text(encoding="utf-8"))
            except Exception:
                comp_rep = {}
        publication_ready_status, publication_ready_reasons = evaluate_publication_ready_status(
            paper_mode=bool((manifest.get("paper_mode") or {}).get("resolved_value", False)),
            manifest=manifest,
            compliance_report=comp_rep if comp_rep else None,
        )
        if run_status != "complete":
            terminal_reason = "run_failed" if run_status == "failed" else "run_not_complete"
            if "paper_compliance_not_pass" not in publication_ready_reasons:
                publication_ready_reasons.append("paper_compliance_not_pass")
            if terminal_reason not in publication_ready_reasons:
                publication_ready_reasons.append(terminal_reason)
            publication_ready_status = "FAIL"

        feat_cols_resolved = manifest.get("feature_matrix_cols_post_prune")
        if feat_cols_resolved is None:
            feat_cols_resolved = manifest.get("feature_matrix_row_count")

        feat_rows_resolved = manifest.get("feature_matrix_rows")
        if feat_rows_resolved is None:
            feat_rows_resolved = manifest_context.get("fused_feature_rows")
        if feat_rows_resolved is not None:
            try:
                feat_rows_resolved = int(feat_rows_resolved)
            except (TypeError, ValueError):
                feat_rows_resolved = None

        payload = {
            "schema_version": "1.0",
            "run_id": run_id,
            "profile_id": str(profile.get("profile_id", "unknown")),
            "timestamp_utc": str(manifest.get("timestamp_utc", "") or manifest_context.get("timestamp_utc", "")),
            "run_status": run_status,
            "completed_stage": completed_stage,
            "failed_stage": str(manifest_context.get("failed_stage", "") or "").strip() or None,
            "failure_reason": failure_reason or None,
            "cohort_size": int(manifest.get("cohort_size", 0) or 0),
            "selected_vendor_count": manifest.get("selected_vendor_count"),
            "vendor_constrained_run_flag": bool(manifest.get("vendor_constrained_run_flag", False)),
            "pipeline_runtime_sec": manifest_context.get("pipeline_runtime_sec"),
            "top_model": str(model_summary.get("top_model", "") or "").strip() or None,
            "top_macro_f1": model_summary.get("top_macro_f1"),
            "model_summary": model_summary,
            "trained_model_count": manifest.get("trained_model_count")
            or len(list(manifest.get("trained_models") or [])),
            "main_training_row_authority": manifest.get("main_training_row_authority"),
            "feature_matrix_cols_post_prune": feat_cols_resolved,
            "feature_matrix_rows": feat_rows_resolved,
            # Legacy key retained for older tooling; this is a *column* count (post-prune).
            "feature_matrix_row_count": feat_cols_resolved,
            "train_sample_count": split_blob.get("train_sample_count"),
            "test_sample_count": split_blob.get("test_sample_count"),
            "ablation_multi_label_targets": manifest.get("ablation_multi_label_targets"),
            "manifest_path": str(run_root / "run_manifest.json"),
            "run_root": str(run_root),
            "paper_mode": bool((manifest.get("paper_mode") or {}).get("resolved_value", False)),
            "evidence_mode": coalesce_manifest_publication_mode(manifest),
            "result_code": int(result_code),
            "lifecycle_started_at_utc": manifest_context.get("lifecycle_started_at_utc"),
            "lifecycle_state": manifest_context.get("lifecycle_state"),
            "lifecycle_finished_at_utc": manifest_context.get("lifecycle_finished_at_utc"),
        }
        payload.update(
            publication_ready_alias_payload(
                publication_ready_status,
                publication_ready_reasons,
            )
        )

        run_summary_path = run_root / "run_summary.json"
        run_summary_run_path = diagnostics_dir / f"run_summary_{run_id}.json"
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        run_summary_path.write_text(encoded, encoding="utf-8")
        if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
            run_summary_run_path.write_text(encoded, encoding="utf-8")
        elif run_summary_run_path.exists():
            try:
                run_summary_run_path.unlink()
            except OSError:
                pass
        if oh.run_diagnostics_should_omit_latest_duplicate() and oh.path_is_under_output_runs(diagnostics_dir):
            oh.write_global_latest_text(filename="run_summary.latest.json", text=encoded)
        else:
            run_summary_latest_path = diagnostics_dir / "run_summary.latest.json"
            run_summary_latest_path.write_text(encoded, encoding="utf-8")
        return run_summary_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write canonical run summary: {exc}")
        return None


def merge_lifecycle_fields_into_run_summaries(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
) -> None:
    """Patch lifecycle keys into ``run_summary`` JSON sinks after terminal lifecycle write."""
    keys = ("lifecycle_state", "lifecycle_started_at_utc", "lifecycle_finished_at_utc")
    updates = {k: manifest_context[k] for k in keys if k in manifest_context}
    if not updates:
        return
    paths: list[Path] = [
        run_root / "run_summary.json",
        diagnostics_dir / f"run_summary_{run_id}.json",
    ]
    if oh.run_diagnostics_should_omit_latest_duplicate() and oh.path_is_under_output_runs(diagnostics_dir):
        paths.append(oh.global_diagnostics_root() / "run_summary.latest.json")
    else:
        paths.append(diagnostics_dir / "run_summary.latest.json")

    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        data.update(updates)
        try:
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            continue


def finalize_output_hygiene_bundle(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    artifact_list: list[str],
    compliance_report: dict[str, Any] | None,
    paper_mode: bool,
    evidence_mode: bool,
    result_code: int = 0,
) -> None:
    """Artifact inventory, virtual layout, run evidence index, and terminal summary."""
    try:
        from obsidiandroid.diagnostics import output_inventory
        from obsidiandroid.diagnostics.diagnostic_provenance import record_diagnostic_provenance
        from obsidiandroid.observability.pipeline_observability.finalize import finalize_pipeline_observability
        from obsidiandroid.observability.pipeline_observability.run_health import print_unified_run_health
        from obsidiandroid.pipeline.manifest.stage_manifest_artifacts import write_run_artifact_index

        emit_run_authority_coverage_bundle(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            artifact_list=artifact_list,
            manifest_context=manifest_context,
        )

        verbose_run_artifacts = bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))

        layout_path = output_inventory.write_virtual_layout(run_root) if verbose_run_artifacts else None
        inv_paths: list[Path] = []
        summary = {}
        if verbose_run_artifacts:
            inv_paths, summary = output_inventory.write_artifact_inventory_bundle(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                run_id=run_id,
                manifest_paths=list(artifact_list),
                extra_summary={
                    "profile_id": str(profile.get("profile_id", "")),
                    "evidence_mode": evidence_mode,
                    "paper_mode": paper_mode,
                },
            )

        mf_start = manifest_context.get("_manifest_finalize_perf_start")
        try:
            if isinstance(mf_start, (float, int)):
                manifest_context["_manifest_finalize_duration_sec"] = max(
                    0.0, float(time.perf_counter()) - float(mf_start),
                )
        except Exception:
            manifest_context["_manifest_finalize_duration_sec"] = 0.0

        obs_path = finalize_pipeline_observability(
            diagnostics_dir=diagnostics_dir,
            run_root=run_root,
            manifest_context=manifest_context,
            manifest=manifest,
            artifact_list=artifact_list,
            compliance_report=compliance_report,
            paper_mode=bool(paper_mode),
            evidence_mode=bool(evidence_mode),
            result_code=int(result_code),
            profile_id=str(profile.get("profile_id", "unknown")),
        )

        paper_safe_status, reasons = evaluate_publication_ready_status(
            paper_mode=paper_mode,
            manifest=manifest,
            compliance_report=compliance_report,
        )
        cohort_size = int(manifest.get("cohort_size", 0) or 0)
        trained_models = list(manifest.get("trained_models", []) or [])
        evidence_path = output_inventory.write_run_evidence_index_md(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile_id=str(profile.get("profile_id", "unknown")),
            paper_mode=bool(paper_mode),
            cohort_size=cohort_size,
            manifest=manifest,
            manifest_context=manifest_context,
            trained_models=trained_models,
            paper_safe_status=paper_safe_status,
            paper_safe_reasons=reasons,
        )
        pipeline_artifact_paths = list(artifact_list)
        pipeline_artifact_paths.extend(str(p) for p in inv_paths if p)
        if layout_path:
            pipeline_artifact_paths.append(str(layout_path))
        if evidence_path:
            pipeline_artifact_paths.append(str(evidence_path))
        provenance_path = None
        if verbose_run_artifacts:
            provenance_path = record_diagnostic_provenance(
                diagnostics_dir=diagnostics_dir,
                run_root=run_root,
                run_id=run_id,
                entry_id=f"pipeline::{run_id}",
                generated_during_pipeline=True,
                source_command="run_pipeline",
                source_run_id=run_id,
                artifact_paths=pipeline_artifact_paths,
            )
        cohort_contract = (
            manifest.get("cohort_contract")
            if isinstance(manifest.get("cohort_contract"), dict)
            else manifest_context.get("paper_cohort_contract")
        )
        cohort_locked = bool((cohort_contract or {}).get("paper_locked", False))
        science_index_path = output_inventory.write_run_science_index_md(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile_id=str(profile.get("profile_id", "unknown")),
            evidence_mode=bool(evidence_mode),
            cohort_locked=cohort_locked,
            publication_ready_status=paper_safe_status,
        )
        for p in inv_paths:
            if p and p not in artifact_list:
                artifact_list.append(p)
        if layout_path and str(layout_path) not in artifact_list:
            artifact_list.append(str(layout_path))
        if evidence_path and str(evidence_path) not in artifact_list:
            artifact_list.append(str(evidence_path))
        if provenance_path and str(provenance_path) not in artifact_list:
            artifact_list.append(str(provenance_path))
        if science_index_path and str(science_index_path) not in artifact_list:
            artifact_list.append(str(science_index_path))
        refreshed_index_path = None
        if verbose_run_artifacts:
            refreshed_index_path = write_run_artifact_index(
                run_id=run_id,
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
            )
        if refreshed_index_path and str(refreshed_index_path) not in artifact_list:
            artifact_list.append(str(refreshed_index_path))
        if verbose_run_artifacts:
            inv_paths, summary = output_inventory.write_artifact_inventory_bundle(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                run_id=run_id,
                manifest_paths=list(artifact_list),
                extra_summary={
                    "profile_id": str(profile.get("profile_id", "")),
                    "evidence_mode": evidence_mode,
                    "paper_mode": paper_mode,
                },
            )
            for p in inv_paths:
                if p and p not in artifact_list:
                    artifact_list.append(p)

        observability_json_path = (
            obs_path
            if obs_path is not None
            else diagnostics_dir / "run_observability_summary.json"
        )
        if verbose_run_artifacts:
            output_inventory.print_output_hygiene_terminal_summary(
                run_root=run_root,
                summary=summary,
                evidence_index_path=evidence_path,
                paper_safe_status=paper_safe_status,
            )
        print_unified_run_health(
            inventory_summary=summary,
            observability_json_path=observability_json_path,
            evidence_index_path=evidence_path,
            run_root=run_root,
        )
    except Exception as exc:
        du.print_warning(f"[OUTPUT] Hygiene bundle skipped: {exc}")


def write_run_summary_onepager(
    *,
    run_id: str,
    diagnostics_dir: Path,
    profile: dict[str, Any],
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    compliance_path: Path,
) -> Path | None:
    """Write a concise run-summary markdown artifact for quick reviewer/operator use."""
    try:
        paper_mode_data = manifest_context.get("paper_mode", {})
        model_summary = manifest_context.get("model_summary", {})
        stage_timings = manifest_context.get("stage_timings_sec", {})
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        duplicate_meta = manifest.get("duplicate_sha", {}) if isinstance(manifest, dict) else {}

        lines = [
            f"# Run Summary One-Pager ({run_id})",
            "",
            "## Context",
            f"- run_id: `{run_id}`",
            f"- profile_id: `{profile.get('profile_id', 'unknown')}`",
            f"- publication_ready_mode: `{bool(paper_mode_data.get('resolved_value', False))}` (source=`{paper_mode_data.get('source', 'unknown')}`)",
            f"- cohort_size: `{manifest.get('cohort_size', 0)}`",
            f"- selected_vendor_count: `{manifest.get('selected_vendor_count', 0)}`",
            "",
            "## Governance",
            f"- split_hash: `{split_meta.get('split_hash', '')}`",
            f"- split_audit: `{split_meta.get('split_audit_path', '')}`",
            f"- duplicate_sha_groups: `{duplicate_meta.get('duplicate_sha_groups', 0)}`",
            f"- invalid_sha_count: `{duplicate_meta.get('invalid_sha_count', 0)}`",
            f"- vendor_set_hash: `{manifest.get('vendor_set_hash', '')}`",
            f"- compliance_report: `{compliance_path}`",
            "",
            "## Model Snapshot",
        ]
        if isinstance(model_summary, dict) and model_summary:
            lines.extend(
                [
                    f"- top_model: `{model_summary.get('top_model', '')}`",
                    f"- top_macro_f1: `{model_summary.get('top_macro_f1', '')}`",
                ]
            )
            model_rows = model_summary.get("model_rows", [])
            if isinstance(model_rows, list) and model_rows:
                lines.append("")
                lines.append("| model | macro_f1 | weighted_f1 | accuracy |")
                lines.append("|---|---:|---:|---:|")
                for row in model_rows:
                    lines.append(
                        f"| {row.get('model', '')} | {row.get('macro_f1', '')} | "
                        f"{row.get('weighted_f1', '')} | {row.get('accuracy', '')} |"
                    )
        else:
            lines.append("- model summary not available (run stopped before training).")

        if isinstance(stage_timings, dict) and stage_timings:
            lines.extend(["", "## Stage Timings (sec)"])
            for stage_name, sec in stage_timings.items():
                lines.append(f"- {stage_name}: `{sec}`")

        onepager_path = diagnostics_dir / f"run_summary_onepager_{run_id}.md"
        payload = "\n".join(lines).strip() + "\n"
        onepager_path.write_text(payload, encoding="utf-8")
        oh.mirror_utf8_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=onepager_path.name,
            text=payload,
            global_latest_name="run_summary_onepager.latest.md",
        )
        return onepager_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write run one-pager: {exc}")
        return None


def write_experiment_contract_snapshot(
    *,
    run_id: str,
    diagnostics_dir: Path,
    profile: dict[str, Any],
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
) -> Path | None:
    """Write one-file snapshot of experiment contract decisions for reproducibility."""
    try:
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        paper_mode_data = manifest_context.get("paper_mode", {})
        profile_gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
        profile_id = str(profile.get("profile_id", "unknown"))
        split_hash = str(split_meta.get("split_hash", ""))
        model_config_hash = str(manifest_context.get("model_config_hash", ""))
        series_id = compute_experiment_series_id(profile_id=profile_id, split_hash=split_hash)
        previous_series_contract = load_previous_series_contract(
            diagnostics_dir=diagnostics_dir,
            series_id=series_id,
            current_run_id=run_id,
        )
        previous_run_id = str(previous_series_contract.get("run_id", "")) if previous_series_contract else ""
        previous_model_config_hash = (
            str((previous_series_contract.get("model_contract") or {}).get("model_config_hash", ""))
            if previous_series_contract
            else ""
        )
        no_retuning_consistent = bool(
            not previous_model_config_hash
            or not model_config_hash
            or previous_model_config_hash == model_config_hash
        )

        cohort_contract = dict(manifest_context.get("paper_cohort_contract", {}) or {})

        contract = {
            "schema_version": "1.0",
            "run_id": run_id,
            "profile_id": profile_id,
            "experiment_series": {
                "series_id": series_id,
                "series_key": {
                    "profile_id": profile_id,
                    "split_hash": split_hash,
                },
                "previous_run_id_in_series": previous_run_id or None,
                "previous_model_config_hash_in_series": previous_model_config_hash or None,
                "model_config_hash_stable_with_series": bool(no_retuning_consistent),
            },
            "paper_mode": {
                "enabled": bool(paper_mode_data.get("resolved_value", False)),
                "source": str(paper_mode_data.get("source", "unknown")),
            },
            "target_task": {
                "training_label_field": "family_id",
                "display_label_field": "family_canonical",
                "label_selection_policy": "family_id_first",
                "label_field_legacy": "family_canonical",
                "task_type": "multiclass_classification",
                "primary_metric": "macro_f1_mean_cv5",
            },
            "label_authority_reporting": {
                "training_label_field": str(
                    getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "") or ""
                ).strip(),
                "display_label_field": "family_canonical",
                "label_selection_policy": "family_id_first",
                "active_training_classes": getattr(
                    app_config,
                    "RUNTIME_TRAINING_LABEL_CLASS_COUNT",
                    None,
                ),
                "cohort_family_count": _safe_config_int("RUNTIME_COHORT_FAMILY_COUNT", default=0),
            },
            "split_contract": {
                "split_hash": split_hash,
                "split_seed": split_meta.get("split_seed"),
                "split_algorithm": split_meta.get("split_algorithm"),
                "split_algorithm_version": split_meta.get("split_algorithm_version"),
                "temporal_holdout": split_meta.get("temporal_split_summary") or {},
                "cv_protocol": {
                    "stratified_kfold_splits": coerce_stratified_cv_folds_config(
                        getattr(app_config, "CV_FOLDS", 5)
                    ),
                    "repeats": max(1, _safe_config_int("CV_REPEATS", default=1)),
                    "fixed_seed": _safe_config_int("RANDOM_STATE", default=42),
                },
            },
            "perturbation_contract": {
                "consensus_min_malicious_detections": profile_gates.get("min_malicious_detections"),
                "family_cap": profile_gates.get("family_cap"),
                "family_cap_seed": profile_gates.get("family_cap_seed"),
                "type_cap": profile_gates.get("type_cap"),
                "type_cap_seed": profile_gates.get("type_cap_seed"),
                "unknown_type_excluded": bool(
                    profile_gates.get(
                        "exclude_unknown_type_slug",
                        bool(getattr(app_config, "PAPER_MODE_ENABLED", False)),
                    )
                ),
            },
            "feature_contract": {
                "sample_level_only": True,
                "label_derived_features_forbidden": True,
                "family_aggregate_features_forbidden": True,
                "post_split_stats_forbidden": True,
                "temporal_features_forbidden": True,
            },
            "model_contract": {
                "no_model_retuning_across_perturbations": bool(no_retuning_consistent),
                "model_config_hash": model_config_hash,
            },
            "paper_cohort_contract": cohort_contract,
            "cohort_contract": cohort_contract,
            "material_change_rule": {
                "primary_abs_delta_macro_f1_gt": float(
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_ABS_DELTA_MACRO_F1", 0.02)
                ),
                "secondary_relative_drop_pct_gt": float(
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_REL_DROP_PCT", 5.0)
                ),
                "ci_overrides_threshold": False,
            },
        }
        out_path = diagnostics_dir / f"experiment_contract_snapshot_{run_id}.json"
        payload = json.dumps(contract, indent=2, sort_keys=True)
        out_path.write_text(payload, encoding="utf-8")
        oh.mirror_json_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=out_path.name,
            payload=contract,
            global_latest_name="experiment_contract_snapshot.latest.json",
        )
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write experiment contract snapshot: {exc}")
        return None


def write_evaluation_contract_json(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
) -> Path | None:
    """Stitch run-scoped pointers/hashes for headline evaluation evidence."""
    try:
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        label_block = {}
        if isinstance(manifest_context, dict):
            maybe = manifest_context.get("label_authority")
            if isinstance(maybe, dict):
                label_block = maybe
        predictions_path = diagnostics_dir / f"headline_test_predictions_{run_id}.csv"
        errors_path = diagnostics_dir / f"headline_test_errors_{run_id}.csv"
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": str(run_id),
            "split_contract": {
                "split_hash": str(split_meta.get("split_hash", "") or ""),
                "split_audit_path": str(split_meta.get("split_audit_path", "") or ""),
                "split_key_hash": str(split_meta.get("split_key_hash", "") or ""),
                "train_sample_hash": str(split_meta.get("train_sample_hash", "") or ""),
                "test_sample_hash": str(split_meta.get("test_sample_hash", "") or ""),
            },
            "feature_contract": {
                "headline_feature_column_hash": str(
                    getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
                ),
                "headline_feature_contract_path": str(
                    getattr(app_config, "RUNTIME_HEADLINE_FEATURE_CONTRACT_PATH", "") or ""
                ),
            },
            "label_authority": label_block,
            "headline_test_tables": {
                "predictions_csv": str(predictions_path),
                "predictions_csv_exists": bool(predictions_path.is_file()),
                "errors_csv": str(errors_path),
                "errors_csv_exists": bool(errors_path.is_file()),
            },
        }
        out_path = diagnostics_dir / f"evaluation_contract_{run_id}.json"
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        out_path.write_text(text, encoding="utf-8")
        oh.mirror_json_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=out_path.name,
            payload=payload,
            global_latest_name="evaluation_contract.latest.json",
        )
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] evaluation_contract export skipped: {exc}")
        return None


def write_taxonomy_authority_recommendation_md(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
) -> Path | None:
    """Markdown analysis-only note for taxonomy / type_slug paper safety (no policy enforcement)."""
    try:
        mismatch_path = ""
        if isinstance(manifest_context, dict):
            mismatch_path = str(manifest_context.get("taxonomy_mismatch_csv", "") or "").strip()
        lines = [
            "# Taxonomy authority recommendation (analysis-only)",
            "",
            f"Run ID: `{run_id}`",
            "",
            "## Policy",
            "",
            "- Taxonomy mapping logic is unchanged in this pass; this file is reporting only.",
            "- **type_slug** prevalence or type-level paper claims are **caution / not paper-safe** until a single authoritative type source is declared and reconciled.",
            "",
        ]
        if not mismatch_path or not Path(mismatch_path).is_file():
            lines.append("_No taxonomy mismatch export path recorded on this run._\n")
        else:
            df = pd.read_csv(mismatch_path)
            lines.append(f"Source: `{mismatch_path}` — {len(df)} row(s)\n")
            if not df.empty and "mismatch_reason" in df.columns:
                lines.append("## Mismatch reasons (top counts)\n")
                counts = df["mismatch_reason"].fillna("unknown").astype(str).value_counts().head(15)
                for reason, cnt in counts.items():
                    lines.append(f"- {reason}: {int(cnt)}")
                lines.append("")
            if not df.empty and {"type_slug", "type_slug_expected"} <= set(df.columns):
                lines.append("## Top mismatch pairs (observed type_slug, expected type_slug)\n")
                lines.append("| observed | expected | count |")
                lines.append("| --- | --- | --- |")
                pairs: dict[tuple[str, str], int] = {}
                for ts, te in zip(
                    df["type_slug"].fillna("").astype(str).str.strip().tolist(),
                    df["type_slug_expected"].fillna("").astype(str).str.strip().tolist(),
                ):
                    pairs[(ts, te)] = pairs.get((ts, te), 0) + 1
                sorted_pairs = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:25]
                for (ts, te), cnt in sorted_pairs:
                    lines.append(f"| `{ts}` | `{te}` | {int(cnt)} |")
                lines.append("")
            if not df.empty:
                lines.append("## Paper-facing recommendation\n")
                lines.append("")
                lines.append("- **Treat type_slug-derived quantitative claims as paper-safe:** no (pending governance).")
                lines.append("- **Suggested authority:** designate one authoritative type source for reporting; reconcile `type_mapping_mismatch` rows explicitly.\n")
        body = "\n".join(lines).strip() + "\n"
        out_path = diagnostics_dir / f"taxonomy_authority_recommendation_{run_id}.md"
        out_path.write_text(body, encoding="utf-8")
        oh.mirror_utf8_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=out_path.name,
            text=body,
            global_latest_name="taxonomy_authority_recommendation.latest.md",
        )
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] taxonomy_authority_recommendation skipped: {exc}")
        return None


def compute_experiment_series_id(*, profile_id: str, split_hash: str) -> str:
    """Build a stable series identifier for cross-run comparability checks."""
    payload = {"profile_id": str(profile_id), "split_hash": str(split_hash)}
    return hash_payload(payload)[:12]


def load_previous_series_contract(
    *,
    diagnostics_dir: Path,
    series_id: str,
    current_run_id: str,
) -> dict[str, Any]:
    """Load latest contract snapshot when it belongs to the same series."""
    latest_path = diagnostics_dir / "experiment_contract_snapshot.latest.json"
    if not latest_path.exists():
        latest_path = oh.global_diagnostics_root() / "experiment_contract_snapshot.latest.json"
    if not latest_path.exists():
        return {}
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    latest_run_id = str(payload.get("run_id", ""))
    if latest_run_id == current_run_id:
        return {}
    payload_series = str((payload.get("experiment_series") or {}).get("series_id", ""))
    if payload_series != series_id:
        return {}
    return payload
