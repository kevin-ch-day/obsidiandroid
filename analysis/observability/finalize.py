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

from utils import display_utils as du

from analysis.diagnostics.cohort_vocabulary import (
    KEY_COHORT_PREPARED_ROW_COUNT,
    KEY_COHORT_SQL_SCOPE_ROW_COUNT,
    read_prepared_cohort_row_count,
    read_sql_scope_row_count,
)
from analysis.diagnostics.output_inventory import evaluate_paper_safe_status
from analysis.observability.logging_audit import write_logging_audit_artifacts
from analysis.observability.session import PipelineObservabilitySession


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


def _coerce_int(v: Any) -> int | None:
    """Best-effort int for dashboard fields."""
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _top_artifacts_to_open(run_root: Path | None, diagnostics_dir: Path, run_id: str) -> list[str]:
    """Ordered open-first list (paths may be written in the same hygiene pass)."""
    rr = run_root if run_root is not None else diagnostics_dir
    ordered: list[Path] = [
        rr / "run_evidence_index.md",
        diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME,
        diagnostics_dir / "pipeline_stage_summary.md",
        diagnostics_dir / "partial_failures.md",
        diagnostics_dir / "paper_claim_audit.md",
        diagnostics_dir / "cohort_funnel.md",
        diagnostics_dir / "recommended_findings.md",
        diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json",
        diagnostics_dir / "logging_audit.md",
        diagnostics_dir / "figure_validity_audit.md",
        diagnostics_dir / "hostile_audit_partial_errors.txt",
    ]
    return [str(p) for p in ordered][:16]


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

    run_status_raw = str(manifest_context.get("run_status", "")).strip().lower()
    if not run_status_raw:
        run_status_raw = "complete" if int(result_code) == 0 else "failed"

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
    hostile_err_path = diagnostics_dir / "hostile_audit_partial_errors.txt"
    hostile_failed = hostile_err_path.exists() and hostile_err_path.stat().st_size > 0

    rv_status = "PASS"
    if rv_err:
        rv_status = "FAIL"
        if obs_session:
            obs_session.record_partial_failure(stage="research_validity", error=rv_err, recoverable=True)

    hostile_status = "PASS"
    if hostile_failed:
        hostile_status = "PASS_WITH_WARNINGS"
        summary_txt = hostile_err_path.read_text(encoding="utf-8")[:1200]
        manifest_context["_hostile_audit_warning_blob"] = summary_txt
        if obs_session:
            obs_session.record_partial_failure(
                stage="hostile_audit",
                error=f"partial steps logged in {hostile_err_path}",
                recoverable=True,
            )

    if obs_session:
        wt = manifest_context.get("_research_bundle_wall_start_iso", "")
        extras_rv = {}
        if isinstance(wt, str) and wt.strip():
            extras_rv["start_time_iso"] = wt.strip()
        obs_session.emit_stage_completion(
            "research_validity",
            status=rv_status,
            duration_sec=float(manifest_context.get("_research_bundle_duration_sec", 0.0) or 0.0),
            major_warnings=rv_err or "",
            paper_blocker_stage=False,
            next_stage_allowed=int(result_code) == 0 or not rv_err,
            extras=extras_rv,
        )
        wf = manifest_context.get("_hostile_bundle_wall_start_iso", "")
        exh = {}
        if isinstance(wf, str) and wf.strip():
            exh["start_time_iso"] = wf.strip()
        obs_session.emit_stage_completion(
            "hostile_audit",
            status=hostile_status,
            duration_sec=float(manifest_context.get("_hostile_bundle_duration_sec", 0.0) or 0.0),
            major_warnings=("hostile_audit_partial_errors.txt non-empty") if hostile_failed else "",
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

    verdict = _derive_aggregate_pipeline_verdict(
        run_status_raw=run_status_raw,
        result_code=int(result_code),
        rv_err=rv_err,
        hostile_failed=hostile_failed,
        readiness_issues=list(evidence_readiness_issues),
    )

    paper_safe_terminal, reasons = evaluate_paper_safe_status(
        paper_mode=bool(paper_mode),
        manifest=manifest,
        compliance_report=compliance_report,
    )

    research_warnings_msgs = []
    rw = manifest_context.get("_research_warning_messages")
    if isinstance(rw, list):
        research_warnings_msgs = [str(x) for x in rw][:32]

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
        or manifest.get("feature_matrix_row_count")
    )

    parts: list[str] = []
    if gov not in (None, ""):
        parts.append(f"{gov} prepared-cohort rows")
    if fused not in (None, ""):
        parts.append(f"{fused} feature_matrix_rows (fused)")
    if aligned not in (None, ""):
        parts.append(f"{aligned} aligned supervised")
    if post not in (None, ""):
        parts.append(
            f"{post} post-family-support trainable rows "
            "(training pool after min-family filter; not cohort size)"
        )
    if tr_ct not in (None, "") or te_ct not in (None, ""):
        parts.append(f"train={tr_ct}/test={te_ct}")
    cohort_funnel_plain = " → ".join(parts)

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

    top_open = _top_artifacts_to_open(resolved_run_root, diagnostics_dir, run_id)
    obs_summary_path_str = str(diagnostics_dir / AUTHORITATIVE_SUMMARY_FILENAME)

    status_blob = {
        "schema_version": "2.0",
        "run_id": run_id,
        "profile_id": profile_id,
        "pipeline_status": verdict,
        "paper_mode": bool(paper_mode),
        "evidence_mode": bool(evidence_mode),
        "paper_safe_status": paper_safe_terminal,
        "paper_safe_reasons": reasons,
        "research_validity_status": rv_status,
        "hostile_audit_status": hostile_status,
        "hostile_audit_degraded": bool(hostile_failed),
        "main_training_row_authority": manifest.get("main_training_row_authority")
        or manifest_context.get("main_training_row_authority"),
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
        "model": {"top_model": top_model, "top_macro_f1": top_macro_f1},
        "model_summary": model_summary,
        "ablation": {
            "status_line": manifest_context.get("_ablation_run_status_summary", ""),
            "cohort_gap_summary": ablation_snap,
            "label_target_class_stats": label_stats,
        },
        "research_warnings_top": research_warn_combined,
        "research_warnings": research_warn_combined,
        "paper_blockers": paper_blockers_list,
        "top_artifacts_to_open_first": top_open,
        "claim_audit_summary": str(diagnostics_dir / "paper_claim_audit.md"),
        "figure_audit_summary": str(diagnostics_dir / "figure_validity_audit.md"),
        "cohort_population_warning": cohort_warn if cohort_warn is not None else "",
        "cohort_funnel_plain": cohort_funnel_plain,
        "train_sample_count": tr_ct,
        "test_sample_count": te_ct,
        "post_low_support_training_rows": post,
        "feature_matrix_rows": fused,
        "aligned_supervised_rows": aligned,
        "research_validity_error": rv_err or None,
        "manifest_result_code": int(result_code),
        "row_authority": manifest.get("main_training_row_authority"),
        "paths": {
            "run_observability_summary_json": obs_summary_path_str,
            "pipeline_stage_summary_csv": str(diagnostics_dir / "pipeline_stage_summary.csv"),
            "pipeline_stage_summary_md": str(diagnostics_dir / "pipeline_stage_summary.md"),
            "pipeline_events_jsonl": str(diagnostics_dir / "pipeline_events.jsonl"),
            "logging_audit_md": str(diagnostics_dir / "logging_audit.md"),
            "logging_audit_csv": str(diagnostics_dir / "logging_audit.csv"),
            "partial_failures_md": str(diagnostics_dir / "partial_failures.md"),
            "run_manifest_json": str(resolved_run_root / "run_manifest.json") if resolved_run_root else "",
            "run_summary_json": str(resolved_run_root / "run_summary.json") if resolved_run_root else "",
            "run_evidence_index_md": str(resolved_run_root / "run_evidence_index.md") if resolved_run_root else "",
        },
    }

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

    log_md, log_csv = write_logging_audit_artifacts(diagnostics_dir, run_id=run_id)
    for lp in (log_md, log_csv):
        if str(lp) not in artifact_list:
            artifact_list.append(str(lp))

    # Terminal visibility (minimal mode suppresses duplicates elsewhere)
    if not bool(run_status_raw == "failed" and int(result_code) != 0 and verdict.endswith("UNKNOWN")):
        du.print_section("Observability snapshot")
        du.print_stat("Aggregate pipeline verdict", verdict)
        du.print_stat("Research validity bundle", rv_status + (f" ({rv_err})" if rv_err else ""))
        du.print_stat("paper_safe_status (strict)", paper_safe_terminal)
        du.print_stat(AUTHORITATIVE_SUMMARY_FILENAME, str(summary_path))

    manifest_context["_observability_finalized_once"] = True
    return summary_path


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


def _derive_aggregate_pipeline_verdict(
    *,
    run_status_raw: str,
    result_code: int,
    rv_err: str,
    hostile_failed: bool,
    readiness_issues: list[Any],
) -> str:
    if result_code != 0 and run_status_raw == "failed":
        return "FAIL"
    if rv_err.strip():
        return "FAIL_WITH_PARTIAL_AUDITS"
    if hostile_failed:
        return "PASS_WITH_WARNINGS"
    if readiness_issues:
        return "PASS_WITH_WARNINGS"
    if run_status_raw == "partial":
        return "PASS_WITH_WARNINGS"
    if run_status_raw == "complete":
        return "PASS"
    return "PASS_WITH_WARNINGS"


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
        lines.extend(["## Hostile audit", "", "_See hostile_audit_partial_errors.txt for step-level faults._", ""])
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
