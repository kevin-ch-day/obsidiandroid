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
    evidence_mode = bool(payload.get("evidence_mode"))
    publication_ready_mode = evidence_mode or bool(payload.get("paper_mode"))
    du.print_stat("Publication-ready mode", "ON" if publication_ready_mode else "OFF")
    du.print_stat("Evidence mode", "ON" if evidence_mode else "OFF")
    publication_ready_status = coalesce_publication_ready_status(payload)
    du.print_stat("publication_ready_status", publication_ready_status)
    publication_ready_reasons = coalesce_publication_ready_reasons(payload)
    if publication_ready_reasons:
        du.print_stat("publication_ready_reasons", ", ".join(str(x) for x in publication_ready_reasons))
    scientific = payload.get("scientific_adequacy") if isinstance(payload.get("scientific_adequacy"), dict) else {}
    scientific_posture = str(scientific.get("posture", "") or "").strip()
    if scientific_posture:
        du.print_stat("Scientific adequacy", scientific_posture)
        blockers = scientific.get("blockers")
        if isinstance(blockers, list) and blockers:
            du.print_stat("Scientific blockers", "; ".join(str(x) for x in blockers[:4]))

    row_auth = payload.get("main_training_row_authority") or payload.get("row_authority")
    du.print_stat("Row authority", row_auth or "n/a")
    if payload.get("label_resolution_enabled") is False:
        du.print_stat("Label resolution", "DISABLED")
        du.print_stat("Type-guard suppressions", "unavailable (label resolution disabled)")
    else:
        if payload.get("label_resolution_enabled") is True:
            du.print_stat("Label resolution", "ENABLED")
        if payload.get("type_guard_family_suppressed_count") is not None:
            du.print_stat(
                "Type-guard suppressions",
                str(payload.get("type_guard_family_suppressed_count")),
            )
    alignment_drop = payload.get("alignment_non_authoritative_family_drop_count")
    alignment_rescue = payload.get("alignment_live_authority_rescue_count")
    if alignment_drop is not None or alignment_rescue is not None:
        du.print_stat(
            "Alignment authority filter",
            f"dropped={alignment_drop or 0}; rescued={alignment_rescue or 0}",
        )
    rescue_top = str(payload.get("alignment_live_authority_rescue_families_top", "") or "").strip()
    if rescue_top:
        du.print_stat("Alignment rescue families", rescue_top)
    dropped_top = str(payload.get("alignment_non_authoritative_family_drops_top", "") or "").strip()
    if dropped_top:
        du.print_stat("Alignment dropped families", dropped_top)
    low_support_fams = payload.get("low_support_family_drop_count")
    low_support_rows = payload.get("low_support_row_drop_count")
    if low_support_fams is not None or low_support_rows is not None:
        du.print_stat(
            "Low-support drops",
            f"rows={low_support_rows or 0}; families={low_support_fams or 0}",
        )
    low_support_top = str(payload.get("low_support_family_drops_top", "") or "").strip()
    if low_support_top:
        du.print_stat("Low-support families", low_support_top)
    temporal_top = str(payload.get("temporal_future_only_family_drops_top", "") or "").strip()
    if temporal_top:
        du.print_stat("Temporal future-only families", temporal_top)
    label_strategy = payload.get("label_strategy") if isinstance(payload.get("label_strategy"), dict) else {}
    if label_strategy:
        du.print_stat("Family target", label_strategy.get("preferred_family_target") or "n/a")
        du.print_stat("Type target", label_strategy.get("preferred_type_target") or "n/a")
        avoid = label_strategy.get("avoid_for_primary_claims")
        if isinstance(avoid, list) and avoid:
            du.print_stat("Avoid primary claims on", ", ".join(str(x) for x in avoid))
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
        du.print_info(f"[WARN] Top research/ops warnings: {_compact_list_line(rw, limit=3)}")

    primed = payload.get("top_artifacts_to_open_first")
    primary_hints: list[str] = []
    if isinstance(primed, list):
        primary_hints = [str(x) for x in primed[:8]]
    open_hints = _merge_open_hints(
        primary_hints,
        _open_first_hints(
            evidence_index_path,
            Path(payload.get("paths", {}).get("logging_audit_md", "")),
            verbose_run_artifacts=bool(payload.get("verbose_run_artifacts", True)),
            research_validity_enabled=bool(payload.get("research_validity_bundle_enabled", True)),
        ),
    )
    if open_hints:
        du.print_info(
            f"[OPEN] Suggested first artifacts: {_compact_list_line(open_hints, limit=4, base=run_root)}"
        )


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


def _compact_list_line(items: list[Any], *, limit: int, base: Path | None = None) -> str:
    values = [_short_display_path(str(item), base=base) for item in items if str(item).strip()]
    if not values:
        return "n/a"
    shown = values[: max(1, int(limit))]
    suffix = ""
    if len(values) > len(shown):
        suffix = f" (+{len(values) - len(shown)} more in diagnostics)"
    return " | ".join(shown) + suffix


def _short_display_path(value: str, *, base: Path | None = None) -> str:
    text = str(value).strip()
    if not text:
        return text
    try:
        path = Path(text)
        if base is not None:
            try:
                return path.resolve().relative_to(base.resolve()).as_posix()
            except Exception:
                pass
        return path.name or text
    except Exception:
        return text


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


def _open_first_hints(
    evidence_index_path: Path | None,
    logging_audit: Path,
    *,
    verbose_run_artifacts: bool,
    research_validity_enabled: bool,
) -> list[str]:
    hints: list[str] = []
    if evidence_index_path and evidence_index_path.exists():
        hints.append(str(evidence_index_path))
    diag_parent: Path | None = None
    if evidence_index_path:
        cand = evidence_index_path.parent / "diagnostics"
        if cand.is_dir():
            diag_parent = cand
    names = ["pipeline_stage_summary.md"]
    if research_validity_enabled:
        names = [
            "cohort_funnel.md",
            "publication_claim_audit.md",
            "paper_claim_audit.md",
            "recommended_findings.md",
            "figure_validity_audit.md",
            *names,
        ]
    for name in names:
        parent = (evidence_index_path.parent if evidence_index_path else Path("."))
        p = parent / name
        if p.exists():
            hints.append(str(p))
    ros = (diag_parent or Path(".")) / "run_observability_summary.json"
    if ros.exists():
        hints.append(str(ros))
    if verbose_run_artifacts and logging_audit.exists():
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
