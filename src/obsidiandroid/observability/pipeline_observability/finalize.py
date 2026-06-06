"""Regenerate rollup artifacts after manifest/output hygiene completes.

``run_observability_summary.json`` uses ``cohort_sql_scope_row_count`` /
``cohort_prepared_row_count`` as the preferred cohort population fields; legacy keys are
still emitted for older dashboards (see ``cohort_vocabulary``).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.publication_readiness import (
    evaluate_publication_ready_status,
    publication_ready_payload,
)
from obsidiandroid.common.scientific_adequacy import classify_scientific_adequacy

from obsidiandroid.diagnostics.cohort_vocabulary import (
    KEY_COHORT_PREPARED_ROW_COUNT,
    KEY_COHORT_SQL_SCOPE_ROW_COUNT,
    read_prepared_cohort_row_count,
    read_sql_scope_row_count,
)
from obsidiandroid.diagnostics.research_validity.cohort_funnel import (
    build_cohort_funnel_plain,
    describe_trainable_pool_funnel_segment,
)
from obsidiandroid.governance.evidence_mode_resolver import (
    coalesce_manifest_evidence_mode,
    coalesce_manifest_publication_mode,
)
from obsidiandroid.pipeline.manifest.runtime_support import (
    derive_aggregate_pipeline_verdict,
    derive_terminal_run_status,
)
from obsidiandroid.diagnostics.v3_dl_handoff import build_v3_dl_handoff_observability_block as _build_v3_dl_handoff_observability_block
from obsidiandroid.observability.pipeline_observability.logging_audit import write_logging_audit_artifacts
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession


_RUNNER_CHAIN = [
    "preflight",
    "samples",
    "av_pipeline",
    "vendor_metadata",
    "engine_weights",
    "feature_matrix",
    "alignment",
    "training",
    "ablation",
    "permission_trends",
    "label_resolution",
]

AUTHORITATIVE_SUMMARY_FILENAME = "run_observability_summary.json"


def _claim_audit_alias_name(*, profile_id: str, evidence_mode: bool, paper_mode: bool) -> str:
    """Return the profile-appropriate claim audit alias name."""
    if bool(evidence_mode or paper_mode):
        return "publication_claim_audit.md"
    if str(profile_id or "").strip() in {
        "android_malware_major_families",
        "android_malware_type_taxonomy",
    }:
        return "benchmark_claim_audit.md"
    return "research_claim_audit.md"


def _claim_surface_label(*, profile_id: str, evidence_mode: bool, paper_mode: bool) -> str:
    """Return a human-readable claim surface label for summaries."""
    profile = str(profile_id or "").strip()
    if bool(evidence_mode or paper_mode):
        return "Locked publication cohort"
    if profile == "android_malware_all_current":
        return "Current-corpus diagnostic surface"
    if profile == "android_malware_major_families":
        return "Support-gated benchmark cohort"
    if profile == "android_malware_expanded_families":
        return "Expanded-family exploratory cohort"
    if profile == "android_malware_type_taxonomy":
        return "Type taxonomy benchmark"
    return "Benchmark research surface"


def _coerce_int(v: Any) -> int | None:
    """Best-effort int for dashboard fields."""
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _format_top_count_pairs(counts: dict[str, Any], *, limit: int = 5) -> str:
    """Render compact ``name=count`` pairs for observability summaries."""
    if not isinstance(counts, dict) or not counts:
        return ""
    rows: list[tuple[str, int]] = []
    for key, value in counts.items():
        try:
            rows.append((str(key), int(value)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: (-item[1], item[0].lower()))
    shown = [f"{name}={count}" for name, count in rows[: max(1, int(limit))]]
    if len(rows) > len(shown):
        shown.append("…")
    return ", ".join(shown)


def _read_label_strategy_blob(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    label_strategy = payload.get("label_strategy") if isinstance(payload, dict) else {}
    return label_strategy if isinstance(label_strategy, dict) else {}


def _read_taxonomy_target_surface_blob(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Load taxonomy target-surface summary when present."""
    path = diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _top_artifacts_to_open(
    run_root: Path | None,
    diagnostics_dir: Path,
    run_id: str,
    *,
    verbose_run_artifacts: bool,
    research_validity_enabled: bool,
    paper_mode: bool,
    profile_id: str,
    evidence_mode: bool,
) -> list[str]:
    """Ordered open-first list constrained to artifacts that actually exist."""
    rr = run_root if run_root is not None else diagnostics_dir
    authority_md = diagnostics_dir / f"family_type_authority_coverage_{run_id}.md"
    taxonomy_split_md = diagnostics_dir / f"taxonomy_authority_split_{run_id}.md"
    ordered: list[Path] = [
        diagnostics_dir / f"v3_label_contract_{run_id}.md",
        diagnostics_dir / f"permission_pattern_contract_{run_id}.md",
        taxonomy_split_md,
        rr / "run_evidence_index.md",
        diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME,
        diagnostics_dir / f"v3_label_contract_{run_id}.json",
        diagnostics_dir / f"permission_pattern_contract_{run_id}.json",
        diagnostics_dir / f"ml_run_manifest_{run_id}.json",
        diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv",
        diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json",
        diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json",
        authority_md,
        diagnostics_dir / "pipeline_stage_summary.md",
        diagnostics_dir / "partial_failures.md",
    ]
    if paper_mode:
        ordered.append(diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json")
    if research_validity_enabled:
        claim_audit_alias = _claim_audit_alias_name(
            profile_id=profile_id,
            evidence_mode=bool(evidence_mode),
            paper_mode=bool(paper_mode),
        )
        ordered.extend(
            [
                diagnostics_dir / claim_audit_alias,
                diagnostics_dir / "publication_claim_audit.md",
                diagnostics_dir / "benchmark_claim_audit.md",
                diagnostics_dir / "research_claim_audit.md",
                diagnostics_dir / "paper_claim_audit.md",
                diagnostics_dir / "cohort_funnel.md",
                diagnostics_dir / "recommended_findings.md",
                diagnostics_dir / "figure_validity_audit.md",
                diagnostics_dir / "hostile_audit_partial_errors.txt",
            ]
        )
    if verbose_run_artifacts:
        ordered.append(diagnostics_dir / "logging_audit.md")
    return [str(p) for p in ordered if p.exists()][:16]


_STOP_IX = {
    "preflight": 0,
    "samples": 1,
    "av_pipeline": 2,
    "vendor_metadata": 3,
    "engine_weights": 4,
    "feature_matrix": 5,
    "alignment": 6,
    "training": 7,
    "ablation": 8,
    "permission_trends": 9,
    "label_resolution": 10,
    "full": len(_RUNNER_CHAIN) - 1,
}


def finalize_pipeline_observability(
    *,
    diagnostics_dir: Path,
    run_root: Path | None,
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    artifact_list: list[str],
    compliance_report: dict[str, Any] | None,
    paper_mode: bool,
    evidence_mode: bool,
    result_code: int,
    profile_id: str,
) -> Path | None:
    """Emit skipped-stage rows, status JSON, partial_failures.md, pipeline_stage_summary.md, logging audit."""

    if manifest_context.get("_observability_finalized_once"):
        return diagnostic_status_path_fallback(diagnostics_dir)
    diagnostics_dir = Path(diagnostics_dir)
    caller_evidence_mode = bool(evidence_mode)
    caller_paper_mode = bool(paper_mode)
    evidence_mode = coalesce_manifest_evidence_mode(
        manifest_context.get("evidence_mode")
        if isinstance(manifest_context, dict)
        else None
    )
    if not evidence_mode and isinstance(manifest, dict):
        evidence_mode = coalesce_manifest_publication_mode(manifest)
    if not evidence_mode:
        evidence_mode = caller_evidence_mode
    paper_mode = coalesce_manifest_evidence_mode(
        manifest_context.get("paper_mode")
        if isinstance(manifest_context, dict)
        else None
    )
    if not paper_mode:
        paper_mode = evidence_mode or caller_paper_mode
    verbose_run_artifacts = bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))
    resolved_run_root = Path(run_root).resolve() if run_root is not None else None
    run_id = str(manifest_context.get("run_id", manifest.get("run_id", "unknown")))
    obs = manifest_context.get("pipeline_observability")
    obs_session = obs if isinstance(obs, PipelineObservabilitySession) else None

    stop_after = str(manifest_context.get("stop_after", "full")).strip().lower()
    stop_ix = _STOP_IX.get(stop_after)
    if stop_ix is None:
        stop_ix = len(_RUNNER_CHAIN) - 1
    if stop_ix < 0:
        stop_ix = 0

    run_status_raw = derive_terminal_run_status(manifest_context, result_code=int(result_code))
    completed_stage = str(
        manifest_context.get("completed_stage", "") or manifest.get("completed_stage", "")
    ).strip()
    if not completed_stage:
        completed_stage = "manifest" if run_status_raw == "complete" else "unknown"

    # --- Synthetic SKIPPED runner stages ---
    completed = obs_session.completed_stages() if obs_session else set()
    if obs_session:
        skip_reason = "stop_before_stage"
        for ix, st in enumerate(_RUNNER_CHAIN):
            if ix <= stop_ix:
                continue
            if st in completed:
                continue
            extras = {"skip_reason": skip_reason}
            obs_session.emit_stage_completion(
                st,
                status="SKIPPED",
                duration_sec=0.0,
                major_warnings="Stage not executed (requested stop_before or cutoff).",
                next_stage_allowed=True,
                extras=extras,
            )

    # --- Research validity / hostile (manifest-phase) ---
    rv_err = str(manifest_context.get("research_validity_bundle_error", "") or "").strip()
    rv_skip_reason = str(manifest_context.get("_research_bundle_skipped_reason", "") or "").strip()
    hostile_skip_reason = str(manifest_context.get("_hostile_bundle_skipped_reason", "") or "").strip()
    hostile_err_path = diagnostics_dir / "hostile_audit_partial_errors.txt"
    hostile_failed = hostile_err_path.exists() and hostile_err_path.stat().st_size > 0

    rv_status = "PASS"
    if rv_skip_reason:
        rv_status = "SKIPPED"
    elif rv_err:
        rv_status = "FAIL"
        if obs_session:
            obs_session.record_partial_failure(stage="research_validity", error=rv_err, recoverable=True)

    hostile_status = "PASS"
    if hostile_skip_reason:
        hostile_status = "SKIPPED"
    elif hostile_failed:
        hostile_status = "PASS_WITH_WARNINGS"
        summary_txt = hostile_err_path.read_text(encoding="utf-8")[:1200]
        manifest_context["_hostile_audit_warning_blob"] = summary_txt
        if obs_session:
            obs_session.record_partial_failure(
                stage="hostile_audit",
                error=f"partial steps logged in {hostile_err_path}",
                recoverable=True,
            )

    rv_status = _adjust_bundle_terminal_status(
        rv_status,
        run_status_raw=run_status_raw,
    )
    hostile_status = _adjust_bundle_terminal_status(
        hostile_status,
        run_status_raw=run_status_raw,
    )

    if obs_session:
        wt = manifest_context.get("_research_bundle_wall_start_iso", "")
        extras_rv = {}
        if isinstance(wt, str) and wt.strip():
            extras_rv["start_time_iso"] = wt.strip()
        if rv_skip_reason:
            extras_rv["skip_reason"] = rv_skip_reason
        obs_session.emit_stage_completion(
            "research_validity",
            status=rv_status,
            duration_sec=float(manifest_context.get("_research_bundle_duration_sec", 0.0) or 0.0),
            major_warnings=rv_err or rv_skip_reason,
            paper_blocker_stage=False,
            next_stage_allowed=True if rv_skip_reason else int(result_code) == 0 or not rv_err,
            extras=extras_rv,
        )
        wf = manifest_context.get("_hostile_bundle_wall_start_iso", "")
        exh = {}
        if isinstance(wf, str) and wf.strip():
            exh["start_time_iso"] = wf.strip()
        if hostile_skip_reason:
            exh["skip_reason"] = hostile_skip_reason
        obs_session.emit_stage_completion(
            "hostile_audit",
            status=hostile_status,
            duration_sec=float(manifest_context.get("_hostile_bundle_duration_sec", 0.0) or 0.0),
            major_warnings=hostile_skip_reason
            or (("hostile_audit_partial_errors.txt non-empty") if hostile_failed else ""),
            next_stage_allowed=True,
            extras=exh,
        )

        mf_start = manifest_context.get("_manifest_finalize_wall_start_iso", "")
        mextra = {}
        if isinstance(mf_start, str) and mf_start.strip():
            mextra["start_time_iso"] = mf_start.strip()
        manifest_stage_status = "FAIL" if int(result_code) != 0 else "PASS"
        if run_status_raw == "partial":
            manifest_stage_status = "PASS_WITH_WARNINGS"
        obs_session.emit_stage_completion(
            "manifest_finalization",
            status=manifest_stage_status,
            duration_sec=float(manifest_context.get("_manifest_finalize_duration_sec", 0.0) or 0.0),
            next_stage_allowed=int(result_code) == 0,
            extras=mextra,
        )

    # --- Aggregate pipeline verdict (explicit about audits) ---
    evidence_readiness_issues = manifest_context.get("_evidence_readiness_failed_checks") or []

    from obsidiandroid.common.run_slots import is_canonical_v3_profile

    verdict = derive_aggregate_pipeline_verdict(
        run_status_raw=run_status_raw,
        result_code=int(result_code),
        rv_err=rv_err,
        hostile_failed=hostile_failed,
        readiness_issues=list(evidence_readiness_issues),
        failure_reason=str(
            manifest_context.get("failure_reason", "")
            or manifest_context.get("integrity_error", "")
            or ""
        ),
        canonical_v3=is_canonical_v3_profile(str(profile_id or "")),
    )

    publication_ready_terminal, reasons = evaluate_publication_ready_status(
        paper_mode=bool(paper_mode),
        manifest=manifest,
        compliance_report=compliance_report,
    )

    research_warnings_msgs = []
    rw = manifest_context.get("_research_warning_messages")
    if isinstance(rw, list):
        research_warnings_msgs = [str(x) for x in rw][:32]
    profile_id_runtime = str(profile_id or "").strip()
    split_algorithm_runtime = str(
        getattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "") or ""
    ).strip()
    if profile_id_runtime.startswith("malicious_temporal_") and split_algorithm_runtime:
        split_algo_norm = split_algorithm_runtime.lower()
        if "temporal" not in split_algo_norm and "year_holdout" not in split_algo_norm:
            temporal_warning = (
                f"[TEMPORAL] Profile {profile_id_runtime} used non-temporal split "
                f"algorithm {split_algorithm_runtime}; interpret results as random/group "
                "holdout evidence, not forward-in-time generalization."
            )
            if temporal_warning not in research_warnings_msgs:
                research_warnings_msgs.append(temporal_warning)
        else:
            temporal_summary = getattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", None)
            if isinstance(temporal_summary, dict):
                dropped_future_only = int(
                    temporal_summary.get("test_rows_dropped_unseen_train_classes", 0) or 0
                )
                test_year_floor = int(temporal_summary.get("test_year_floor", 0) or 0)
                if dropped_future_only > 0 and test_year_floor > 0:
                    temporal_warning = (
                        f"[TEMPORAL] Split {split_algorithm_runtime} used test years >= {test_year_floor} "
                        f"and dropped {dropped_future_only} newer-row sample(s) from classes unseen in "
                        "historical training years."
                    )
                    if temporal_warning not in research_warnings_msgs:
                        research_warnings_msgs.append(temporal_warning)

    cohort_contract = (
        manifest_context.get("paper_cohort_contract")
        if isinstance(manifest_context.get("paper_cohort_contract"), dict)
        else {}
    )
    cohort_validation = (
        cohort_contract.get("validation")
        if isinstance(cohort_contract.get("validation"), dict)
        else {}
    )
    cohort_validation_status = str(cohort_validation.get("status", "") or "").strip()
    cohort_validation_warning = str(cohort_validation.get("warning", "") or "").strip()
    if cohort_validation_status.startswith("degraded_") and cohort_validation_warning:
        if cohort_validation_warning not in research_warnings_msgs:
            research_warnings_msgs.append(cohort_validation_warning)

    split_blob = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    gov = manifest.get("cohort_size") or read_prepared_cohort_row_count(manifest_context)
    fused = manifest_context.get("fused_feature_rows")
    aligned = manifest_context.get("aligned_supervised_rows")
    post = manifest_context.get("post_low_support_training_rows")
    tr_ct = split_blob.get("train_sample_count") or manifest.get("train_sample_count")
    te_ct = split_blob.get("test_sample_count") or manifest.get("test_sample_count")

    sql_scope_row_count = read_sql_scope_row_count(manifest_context)
    vendor_eval_n = manifest_context.get("vendor_eval_sample_rows")
    perm_feat_n = manifest_context.get("permission_unique_rows")

    feat_pre = manifest.get("feature_count_pre_prune") or manifest_context.get("_aligned_feature_cols")
    feat_post = (
        manifest.get("feature_matrix_cols_post_prune")
        or manifest.get("feature_count_post_prune")
        or manifest_context.get("feature_matrix_cols_post_prune")
    )

    funnel_context = dict(manifest_context)
    if not funnel_context.get("support_floor_mode"):
        funnel_context["support_floor_mode"] = str(
            getattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "") or ""
        ).strip().lower()
    if tr_ct not in (None, ""):
        funnel_context.setdefault("train_sample_count", tr_ct)
    if te_ct not in (None, ""):
        funnel_context.setdefault("test_sample_count", te_ct)
    cohort_funnel_plain = build_cohort_funnel_plain(
        manifest=manifest if isinstance(manifest, dict) else {},
        manifest_context=funnel_context,
    )

    cohort_warn = manifest_context.get("cohort_population_warning")
    if cohort_warn is None and fused and gov and abs(int(_coerce_nonneg_int(gov)) - int(fused)) > 10:
        cohort_warn = (
            f"prepared cohort ({gov}) vs fused feature rows ({fused}) mismatch — "
            "inspect cohort funnel + feature_build_coverage."
        )

    model_summary = manifest.get("model_summary") or manifest_context.get("model_summary")
    top_model = ""
    top_macro_f1: Any = None
    if isinstance(model_summary, dict):
        top_model = str(model_summary.get("top_model", "") or "")
        top_macro_f1 = model_summary.get("top_macro_f1")

    paper_blockers_list: list[str]
    if isinstance(manifest_context.get("paper_blockers"), list):
        paper_blockers_list = [str(x) for x in manifest_context["paper_blockers"]]
    else:
        paper_blockers_list = [str(x) for x in (obs_session.paper_blockers_snapshot() if obs_session else [])]

    research_warn_combined = (
        research_warnings_msgs + [w["message"] for w in (obs_session.warnings_snapshot() if obs_session else [])]
    )[:32]

    ablation_snap = manifest_context.get("_ablation_cohort_gap_summary")
    if not isinstance(ablation_snap, dict):
        ablation_snap = {}
    label_stats = manifest_context.get("_ablation_label_target_stats")
    if not isinstance(label_stats, list):
        label_stats = []

    research_validity_enabled = bool(getattr(app_config, "ENABLE_RESEARCH_VALIDITY_BUNDLE", True))
    top_open = _top_artifacts_to_open(
        resolved_run_root,
        diagnostics_dir,
        run_id,
        verbose_run_artifacts=verbose_run_artifacts,
        research_validity_enabled=research_validity_enabled,
        paper_mode=bool(paper_mode),
        profile_id=profile_id,
        evidence_mode=bool(evidence_mode),
    )
    obs_summary_path_str = str(diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME)

    row_authority = (
        manifest.get("main_training_row_authority")
        or manifest_context.get("main_training_row_authority")
        or manifest_context.get("feature_matrix_row_authority")
    )
    label_strategy = _read_label_strategy_blob(diagnostics_dir, run_id)
    taxonomy_target_surface = _read_taxonomy_target_surface_blob(diagnostics_dir, run_id)
    dataset_foundation_payload: dict[str, Any] = {}
    dataset_foundation_path = diagnostics_dir / "dataset_foundation_summary.json"
    if dataset_foundation_path.exists():
        try:
            dataset_foundation_payload = json.loads(dataset_foundation_path.read_text(encoding="utf-8"))
        except Exception:
            dataset_foundation_payload = {}
    supervised_family_claims_suitable = bool(
        dataset_foundation_payload.get("supervised_family_claims_suitable", False)
    )
    temporal_split_summary = {}
    split_blob = manifest_context.get("split")
    if isinstance(split_blob, dict):
        temporal_split_summary = (
            split_blob.get("temporal_split_summary")
            if isinstance(split_blob.get("temporal_split_summary"), dict)
            else {}
        )
    training_reached = completed_stage in {"training", "ablation", "permission_trends", "label_resolution", "manifest"}
    if training_reached and top_macro_f1 is not None:
        scientific_adequacy, scientific_blockers = classify_scientific_adequacy(
            macro_f1=top_macro_f1,
            supervised_family_claims_suitable=supervised_family_claims_suitable,
            dropped_future_only_rows=temporal_split_summary.get("test_rows_dropped_unseen_train_classes", 0),
        )
    else:
        scientific_adequacy, scientific_blockers = ("Not assessed", [])
    taxonomy_summary_payload: dict[str, Any] = {}
    taxonomy_summary_path = diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json"
    if taxonomy_summary_path.exists():
        try:
            taxonomy_summary_payload = json.loads(taxonomy_summary_path.read_text(encoding="utf-8"))
        except Exception:
            taxonomy_summary_payload = {}
    label_resolution_enabled = bool(manifest_context.get("label_resolution_enabled", True))
    type_guard_family_suppressed_count = int(
        taxonomy_summary_payload.get("type_guard_family_suppressed_count", 0) or 0
    )
    alignment_attrition = (
        manifest_context.get("alignment_attrition_stats")
        if isinstance(manifest_context.get("alignment_attrition_stats"), dict)
        else {}
    )
    alignment_attrition_details = (
        manifest_context.get("alignment_attrition_details")
        if isinstance(manifest_context.get("alignment_attrition_details"), dict)
        else {}
    )
    low_support_detail = (
        manifest_context.get("low_support_family_drop_detail")
        if isinstance(manifest_context.get("low_support_family_drop_detail"), list)
        else []
    )
    low_support_row_drop_count = 0
    low_support_family_drop_count = 0
    low_support_top: list[tuple[str, int]] = []
    for row in low_support_detail:
        if not isinstance(row, dict):
            continue
        family = str(row.get("family", "")).strip()
        if not family:
            continue
        try:
            support = int(row.get("aligned_support"))
        except (TypeError, ValueError):
            continue
        low_support_family_drop_count += 1
        low_support_row_drop_count += support
        low_support_top.append((family, support))
    low_support_top.sort(key=lambda item: (item[1], item[0].lower()))
    low_support_top_preview = ", ".join(
        f"{family}={support}" for family, support in low_support_top[:5]
    )
    if len(low_support_top) > 5:
        low_support_top_preview += ", …"
    benchmark_support_policy = (
        taxonomy_target_surface.get("benchmark_support_policy")
        if isinstance(taxonomy_target_surface.get("benchmark_support_policy"), dict)
        else {}
    )
    benchmark_tier_counts = (
        taxonomy_target_surface.get("tier_counts")
        if isinstance(taxonomy_target_surface.get("tier_counts"), dict)
        else {}
    )
    benchmark_support_excluded_rows = int(
        benchmark_tier_counts.get("excluded_below_benchmark_support_samples", 0) or 0
    )
    benchmark_support_excluded_families = int(
        benchmark_support_policy.get("excluded_below_support_family_count", 0) or 0
    )
    target_rows = taxonomy_target_surface.get("targets", []) if isinstance(taxonomy_target_surface.get("targets"), list) else []
    family_target_row = next(
        (
            row for row in target_rows
            if isinstance(row, dict) and str(row.get("surface_name", "") or "").strip() == "family_id"
        ),
        {},
    )
    type_target_row = next(
        (
            row for row in target_rows
            if isinstance(row, dict) and str(row.get("surface_name", "") or "").strip() == "type_slug"
        ),
        {},
    )
    visible_family_count = int(family_target_row.get("unique_classes", 0) or 0)
    benchmark_trainable_family_count = int(
        family_target_row.get("trainable_classes_at_min_support", 0)
        or benchmark_support_policy.get("benchmark_eligible_family_count", 0)
        or 0
    )
    visible_type_count = int(type_target_row.get("unique_classes", 0) or 0)
    modeled_family_class_count = int(
        getattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 0) or 0
    )
    claim_audit_alias = _claim_audit_alias_name(
        profile_id=str(profile_id or ""),
        evidence_mode=bool(evidence_mode),
        paper_mode=bool(paper_mode),
    )
    claim_surface_label = _claim_surface_label(
        profile_id=str(profile_id or ""),
        evidence_mode=bool(evidence_mode),
        paper_mode=bool(paper_mode),
    )
    benchmark_support_top_rows: list[str] = []
    for row in benchmark_support_policy.get("excluded_below_support_families", []) or []:
        if not isinstance(row, dict):
            continue
        family = str(row.get("family_canonical", "") or "").strip()
        if not family:
            continue
        try:
            support = int(row.get("sample_count", 0) or 0)
        except (TypeError, ValueError):
            support = 0
        benchmark_support_top_rows.append(f"{family}={support}")
    benchmark_support_top_preview = ", ".join(benchmark_support_top_rows[:5])
    if len(benchmark_support_top_rows) > 5:
        benchmark_support_top_preview += ", …"
    benchmark_support_floor = benchmark_support_policy.get("benchmark_min_support")
    temporal_dropped_family_counts = (
        temporal_split_summary.get("test_rows_dropped_unseen_train_class_families")
        if isinstance(temporal_split_summary.get("test_rows_dropped_unseen_train_class_families"), dict)
        else {}
    )

    status_blob = {
        "schema_version": "2.0",
        "run_id": run_id,
        "run_instance_id": str(manifest.get("run_instance_id", "") or manifest_context.get("run_instance_id", "") or run_id),
        "run_slot": str(manifest.get("run_slot", "") or manifest_context.get("run_slot", "") or ""),
        "run_mode": str(manifest.get("run_mode", "") or manifest_context.get("run_mode", "") or ""),
        "claim_surface": str(manifest.get("claim_surface", "") or manifest_context.get("claim_surface", "") or ""),
        "claim_surface_label": claim_surface_label,
        "run_started_at_utc": str(manifest.get("run_started_at_utc", "") or manifest_context.get("run_started_at_utc", "") or manifest.get("timestamp_utc", "") or ""),
        "profile_id": profile_id,
        "run_status": run_status_raw,
        "completed_stage": completed_stage,
        "pipeline_status": verdict,
        "paper_mode": bool(paper_mode),
        "evidence_mode": bool(evidence_mode),
        "verbose_run_artifacts": bool(verbose_run_artifacts),
        "research_validity_bundle_enabled": bool(research_validity_enabled),
        "research_validity_status": rv_status,
        "research_validity_skip_reason": rv_skip_reason or None,
        "hostile_audit_status": hostile_status,
        "hostile_audit_skip_reason": hostile_skip_reason or None,
        "hostile_audit_degraded": bool(hostile_failed),
        "label_resolution_enabled": label_resolution_enabled,
        "type_guard_family_suppressed_count": type_guard_family_suppressed_count,
        "coarse_aligned_supervised_rows": _coerce_int(manifest_context.get("coarse_aligned_supervised_rows")),
        "training_authority_aligned_rows": _coerce_int(
            manifest_context.get("training_authority_aligned_rows")
        ),
        "alignment_non_authoritative_family_drop_count": int(
            alignment_attrition.get("alignment_non_authoritative_family_drop_count", 0) or 0
        ),
        "alignment_live_authority_rescue_count": int(
            alignment_attrition.get("alignment_live_authority_rescue_count", 0) or 0
        ),
        "alignment_live_authority_rescue_families_top": _format_top_count_pairs(
            alignment_attrition_details.get("alignment_live_authority_rescue_families", {})
            if isinstance(alignment_attrition_details, dict)
            else {}
        ),
        "alignment_non_authoritative_family_drops_top": _format_top_count_pairs(
            alignment_attrition_details.get("alignment_non_authoritative_family_drop_families", {})
            if isinstance(alignment_attrition_details, dict)
            else {}
        ),
        "low_support_family_drop_count": int(low_support_family_drop_count),
        "low_support_row_drop_count": int(low_support_row_drop_count),
        "low_support_family_drops_top": low_support_top_preview,
        "benchmark_support_floor": _coerce_int(benchmark_support_floor),
        "benchmark_support_excluded_sample_count": int(benchmark_support_excluded_rows),
        "benchmark_support_excluded_family_count": int(benchmark_support_excluded_families),
        "benchmark_support_excluded_families_top": benchmark_support_top_preview,
        "visible_family_count": visible_family_count,
        "benchmark_trainable_family_count": benchmark_trainable_family_count,
        "modeled_family_class_count": modeled_family_class_count,
        "visible_type_count": visible_type_count,
        "family_conflict_count": int(taxonomy_summary_payload.get("taxonomy_mismatch_count", 0) or 0),
        "temporal_future_only_family_drops_top": _format_top_count_pairs(temporal_dropped_family_counts),
        "main_training_row_authority": row_authority,
        "cohort_rows": _coerce_int(gov),
        KEY_COHORT_SQL_SCOPE_ROW_COUNT: _coerce_int(sql_scope_row_count),
        KEY_COHORT_PREPARED_ROW_COUNT: _coerce_int(gov),
        "gate_total_candidates": _coerce_int(sql_scope_row_count),
        "raw_candidate_rows": _coerce_int(sql_scope_row_count),
        "governed_cohort_rows": _coerce_int(gov),
        "vendor_eval_sample_rows": _coerce_int(vendor_eval_n),
        "permission_feature_rows": _coerce_int(perm_feat_n),
        "counts": {
            KEY_COHORT_SQL_SCOPE_ROW_COUNT: _coerce_int(sql_scope_row_count),
            KEY_COHORT_PREPARED_ROW_COUNT: _coerce_int(gov),
            "gate_total_candidates": _coerce_int(sql_scope_row_count),
            "raw_candidate_rows": _coerce_int(sql_scope_row_count),
            "governed_cohort_rows": _coerce_int(gov),
            "vendor_eval_sample_rows": _coerce_int(vendor_eval_n),
            "permission_feature_rows": _coerce_int(perm_feat_n),
            "feature_matrix_rows": _coerce_int(fused),
            "aligned_supervised_rows": _coerce_int(aligned),
            "aligned_rows": _coerce_int(aligned),
            "post_low_support_training_rows": _coerce_int(post),
            "supervised_training_rows": _coerce_int(post),
            "train_rows": _coerce_int(tr_ct),
            "test_rows": _coerce_int(te_ct),
            "feature_matrix_cols_post_prune": _coerce_int(feat_post),
        },
        "features": {
            "feature_matrix_cols_pre_prune": _coerce_int(feat_pre),
            "pre_prune": _coerce_int(feat_pre),
            "feature_matrix_cols_post_prune": _coerce_int(feat_post),
            "post_prune": _coerce_int(feat_post),
        },
        "model": {
            "top_model": top_model,
            "top_macro_f1": top_macro_f1,
            "top_model_primary_metric_name": (
                model_summary.get("top_model_primary_metric_name")
                if isinstance(model_summary, dict)
                else None
            ),
            "top_model_primary_metric_value": (
                model_summary.get("top_model_primary_metric_value")
                if isinstance(model_summary, dict)
                else None
            ),
            "top_model_primary_metric_tier": (
                model_summary.get("top_model_primary_metric_tier")
                if isinstance(model_summary, dict)
                else None
            ),
            "top_model_weighted_f1_tier": (
                model_summary.get("top_model_weighted_f1_tier")
                if isinstance(model_summary, dict)
                else None
            ),
            "top_model_accuracy_tier": (
                model_summary.get("top_model_accuracy_tier")
                if isinstance(model_summary, dict)
                else None
            ),
        },
        "model_summary": model_summary,
        "scientific_adequacy": {
            "posture": scientific_adequacy,
            "blockers": scientific_blockers,
            "supervised_family_claims_suitable": supervised_family_claims_suitable,
            "temporal_future_only_rows_dropped": temporal_split_summary.get(
                "test_rows_dropped_unseen_train_classes", 0
            ),
        },
        "manifest_finalize_duration_sec": float(manifest_context.get("_manifest_finalize_duration_sec", 0.0) or 0.0),
        "ablation": {
            "status_line": manifest_context.get("_ablation_run_status_summary", ""),
            "cohort_gap_summary": ablation_snap,
            "label_target_class_stats": label_stats,
        },
        "research_warnings_top": research_warn_combined,
        "research_warnings": research_warn_combined,
        "paper_blockers": paper_blockers_list,
        "top_artifacts_to_open_first": top_open,
        "claim_audit_summary": str(diagnostics_dir / claim_audit_alias),
        "figure_audit_summary": str(diagnostics_dir / "figure_validity_audit.md"),
        "cohort_population_warning": cohort_warn if cohort_warn is not None else "",
        "cohort_funnel_plain": cohort_funnel_plain,
        "train_sample_count": tr_ct,
        "test_sample_count": te_ct,
        "post_low_support_training_rows": post,
        "feature_matrix_rows": fused,
        "aligned_supervised_rows": aligned,
        "research_validity_error": rv_err or None,
        "research_validity_partial_failures": list(
            manifest_context.get("research_validity_partial_failures", []) or []
        ),
        "cohort_persistence_source": str(manifest_context.get("cohort_persistence_source", "") or "") or None,
        "dataset_hash": str(manifest.get("dataset_hash", "") or manifest_context.get("dataset_hash", "") or "") or None,
        "v3_dl_handoff": _build_v3_dl_handoff_observability_block(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest=manifest if isinstance(manifest, dict) else {},
            manifest_context=manifest_context if isinstance(manifest_context, dict) else {},
        ),
        "manifest_result_code": int(result_code),
        "row_authority": row_authority,
        "label_strategy": {
            "preferred_family_target": label_strategy.get("preferred_family_target"),
            "preferred_family_reporting_surface": label_strategy.get("preferred_family_reporting_surface"),
            "preferred_type_target": label_strategy.get("preferred_type_target"),
            "preferred_hierarchical_target": label_strategy.get("preferred_hierarchical_target"),
            "avoid_for_primary_claims": label_strategy.get("avoid_for_primary_claims", []),
            "alignment_interpretation": label_strategy.get("alignment_interpretation"),
        },
        "paths": {
            "run_observability_summary_json": obs_summary_path_str,
            "pipeline_stage_summary_csv": str(diagnostics_dir / "pipeline_stage_summary.csv"),
            "pipeline_stage_summary_md": str(diagnostics_dir / "pipeline_stage_summary.md"),
            "pipeline_events_jsonl": str(diagnostics_dir / "pipeline_events.jsonl"),
            "logging_audit_md": str(diagnostics_dir / "logging_audit.md") if verbose_run_artifacts else "",
            "logging_audit_csv": str(diagnostics_dir / "logging_audit.csv") if verbose_run_artifacts else "",
            "partial_failures_md": str(diagnostics_dir / "partial_failures.md"),
            "run_manifest_json": str(resolved_run_root / "run_manifest.json") if resolved_run_root else "",
            "run_summary_json": str(resolved_run_root / "run_summary.json") if resolved_run_root else "",
            "run_evidence_index_md": str(resolved_run_root / "run_evidence_index.md") if resolved_run_root else "",
        },
    }
    status_blob.update(publication_ready_payload(publication_ready_terminal, reasons))

    summary_text = json.dumps(status_blob, indent=2, sort_keys=True)
    summary_path = diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary_text, encoding="utf-8")
    sp = str(summary_path)
    if sp not in artifact_list:
        artifact_list.append(sp)

    _rewrite_stage_summary_md(diagnostics_dir)
    _partial_failures_md(
        diagnostics_dir,
        manifest_context=manifest_context,
        rv_err=rv_err,
        hostile_failed=hostile_failed,
        verdict=verdict,
    )

    if verbose_run_artifacts:
        log_md, log_csv = write_logging_audit_artifacts(diagnostics_dir, run_id=run_id)
        for lp in (log_md, log_csv):
            if str(lp) not in artifact_list:
                artifact_list.append(str(lp))

    # Terminal visibility (minimal mode suppresses duplicates elsewhere)
    if not bool(run_status_raw == "failed" and int(result_code) != 0 and verdict.endswith("UNKNOWN")):
        du.print_section("Observability snapshot")
        du.print_stat("Aggregate pipeline verdict", verdict)
        du.print_stat("Research validity bundle", rv_status + (f" ({rv_err})" if rv_err else ""))
        du.print_stat("strict_publication_status", publication_ready_terminal)
        du.print_stat(AUTHORITATIVE_SUMMARY_FILENAME, str(summary_path))

    manifest_context["_observability_finalized_once"] = True
    return summary_path


