"""Compact terminal run health (Pass 5) built from observability + inventory payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common.publication_readiness import (
    coalesce_publication_ready_reasons,
    coalesce_publication_ready_status,
)


def print_unified_run_health(
    *,
    inventory_summary: dict[str, Any],
    observability_json_path: Path,
    evidence_index_path: Path | None,
    run_root: Path,
) -> None:
    """Single terminal block: pipeline verdict, publication posture, cohort funnel string, top warnings, open-first list."""
    if ml_console.is_minimal():
        return

    base = Path(observability_json_path).parent
    payload: dict[str, Any] = {}
    obs_resolved = Path(observability_json_path)
    candidates: list[Path] = []
    seen: set[str] = set()
    for cand in (
        base / "run_observability_summary.json",
        obs_resolved,
    ):
        key = str(cand)
        if key not in seen:
            seen.add(key)
            candidates.append(cand)
    for cand in candidates:
        if cand.exists():
            try:
                payload = json.loads(cand.read_text(encoding="utf-8"))
                obs_resolved = cand
                break
            except Exception:
                payload = {}

    du.print_section("Run Health")
    du.print_stat("Run ID", payload.get("run_id", "unknown"))
    du.print_stat("Profile", payload.get("profile_id", "unknown"))
    du.print_stat("Pipeline (aggregate)", payload.get("pipeline_status", "UNKNOWN"))
    research_validity_status = str(payload.get("research_validity_status", "UNKNOWN") or "UNKNOWN")
    research_validity_skip_reason = str(payload.get("research_validity_skip_reason", "") or "").strip()
    if research_validity_skip_reason:
        du.print_stat("Research validity bundle", f"{research_validity_status} ({research_validity_skip_reason})")
    else:
        du.print_stat("Research validity bundle", research_validity_status)
    du.print_stat("Publication-ready mode", "ON" if payload.get("paper_mode") else "OFF")
    du.print_stat("Evidence mode", "ON" if payload.get("evidence_mode") else "OFF")
    publication_ready_status = coalesce_publication_ready_status(payload)
    du.print_stat("publication_ready_status", publication_ready_status)
    publication_ready_reasons = coalesce_publication_ready_reasons(payload)
    if publication_ready_reasons:
        du.print_stat("publication_ready_reasons", ", ".join(str(x) for x in publication_ready_reasons))

    row_auth = payload.get("main_training_row_authority") or payload.get("row_authority")
    du.print_stat("Row authority", row_auth or "n/a")
    ab_line = ""
    ab_obj = payload.get("ablation")
    if isinstance(ab_obj, dict):
        ab_line = str(ab_obj.get("status_line", "") or "")
    du.print_stat("Ablation", ab_line or payload.get("ablation_status") or "n/a")

    cohort_line = str(payload.get("cohort_funnel_plain") or "").strip() or _cohort_funnel_line(
        payload,
        inventory_summary,
    )
    du.print_stat("Cohort funnel (high level)", cohort_line)

    model_line = _model_line(inventory_summary, payload)
    if model_line:
        du.print_stat("Main model", model_line)

    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    if counts:
        du.print_stat(
            "Row funnel (four-count + split)",
            "sql_scope={gt}; governed_prepared_cohort={g}; fused_feature_rows={fm}; "
            "aligned_supervised={al}; post_family_support_trainable={pool}; train={tr}; test={te}".format(
                gt=counts.get("cohort_sql_scope_row_count")
                or counts.get("gate_total_candidates")
                or counts.get("raw_candidate_rows"),
                g=counts.get("cohort_prepared_row_count") or counts.get("governed_cohort_rows"),
                fm=counts.get("feature_matrix_rows"),
                al=counts.get("aligned_supervised_rows") or counts.get("aligned_rows"),
                pool=counts.get("post_low_support_training_rows") or counts.get("supervised_training_rows"),
                tr=counts.get("train_rows"),
                te=counts.get("test_rows"),
            ),
        )

    feats = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    if feats.get("pre_prune") is not None or feats.get("post_prune") is not None:
        du.print_stat(
            "Feature columns pre/post prune",
            f"{feats.get('feature_matrix_cols_pre_prune') or feats.get('pre_prune')} → "
            f"{feats.get('feature_matrix_cols_post_prune') or feats.get('post_prune')}",
        )

    hostile_st = payload.get("hostile_audit_status")
    hostile_skip_reason = str(payload.get("hostile_audit_skip_reason", "") or "").strip()
    if hostile_st:
        hostile_line = str(hostile_st)
        if hostile_skip_reason:
            hostile_line = f"{hostile_line} ({hostile_skip_reason})"
        du.print_stat("Hostile audit", hostile_line)

    blockers = payload.get("paper_blockers") or []
    if isinstance(blockers, list) and blockers:
        du.print_stat("Publication blockers", "; ".join(str(x) for x in blockers[:8]))

    rw = payload.get("research_warnings_top") or payload.get("research_warnings") or []
    if isinstance(rw, list) and rw:
        du.print_info("[WARN] Top research/ops warnings:")
        shown = rw[:3]
        for line in shown:
            du.print_info(f"  - {line}")
        if len(rw) > len(shown):
            du.print_info("  - (additional warnings are captured in diagnostics artifacts)")

    du.print_info("[OPEN] Suggested first artifacts:")
    primed = payload.get("top_artifacts_to_open_first")
    primary_hints: list[str] = []
    if isinstance(primed, list):
        primary_hints = [str(x) for x in primed[:8]]
    for hint in _merge_open_hints(
        primary_hints,
        _open_first_hints(evidence_index_path, Path(payload.get("paths", {}).get("logging_audit_md", ""))),
    ):
        du.print_info(f"  - {hint}")


def _cohort_funnel_line(payload: dict[str, Any], inventory_summary: dict[str, Any]) -> str:
    del inventory_summary
    cohort = str(payload.get("cohort_population_warning") or "").strip()
    if cohort:
        return cohort
    # Pull from nested paths if future schema adds them
    return "see diagnostics/cohort_funnel.md and cohort_population_audit.csv"


def _merge_open_hints(primary: list[str], fallback: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for seq in (primary, fallback):
        for h in seq:
            if h and h not in seen:
                seen.add(h)
                out.append(h)
    return out[:8]


def _model_line(inventory_summary: dict[str, Any], payload: dict[str, Any]) -> str:
    del inventory_summary
    ms = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    if not ms:
        inner = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        if inner:
            top = inner.get("top_model", "")
            f1 = inner.get("top_macro_f1", "")
            tn = payload.get("test_sample_count")
            return f"{top} Macro-F1={f1}; test n={tn}" if tn not in (None, "") else f"{top} Macro-F1={f1}"
        return ""
    top = ms.get("top_model", "")
    f1 = ms.get("top_macro_f1", "")
    tn = payload.get("test_sample_count")
    return f"{top} Macro-F1={f1}; test n={tn}" if tn not in (None, "") else f"{top} Macro-F1={f1}"


def _open_first_hints(evidence_index_path: Path | None, logging_audit: Path) -> list[str]:
    hints: list[str] = []
    if evidence_index_path and evidence_index_path.exists():
        hints.append(str(evidence_index_path))
    diag_parent: Path | None = None
    if evidence_index_path:
        cand = evidence_index_path.parent / "diagnostics"
        if cand.is_dir():
            diag_parent = cand
    for name in (
        "cohort_funnel.md",
        "publication_claim_audit.md",
        "paper_claim_audit.md",
        "recommended_findings.md",
        "figure_validity_audit.md",
        "pipeline_stage_summary.md",
    ):
        parent = (evidence_index_path.parent if evidence_index_path else Path("."))
        p = parent / name
        if p.exists():
            hints.append(str(p))
    ros = (diag_parent or Path(".")) / "run_observability_summary.json"
    if ros.exists():
        hints.append(str(ros))
    if logging_audit.exists():
        hints.append(str(logging_audit))
    # De-duplicate preserve order
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:5]


__all__ = ["print_unified_run_health"]