def _observability_funnel_manifest_context(
    *,
    observability: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge observability rollup counts into a funnel manifest_context."""
    ctx = dict(manifest_context) if isinstance(manifest_context, dict) else {}
    for key in (
        "aligned_supervised_rows",
        "post_low_support_training_rows",
        "cohort_prepared_row_count",
        "support_floor_mode",
        "alignment_attrition_stats",
        "alignment_attrition_details",
        "low_support_family_drop_detail",
        "train_sample_count",
        "test_sample_count",
    ):
        if key not in ctx or ctx.get(key) in (None, ""):
            if key in observability and observability.get(key) not in (None, ""):
                ctx[key] = observability.get(key)
    fused = observability.get("feature_matrix_rows")
    if fused not in (None, "") and ctx.get("fused_feature_rows") in (None, ""):
        ctx["fused_feature_rows"] = fused
    if ctx.get("cohort_prepared_row_count") in (None, ""):
        prepared = manifest.get("cohort_prepared_row_count") or manifest.get("cohort_size")
        if prepared not in (None, ""):
            ctx["cohort_prepared_row_count"] = prepared
    return ctx


def patch_observability_funnel_fields(
    *,
    diagnostics_dir: Path,
    manifest: dict[str, Any] | None = None,
    manifest_context: dict[str, Any] | None = None,
) -> bool:
    """Rewrite cohort funnel plain text and attrition fields on observability JSON."""
    obs_path = diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME
    if not obs_path.is_file():
        return False
    try:
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(obs, dict):
        return False
    manifest_payload = manifest if isinstance(manifest, dict) else {}
    funnel_context = _observability_funnel_manifest_context(
        observability=obs,
        manifest=manifest_payload,
        manifest_context=manifest_context,
    )
    obs["cohort_funnel_plain"] = build_cohort_funnel_plain(
        manifest=manifest_payload,
        manifest_context=funnel_context,
    )
    attrition = (
        funnel_context.get("alignment_attrition_stats")
        if isinstance(funnel_context.get("alignment_attrition_stats"), dict)
        else {}
    )
    obs["alignment_non_authoritative_family_drop_count"] = int(
        attrition.get("alignment_non_authoritative_family_drop_count", 0) or 0
    )
    obs_path.write_text(json.dumps(obs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def patch_observability_post_operator_artifacts(
    *,
    diagnostics_dir: Path,
    manifest: dict[str, Any] | None = None,
    manifest_context: dict[str, Any] | None = None,
) -> bool:
    """Refresh operator-derived observability fields after post-finalize artifacts exist.

    ``finalize_pipeline_observability`` runs inside the hygiene bundle before
    ``emit_research_operator_report`` materializes ``dataset_foundation_summary.json``.
    Without this patch, scientific adequacy and claim-surface labels can disagree with
    the refreshed dataset foundation and resolved publication/evidence mode.
    """
    from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode

    obs_path = diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME
    foundation_path = diagnostics_dir / "dataset_foundation_summary.json"
    if not obs_path.is_file() or not foundation_path.is_file():
        return False
    try:
        obs = json.loads(obs_path.read_text(encoding="utf-8"))
        foundation = json.loads(foundation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(obs, dict) or not isinstance(foundation, dict):
        return False

    supervised = bool(foundation.get("supervised_family_claims_suitable", False))
    model_blob = obs.get("model") if isinstance(obs.get("model"), dict) else {}
    macro = model_blob.get("top_model_primary_metric_value")
    if macro is None:
        macro = model_blob.get("top_macro_f1")
    sci_existing = obs.get("scientific_adequacy") if isinstance(obs.get("scientific_adequacy"), dict) else {}
    temporal_dropped = int(sci_existing.get("temporal_future_only_rows_dropped", 0) or 0)
    adequacy, blockers = classify_scientific_adequacy(
        macro_f1=macro,
        supervised_family_claims_suitable=supervised,
        dropped_future_only_rows=temporal_dropped,
    )
    obs["scientific_adequacy"] = {
        "posture": adequacy,
        "blockers": blockers,
        "supervised_family_claims_suitable": supervised,
        "temporal_future_only_rows_dropped": temporal_dropped,
    }

    manifest_payload = manifest if isinstance(manifest, dict) else {}
    profile_id = str(
        manifest_payload.get("profile_id")
        or obs.get("profile_id")
        or ""
    ).strip()
    publication_active = coalesce_manifest_publication_mode(manifest_payload)
    if not publication_active and isinstance(manifest_payload.get("paper_mode"), dict):
        publication_active = coalesce_manifest_publication_mode(
            {"evidence_mode": manifest_payload.get("paper_mode")}
        )
    obs["evidence_mode"] = publication_active
    obs["paper_mode"] = publication_active
    obs["claim_surface_label"] = _claim_surface_label(
        profile_id=profile_id,
        evidence_mode=publication_active,
        paper_mode=publication_active,
    )
    obs["claim_audit_summary"] = str(
        diagnostics_dir
        / _claim_audit_alias_name(
            profile_id=profile_id,
            evidence_mode=publication_active,
            paper_mode=publication_active,
        )
    )

    obs_path.write_text(json.dumps(obs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    patch_observability_funnel_fields(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest_payload,
        manifest_context=manifest_context,
    )
    return True


def patch_observability_scientific_adequacy_from_dataset_foundation(
    *,
    diagnostics_dir: Path,
) -> bool:
    """Backward-compatible alias for the expanded post-operator observability patch."""
    return patch_observability_post_operator_artifacts(diagnostics_dir=diagnostics_dir)


def _adjust_bundle_terminal_status(status: str, *, run_status_raw: str) -> str:
    """Normalize bundle status labels for interrupted / partial runs."""
    normalized = str(status or "").strip().upper() or "UNKNOWN"
    terminal = str(run_status_raw or "").strip().lower()
    if terminal not in {"interrupted", "partial"}:
        return normalized
    if normalized == "PASS":
        return "PASS_PARTIAL"
    if normalized == "PASS_WITH_WARNINGS":
        return "PASS_PARTIAL"
    if normalized == "SKIPPED":
        return "SKIPPED_PARTIAL"
    return normalized


def diagnostic_status_path_fallback(diagnostics_dir: Path) -> Path:
    diagnostics_dir = Path(diagnostics_dir)
    primary = diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME
    if primary.exists():
        return primary
    return diagnostics_dir / "logging_audit.md"


def _coerce_nonneg_int(value: Any) -> int:
    """Best-effort non-negative int for comparing declared row counts."""
    try:
        return int(value or 0)
    except Exception:
        return 0


def _rewrite_stage_summary_md(diagnostics_dir: Path) -> None:
    csv_path = diagnostics_dir / "pipeline_stage_summary.csv"
    out_md = diagnostics_dir / "pipeline_stage_summary.md"
    if not csv_path.exists():
        out_md.write_text("# Pipeline stage summary\n\n_No CSV emitted._\n", encoding="utf-8")
        return
    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    lines = [
        "# Pipeline stage summary",
        "",
        "| stage | status | duration_sec | output_rows | output_features | blockers/warnings snippet | next_ok |",
        "|-------|--------|-------------:|------------:|---------------:|--------------------------|---------|",
    ]
    for r in rows:
        warn_snip = (r.get("major_warnings") or "").replace("|", "\\|").replace("\n", " ")[:140]
        lines.append(
            f"| `{r.get('stage_name','')}` | `{r.get('status','')}` "
            f"| `{r.get('duration_sec','')}` | `{r.get('output_rows','')}` | `{r.get('output_features','')}` "
            f"| {warn_snip} | `{r.get('next_stage_allowed','')}` |"
        )
    lines.append("")
    lines.append("_Full machine-readable table: `pipeline_stage_summary.csv`._")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def _partial_failures_md(
    diagnostics_dir: Path,
    *,
    manifest_context: dict[str, Any],
    rv_err: str,
    hostile_failed: bool,
    verdict: str,
) -> None:
    path = diagnostics_dir / "partial_failures.md"
    obs = manifest_context.get("pipeline_observability")
    snaps: list[dict[str, Any]] = []
    if isinstance(obs, PipelineObservabilitySession):
        snaps = obs.partial_failures_snapshot()

    lines = ["# Partial failures & degraded outputs", "", f"- **Aggregate verdict:** `{verdict}`", ""]
    if rv_err:
        lines.extend(["## Research validity bundle", "", f"- {rv_err}", ""])
    if hostile_failed:
        lines.extend(["## Skeptic audit", "", "_See hostile_audit_partial_errors.txt for step-level faults._", ""])
    if snaps:
        lines.append("## Session partial-failure ledger")
        lines.append("")
        for item in snaps:
            lines.append(f"- **`{item.get('stage')}`:** {item.get('error')}")
        lines.append("")
    if not snaps and not rv_err and not hostile_failed:
        lines.append("_No partial-failure ledger entries for this run._")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = ["finalize_pipeline_observability"]
