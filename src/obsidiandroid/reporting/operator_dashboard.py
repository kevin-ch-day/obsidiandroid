"""Curated terminal narrative and diagnostics index for research/operator workflows.

Heavy diagnostic detail belongs in diagnostics artifacts; the terminal focuses on
cohort semantics, modality coverage, model leaderboard context, and claim hygiene.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.common.authority_taxonomy_terms import taxonomy_count_drift_note
from obsidiandroid.common.backlog_semantics import (
    build_backlog_debt_summary,
    build_backlog_markdown_lines,
    build_backlog_terminal_lines,
    build_taxonomy_curation_posture,
    choose_priority_triage,
    read_android_missing_resolution_snapshot,
    read_false_positive_triage_snapshot,
    read_missing_primary_triage_snapshot,
    read_policy_held_token_risk_snapshot,
    read_profile_family_mapping_debt_snapshot,
    read_blank_resolved_triage_snapshot,
)
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.scientific_adequacy import classify_scientific_adequacy
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.reporting.high_score_skeptic_helpers import (
    build_label_map as _build_label_map,
    label_display as _label_display,
)

# Internal experiment keys → human-readable modality descriptions (CSV keeps internal keys).
ABLATION_FEATURE_SET_LABELS: dict[str, str] = {
    "vendor_full": "vendor_parsed_full",
    "vendor_no_parsed_family": "vendor_parsed_no_family",
    "vendor_no_family_no_type": "vendor_parsed_no_family_no_type",
    "vendor_detection_binary_only": "vendor_detection_binary_only",
    "vendor_consensus_scores_only": "vendor_consensus_scores_only",
    "permissions_raw": "permissions_raw",
    "permissions_grouped": "permissions_grouped",
    "permissions_grouped_plus_vendor_no_family": "permissions_grouped_plus_vendor_safe",
    "full_fused": "full_fused",
}


def format_feature_set_label(internal_key: str) -> str:
    return ABLATION_FEATURE_SET_LABELS.get(str(internal_key), str(internal_key))


def _artifact_label(path: Path, *, base: Path | None = None) -> str:
    try:
        if base is not None:
            return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        pass
    return path.name


def _read_run_taxonomy_summary(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Read the run-scoped taxonomy summary, falling back only when needed."""
    candidates = [
        diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json",
        oh.resolve_taxonomy_consistency_summary_path(diagnostics_dir, run_id),
    ]
    for path in candidates:
        payload = read_json_dict(path)
        if isinstance(payload, dict) and payload:
            return payload
    return {}


def _reporting_output_root(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve output root for report-side backlog lookups."""
    try:
        if diagnostics_dir.name == "diagnostics" and diagnostics_dir.parent.name == str(run_id):
            runs_dir = diagnostics_dir.parent.parent
            if runs_dir.name == "runs":
                return runs_dir.parent.resolve()
    except Exception:
        pass
    return canonical_output_root()


def _publication_mode_active(manifest_context: Mapping[str, Any]) -> bool:
    """Resolve evidence/publication mode from manifest_context metadata dicts or bools."""
    from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_evidence_mode

    return coalesce_manifest_evidence_mode(manifest_context.get("evidence_mode")) or coalesce_manifest_evidence_mode(
        manifest_context.get("paper_mode")
    )


def _claim_readiness_context(
    profile_id: str,
    manifest_context: Mapping[str, Any],
    samples_df: pd.DataFrame | None,
) -> tuple[str, str]:
    """Return terminal heading and machine-readable primary surface label."""
    profile = str(profile_id or "").strip()
    publication_active = _publication_mode_active(manifest_context)
    if publication_active:
        return "PUBLICATION CLAIM READINESS", "locked_publication_surface"
    if profile == "android_malware_type_taxonomy":
        return "BENCHMARK CLAIM READINESS", "type_taxonomy_surface"
    if profile == "android_malware_expanded_families":
        return "RESEARCH CLAIM READINESS", "expanded_family_exploratory"
    support_floor_mode = ""
    if isinstance(samples_df, pd.DataFrame):
        support_floor_mode = str(samples_df.attrs.get("support_floor_mode", "") or "").strip().lower()
    if support_floor_mode == "benchmark_eligibility":
        return "BENCHMARK CLAIM READINESS", "major_family_benchmark"
    if profile == "android_malware_all_current":
        return "RESEARCH CLAIM READINESS", "broad_current_corpus"
    return "RESEARCH CLAIM READINESS", "benchmark_surface"


def _dl_seed_readiness_context(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize Neptune/Iapetus seed-chain readiness for operator claim surfaces."""
    from obsidiandroid.diagnostics.v3_dl_handoff import build_v3_dl_handoff_summary_payload

    run_root = diagnostics_dir.parent if diagnostics_dir.name == "diagnostics" else diagnostics_dir
    manifest = read_json_dict(run_root / "run_manifest.json")
    handoff_path = diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json"
    if handoff_path.is_file():
        handoff = read_json_dict(handoff_path)
    else:
        handoff = build_v3_dl_handoff_summary_payload(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile={"profile_id": profile_id},
            manifest=manifest,
            manifest_context=dict(manifest_context),
        )
    return {
        "dl_seed_status": handoff.get("dl_seed_status", "incomplete"),
        "dl_seed_missing_refs": list(handoff.get("missing_seed_refs") or []),
        "dataset_hash": handoff.get("dataset_hash"),
        "cohort_persistence_source": handoff.get("cohort_persistence_source")
        or manifest_context.get("cohort_persistence_source"),
        "ml_vocabulary_entry_count": int(handoff.get("vocabulary_entry_count", 0) or 0),
        "split_hash": handoff.get("split_hash"),
        "split_export_present": bool(handoff.get("split_export_present")),
        "dl_seed_caveats": list(handoff.get("caveats") or []),
    }


def _claim_status_code(
    readiness_heading: str,
    readiness_blockers: Sequence[str],
) -> str:
    """Return compact terminal claim-readiness status."""
    heading = str(readiness_heading or "").strip().lower()
    blockers = [str(item).strip() for item in readiness_blockers if str(item).strip()]
    if heading == "strong":
        return "STRONG_WITH_CAUTIONS" if blockers else "STRONG"
    if heading == "mixed":
        return "MIXED"
    if heading == "weak":
        return "LIMITED"
    return "NOT_ASSESSED"


def _claim_surface_label(*, profile_id: str, readiness_surface: str) -> str:
    """Return concise operator wording for the active claim surface."""
    profile = str(profile_id or "").strip()
    if readiness_surface == "locked_publication_surface":
        return "Locked publication cohort"
    if profile == "android_malware_all_current":
        return "Current-corpus diagnostic surface"
    if profile == "android_malware_major_families":
        return "Support-gated benchmark cohort"
    if profile == "android_malware_expanded_families":
        return "Expanded-family exploratory cohort"
    if profile == "android_malware_type_taxonomy":
        return "Type taxonomy benchmark"
    if readiness_surface == "major_family_benchmark":
        return "Support-gated benchmark cohort"
    return "Benchmark research surface"


def _write_claim_readiness_summary_json(
    *,
    diagnostics_dir: Path,
    run_id: str,
    payload: Mapping[str, Any],
) -> Path:
    path = diagnostics_dir / f"claim_readiness_summary_{run_id}.json"
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _emit_structured_block(lines: Sequence[str], print_fn: Callable[[str], None] | None) -> None:
    """Render a multiline structured terminal block without collapsing it."""
    emitter = print if print_fn is None else print_fn
    for line in lines:
        emitter(str(line))


def _write_backlog_debt_summary_md(
    *,
    diagnostics_dir: Path,
    run_id: str,
    debt_summary: dict[str, Any],
    priority_backlog: dict[str, Any],
) -> Path:
    """Emit a compact run-scoped backlog/debt summary markdown artifact."""
    lines = [f"# Backlog debt summary — `{run_id}`", ""]
    if priority_backlog:
        lines.extend(
            [
                "## Priority backlog",
                "",
                f"- Focus first: **{str(priority_backlog.get('label', '—') or '—')}**",
                f"- Rows: **{int(priority_backlog.get('row_count', 0) or 0)}**",
                f"- Freshness: **{str(priority_backlog.get('freshness', '—') or '—')}**",
            ]
        )
        top_lane = str(priority_backlog.get("top_lane", "") or "").strip()
        if top_lane:
            lines.append(
                f"- Dominant lane: **{top_lane} ({int(priority_backlog.get('top_lane_count', 0) or 0)})**"
            )
        action = str(priority_backlog.get("action", "") or "").strip()
        if action:
            lines.append(f"- Recommended next action: {action}")
        lines.append("")
    lines.extend(
        build_backlog_markdown_lines(
            debt_summary=debt_summary,
            priority_backlog={},
            heading="## Ranked backlog debt",
            ranked_style="table",
            max_rows=len(list(debt_summary.get("rows", []))) if isinstance(debt_summary, dict) else 0,
        )
    )

    path = diagnostics_dir / f"backlog_debt_summary_{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_reporting_backlog_summary(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], Path | None, dict[str, Any]]:
    """Build shared backlog/debt summary for exported/operator report surfaces."""
    try:
        readiness = get_cohort_readiness_snapshot()
    except Exception as exc:
        readiness = {"status": "degraded", "warnings": [f"Cohort readiness unavailable: {exc}"], "buckets": {}}
    out_root = _reporting_output_root(diagnostics_dir=diagnostics_dir, run_id=run_id)
    fp_triage = read_false_positive_triage_snapshot(output_root=out_root)
    android_triage = read_android_missing_resolution_snapshot(output_root=out_root)
    policy_held_triage = read_policy_held_token_risk_snapshot(output_root=out_root)
    missing_primary_triage = read_missing_primary_triage_snapshot(output_root=out_root)
    profile_mapping_debt = read_profile_family_mapping_debt_snapshot(output_root=out_root)
    blank_resolved_triage = read_blank_resolved_triage_snapshot(output_root=out_root)
    debt_summary = build_backlog_debt_summary(
        readiness=readiness,
        fp_triage=fp_triage,
        android_missing_triage=android_triage,
        policy_held_triage=policy_held_triage,
        missing_primary_triage=missing_primary_triage,
        profile_mapping_debt=profile_mapping_debt,
        blank_resolved_triage=blank_resolved_triage,
    )
    if isinstance(debt_summary, dict):
        debt_summary["source_note"] = "live DB current-state view, not frozen run snapshot"
    priority_backlog = choose_priority_triage(
        fp_triage=fp_triage,
        android_missing_triage=android_triage,
        missing_primary_triage=missing_primary_triage,
    )
    if not debt_summary.get("rows") and not priority_backlog:
        return debt_summary, priority_backlog, None, readiness
    md_path = _write_backlog_debt_summary_md(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        debt_summary=debt_summary,
        priority_backlog=priority_backlog,
    )
    return debt_summary, priority_backlog, md_path, readiness


def clear_operator_state() -> None:
    """Reset per-run operator narrative buffers (call at pipeline start)."""
    setattr(app_config, "RUNTIME_OPERATOR_ISSUES", [])
    setattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", {})
    setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "")
    setattr(app_config, "RUNTIME_SMOTE_WARNING_EMITTED", False)
    setattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", None)
    setattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", {})
    setattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", None)


def record_operator_issue(
    *,
    tag: str,
    title: str,
    lines: Sequence[str],
) -> None:
    """Queue a structured issue for the end-of-run ISSUES FOUND block."""
    bucket = getattr(app_config, "RUNTIME_OPERATOR_ISSUES", None)
    if not isinstance(bucket, list):
        bucket = []
    entry = {"tag": str(tag), "title": str(title), "lines": [str(x) for x in lines]}
    bucket.append(entry)
    setattr(app_config, "RUNTIME_OPERATOR_ISSUES", bucket)


def bump_artifact_counter(group: str, n: int = 1) -> None:
    counts = getattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", None)
    if not isinstance(counts, dict):
        counts = {}
    counts[str(group)] = int(counts.get(str(group), 0)) + int(n)
    setattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", counts)


def _queue_runtime_operator_issues(
    *,
    diagnostics_dir: Path,
    manifest_context: Mapping[str, Any],
) -> None:
    """Promote major runtime caveats into the end-of-run operator issue queue."""

    contract = (
        manifest_context.get("paper_cohort_contract")
        if isinstance(manifest_context.get("paper_cohort_contract"), dict)
        else {}
    )
    validation = contract.get("validation") if isinstance(contract.get("validation"), dict) else {}
    sample_id_lock = contract.get("sample_id_lock") if isinstance(contract.get("sample_id_lock"), dict) else {}
    runtime_drift = sample_id_lock.get("runtime_db_drift") if isinstance(sample_id_lock.get("runtime_db_drift"), dict) else {}
    taxonomy_drift = (
        sample_id_lock.get("taxonomy_label_drift")
        if isinstance(sample_id_lock.get("taxonomy_label_drift"), dict)
        else {}
    )
    validation_status = str(validation.get("status", "")).strip().lower()
    if manifest_context.get("label_resolution_enabled") is False:
        record_operator_issue(
            tag="TAXONOMY",
            title="Label resolution stage was disabled",
            lines=[
                "Final structured label resolution did not run, so taxonomy rendering audits and family/type guard telemetry were not exercised for this run.",
                "Treat family-level metrics as model-output-only until `ENABLE_LABEL_RESOLUTION_STAGE=True` for the same cohort/profile.",
            ],
        )
    if validation_status == "degraded_live_db_drift":
        matched = int(runtime_drift.get("matched_sample_count", 0) or 0)
        missing = int(runtime_drift.get("missing_from_db_count", 0) or 0)
        expected = int(runtime_drift.get("lock_sample_count", 0) or 0)
        record_operator_issue(
            tag="COHORT_LOCK",
            title="Locked cohort drift downgraded to count-only semantics",
            lines=[
                f"Preserved lock expected {expected} sample_ids; {matched} matched the live DB and {missing} are now absent.",
                "Publication-ready status passed, but exact historical sample membership is no longer fully recoverable.",
            ],
        )
    elif validation_status == "degraded_taxonomy_label_drift":
        matched = int(taxonomy_drift.get("matched_sample_count", 0) or 0)
        expected_families = int(taxonomy_drift.get("expected_family_count", 0) or 0)
        observed_families = int(taxonomy_drift.get("observed_family_count", 0) or 0)
        expected_types = int(taxonomy_drift.get("expected_type_count", 0) or 0)
        observed_types = int(taxonomy_drift.get("observed_type_count", 0) or 0)
        record_operator_issue(
            tag="COHORT_LOCK",
            title="Locked cohort membership preserved but taxonomy labels drifted",
            lines=[
                f"Preserved sample-id membership matched {matched} locked row(s), but live labels now report families {observed_families} vs expected {expected_families} and types {observed_types} vs expected {expected_types}.",
                taxonomy_count_drift_note(taxonomy_drift),
                "Treat cohort membership as locked, but refresh the lock or reconcile taxonomy curation before comparing family/type counts to the historical contract.",
            ],
        )

    smote_warning = str(getattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "") or "").strip()
    if smote_warning:
        record_operator_issue(
            tag="REPRO",
            title="SMOTE remained enabled in evidence/publication mode",
            lines=[
                smote_warning,
                "Review `smote_effect_check.md` and consider `OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1` for stricter reproducibility.",
            ],
        )

    profile_id = str(getattr(app_config, "RUNTIME_PROFILE_ID", "") or "").strip()
    split_algorithm = str(getattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "") or "").strip()
    if profile_id.startswith("malicious_temporal_") and split_algorithm:
        split_algo_norm = split_algorithm.lower()
        temporal_summary = getattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", None)
        if "temporal" not in split_algo_norm and "year_holdout" not in split_algo_norm:
            record_operator_issue(
                tag="TEMPORAL",
                title="Temporal profile used a non-temporal holdout policy",
                lines=[
                    f"Profile `{profile_id}` executed with split algorithm `{split_algorithm}`.",
                    "Interpret results as random/group holdout evidence, not forward-in-time generalization.",
                ],
            )
        elif isinstance(temporal_summary, dict):
            test_year_floor = int(temporal_summary.get("test_year_floor", 0) or 0)
            dropped_future_only = int(
                temporal_summary.get("test_rows_dropped_unseen_train_classes", 0) or 0
            )
            observed_min = int(temporal_summary.get("observed_year_min", 0) or 0)
            observed_max = int(temporal_summary.get("observed_year_max", 0) or 0)
            if dropped_future_only > 0:
                record_operator_issue(
                    tag="TEMPORAL",
                    title="Temporal holdout excluded future-only family rows",
                    lines=[
                        f"Split algorithm `{split_algorithm}` used train years < {test_year_floor} and test years >= {test_year_floor}.",
                        f"Dropped {dropped_future_only} newer-row sample(s) because their class never appeared in the historical training years "
                        f"(observed year span {observed_min}–{observed_max}).",
                    ],
                )

    run_id = str(manifest_context.get("run_id", "") or "").strip()
    taxonomy = _read_run_taxonomy_summary(diagnostics_dir, run_id)
    if taxonomy:
        total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0)
        paper_facing = int(taxonomy.get("paper_facing_taxonomy_mismatch_count", total) or 0)
        type_guard_suppressed = int(taxonomy.get("type_guard_family_suppressed_count", 0) or 0)
        if total > 0:
            counts = taxonomy.get("mismatch_reason_counts")
            top_bits: list[str] = []
            if isinstance(counts, list):
                for row in counts[:3]:
                    if not isinstance(row, dict):
                        continue
                    reason = str(row.get("mismatch_reason", "") or "").strip()
                    count = int(row.get("count", 0) or 0)
                    if reason and count > 0:
                        top_bits.append(f"{reason}={count}")
            detail = ", ".join(top_bits) if top_bits else "see taxonomy_consistency_mismatches CSV"
            record_operator_issue(
                tag="TAXONOMY",
                title="Taxonomy split issues present",
                lines=[
                    f"Taxonomy mismatches: total={total}; claim-facing={paper_facing}.",
                    f"Top mismatch buckets: {detail}.",
                    "Use taxonomy_authority_split to separate authority gaps, policy-held generic/coarse token residue, unknown-type families, rendering mismatches, and real model prediction errors.",
                ],
            )
        if type_guard_suppressed > 0:
            record_operator_issue(
                tag="TAXONOMY",
                title="Type guard suppressed cross-type family predictions",
                lines=[
                    f"Structured label resolution demoted {type_guard_suppressed} known-family prediction(s) because they conflicted with authoritative sample type lineage.",
                    "Review `taxonomy_consistency_summary_*.json`, `prediction_errors_*.csv`, and taxonomy consistency review diagnostics to confirm the guard is reducing false family attribution rather than masking label debt.",
                ],
            )
    try:
        readiness = get_cohort_readiness_snapshot()
    except Exception:
        readiness = {}
    taxonomy_signals = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    if isinstance(taxonomy_signals, dict):
        curation_note = str(build_taxonomy_curation_posture(readiness=readiness).get("note", "") or "").strip()
        if curation_note:
            record_operator_issue(
                tag="TAXONOMY",
                title="Family taxonomy curation discipline required",
                lines=[
                    curation_note,
                    "Prioritize DB type mapping, family mapping, and unknown-type cleanup before treating family taxonomy as stable.",
                ],
            )


def _safe_pct(num: float, den: float) -> str:
    if den <= 0:
        return "n/a"
    return f"{100.0 * float(num) / float(den):.1f}%"


def resolve_feature_column_survival_path(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve feature-column survival CSV after run-local `.latest` suppression cleanup."""
    return oh.resolve_feature_column_survival_path(diagnostics_dir, run_id)


def _perm_top_from_survival(surv_path: Path, *, prefix: str, top_n: int = 8) -> list[tuple[str, int]]:
    if not surv_path.is_file():
        return []
    try:
        df = pd.read_csv(surv_path)
    except Exception:
        return []
    if "feature_name" not in df.columns or "nonzero_count_final_training" not in df.columns:
        return []
    sub = df[df["feature_name"].astype(str).str.startswith(prefix)].copy()
    if sub.empty:
        return []
    sub["nz"] = pd.to_numeric(sub["nonzero_count_final_training"], errors="coerce").fillna(0).astype(int)
    sub = sub.sort_values("nz", ascending=False).head(top_n)
    return [(str(r["feature_name"]), int(r["nz"])) for _, r in sub.iterrows()]


def _rf_perm_importance_top(model_results: dict[str, Any], *, top_n: int = 8) -> list[tuple[str, float]]:
    rf = model_results.get("random_forest") if isinstance(model_results, dict) else None
    if not isinstance(rf, dict):
        return []
    named = rf.get("metadata", {}).get("feature_importances_named")
    if not isinstance(named, list):
        return []
    rows: list[tuple[str, float]] = []
    for item in named:
        if not isinstance(item, dict):
            continue
        name = str(item.get("feature_name") or "")
        imp = item.get("importance")
        if imp is None:
            continue
        try:
            imp_f = float(imp)
        except (TypeError, ValueError):
            continue
        if name.startswith(("perm__", "perm_grp__")):
            rows.append((name, imp_f))
    rows.sort(key=lambda x: -x[1])
    return rows[:top_n]


def _claim_readiness_posture(
    *,
    bundle: dict[str, Any],
    runtime_temporal_summary: Mapping[str, Any] | None,
) -> tuple[str, list[str]]:
    """Classify claim-readiness strength for the terminal summary."""
    q1 = bundle.get("q1") if isinstance(bundle.get("q1"), dict) else {}
    supervised_ok = bool(q1.get("supervised_family_claims_suitable", False))
    temporal_summary = runtime_temporal_summary if isinstance(runtime_temporal_summary, Mapping) else {}
    dropped_future_only = int(temporal_summary.get("test_rows_dropped_unseen_train_classes", 0) or 0)
    return classify_scientific_adequacy(
        macro_f1=bundle.get("macro_f1"),
        supervised_family_claims_suitable=supervised_ok,
        dropped_future_only_rows=dropped_future_only,
    )


def _classification_report_family_insights(model_results: dict[str, Any], model_key: str) -> dict[str, Any]:
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    if not isinstance(res, dict):
        return {}
    creport = res.get("metadata", {}).get("classification_report")
    if not isinstance(creport, dict):
        return {}
    diagnostics_dir = Path(
        str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "")
        or str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))
    )
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    label_map = _build_label_map(model_results, model_key, diagnostics_dir, run_id)
    per_class: list[tuple[str, float, float, float, int]] = []
    for label, stats in creport.items():
        if not isinstance(stats, dict):
            continue
        if label in {"accuracy", "macro avg", "weighted avg"}:
            continue
        try:
            p = float(stats.get("precision", 0))
            r = float(stats.get("recall", 0))
            f1 = float(stats.get("f1-score", 0))
            sup = int(float(stats.get("support", 0)))
        except (TypeError, ValueError):
            continue
        per_class.append((_label_display(label, label_map), p, r, f1, sup))
    if not per_class:
        return {}
    lowest_recall = sorted(per_class, key=lambda x: x[2])[:5]
    lowest_prec = sorted(per_class, key=lambda x: x[1])[:5]
    macro_gap_candidates = sorted(per_class, key=lambda x: (x[3] - x[2]))[:5]
    return {
        "lowest_recall": lowest_recall,
        "lowest_precision": lowest_prec,
        "largest_macro_vs_f1_gap": macro_gap_candidates,
    }


def top_confusion_pairs_for_model(
    model_results: dict[str, Any],
    model_key: str,
    *,
    top_n: int = 5,
) -> list[tuple[str, str, int]]:
    """Public wrapper for holdout confusion off-diagonal pairs (true, pred, count)."""
    return _top_confusion_pairs(model_results, model_key, top_n=top_n)


def _top_confusion_pairs(
    model_results: dict[str, Any],
    model_key: str,
    *,
    top_n: int = 5,
) -> list[tuple[str, str, int]]:
    """Largest off-diagonal confusion counts from the holdout confusion matrix (cheap science cue)."""
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    if not isinstance(res, dict):
        return []
    ev = res.get("evaluation", {})
    if not isinstance(ev, dict):
        return []
    cm = ev.get("confusion_matrix")
    labels = ev.get("class_labels") or ev.get("decoded_labels")
    if cm is None or not labels:
        return []
    arr = np.asarray(cm)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        return []
    lab_list = [str(x) for x in labels]
    n = arr.shape[0]
    triples: list[tuple[int, int, int]] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            triples.append((i, j, int(arr[i, j])))
    triples.sort(key=lambda t: -t[2])
    out: list[tuple[str, str, int]] = []
    for i, j, c in triples[: max(1, int(top_n))]:
        li = lab_list[i] if i < len(lab_list) else str(i)
        lj = lab_list[j] if j < len(lab_list) else str(j)
        out.append((li, lj, c))
    return out


def _read_model_comparison_leaderboard(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Return sorted rows by Macro F1 descending and best internal model key."""
    if not path.is_file():
        return [], ""
    try:
        df = pd.read_csv(path)
    except Exception:
        return [], ""
    if df.empty or "Macro F1-Score" not in df.columns:
        cols = [c for c in df.columns if str(c).lower().replace("-", "").replace("_", "") == "macrof1score"]
        metric_col = cols[0] if cols else None
    else:
        metric_col = "Macro F1-Score"
    if metric_col is None or "Model" not in df.columns:
        return [], ""
    work = df.copy()
    work["_m"] = pd.to_numeric(work[metric_col], errors="coerce")
    work = work.dropna(subset=["_m"]).sort_values("_m", ascending=False)
    rows_out = []
    for _, row in work.iterrows():
        rows_out.append(dict(row.drop(labels=["_m"])))
    best = ""
    try:
        best = str(work.iloc[0]["Model"]).strip().lower().replace(" ", "_")
    except Exception:
        best = ""
    return rows_out, best


def write_diagnostics_index_md(
    diagnostics_dir: Path,
    *,
    run_id: str,
    artifact_list: Sequence[str],
) -> Path | None:
    """Emit ``diagnostics/index.md`` with standard sections + artifact map excerpt."""
    if not diagnostics_dir.exists():
        return None
    verbose_run_artifacts = bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))
    rel = diagnostics_dir.resolve()
    lines: list[str] = []
    lines.append(f"# Diagnostics index — `{run_id}`")
    lines.append("")
    lines.append(f"Root: `{rel}`")
    lines.append("")
    lines.append("## Run overview")
    lines.append("")
    lines.append("| Artifact | Purpose |")
    lines.append("| --- | --- |")
    staples = [
        ("dataset_foundation_summary", "Q1 dataset validity (cohort, concentration, gates)."),
        ("modality_contribution_summary", "Q2 modality coverage + ablation pointers."),
        ("model_and_family_failure_summary", "Q3 headline metrics, confusion, type vs family."),
        ("backlog_debt_summary_", "Shared operator backlog/debt ledger for this run."),
        ("run_health_summary_", "High-level cohort/model health snapshot (JSON)."),
        ("model_comparison_summary_", "Model leaderboard CSV for this run."),
        ("experiment_registry_", "Experiment registry wiring + profile context."),
        ("cohort_foundation", "Structured cohort demographics + funnel narrative."),
        ("feature_contract", "Frozen training feature-column contract."),
        ("leakage_assessment.txt", "Leakage posture / modality coupling summary."),
        ("modality_method_contract.json", "Per-modality method + fusion accounting."),
        ("feature_column_survival", "Feature survival through pruning gates."),
        ("ablation_summary_", "Methodology grid (when enabled)."),
        ("pipeline_stage_summary.csv", "Stage timings + throughput."),
        ("split_freeze_headline_", "Headline train/test membership ledger."),
    ]
    for prefix, purpose in staples:
        lines.append(f"| `{prefix}*` | {purpose} |")
    lines.append("")
    sections = [
        ("Cohort and label distribution", ["cohort_foundation", "analysis_snapshot", "family_distribution"]),
        ("Dataset concentration", ["cohort_foundation", "family_distribution_report"]),
        (
            "Backlog and review queues",
            [
                "backlog_debt_summary",
                "android_missing_resolution_triage",
                "vt_false_positive_review_triage",
                "android_policy_held_token_risk",
            ],
        ),
        ("Modality coverage", ["feature_modality_coverage", "feature_build_coverage", "permission_fuse_audit"]),
        ("Feature contracts", ["feature_contract", "feature_column_survival"]),
        ("Leakage assessment", ["leakage_assessment", "leakage_pruning_audit"]),
        ("Model comparison", ["model_comparison_summary", "model_config_snapshot"]),
        ("Ablation summary", ["ablation_summary", "ablation_per_family", "ablation_feature_schema_audit"]),
        ("Contract / taxonomy authority", ["headline_vs_ablation_contract_comparison", "taxonomy_type_authority_review"]),
        ("Permission diagnostics", ["permission_training_survival", "permission_fuse_audit"]),
        ("Vendor/parser diagnostics", ["parser_quality", "vendor_parser"]),
        ("Sample lineage", ["sample_stage_lineage", "feature_matrix_lineage_gate"]),
        ("Predictions / errors", ["headline_test_predictions", "headline_test_errors"]),
        ("Taxonomy", ["taxonomy_consistency", "taxonomy_authority"]),
    ]
    listing = sorted(p.name for p in diagnostics_dir.iterdir() if p.is_file())
    for sec_title, keys in sections:
        lines.append(f"## {sec_title}")
        lines.append("")
        hits: list[str] = []
        for n in listing:
            if not any(k.lower() in n.lower() for k in keys):
                continue
            if str(run_id) in n or "latest." in n:
                hits.append(n)
        uniq = sorted(set(hits))[:42]
        for name in uniq:
            lines.append(f"- `{name}`")
        if not uniq:
            lines.append("(no matching files)")
        lines.append("")
    lines.append("## Artifact map (this run enumeration)")
    lines.append("")
    referenced_artifacts = {
        Path(str(path)).name
        for path in artifact_list
        if str(path).strip()
    }
    art = sorted(
        {
            name
            for name in listing
            if verbose_run_artifacts or ".latest." not in name
        }
        | {
            name
            for name in referenced_artifacts
            if verbose_run_artifacts or ".latest." not in name
        }
    )
    for chunk in art[:120]:
        lines.append(f"- `{chunk}`")
    if len(art) > 120:
        lines.append(f"- … `{len(art) - 120}` additional paths omitted")
    lines.append("")
    out_path = diagnostics_dir / "index.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def emit_research_operator_report(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest_context: Mapping[str, Any],
    samples_df: pd.DataFrame | None,
    model_results: dict[str, Any] | None,
    top_model: str | None,
    artifact_list: list[str],
    print_fn: Callable[[str], None] | None = None,
) -> None:
    """End-of-run operator dashboard: markdown index + TERMINAL blocks."""
    from obsidiandroid.cli.ui import display as du
    from obsidiandroid.diagnostics.contract_and_taxonomy_reports import (
        write_headline_vs_ablation_contract_reports,
        write_taxonomy_authority_split_reports,
        write_taxonomy_type_authority_reports,
    )
    from obsidiandroid.diagnostics.data_problem_quantification import (
        write_data_problem_quantification,
    )
    from obsidiandroid.diagnostics.ml_tuning_recommendations import (
        write_ml_tuning_recommendations,
    )
    from obsidiandroid.reporting import research_three_questions as research_rq

    pr = print_fn or (lambda s: du.print_info(s))

    try:
        _cm, _cc, parity = write_headline_vs_ablation_contract_reports(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=dict(manifest_context),
            runtime_headline_hash=str(
                getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
            ).strip()
            or None,
        )
        for p in (_cm, _cc):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
        _tm, _tc = write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
        _tsm, _tsj, _tsr, _tsp, _tsg = write_taxonomy_authority_split_reports(diagnostics_dir, run_id)
        for p in (_tm, _tc, _tsm, _tsj, _tsr, _tsp, _tsg):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
    except Exception:
        parity = {}

    bundle = research_rq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=profile_id,
        manifest_context=dict(manifest_context),
        samples_df=samples_df,
        model_results=model_results or {},
        top_model=top_model,
    )
    _queue_runtime_operator_issues(
        diagnostics_dir=diagnostics_dir,
        manifest_context={
            **dict(manifest_context),
            "run_id": run_id,
        },
    )
    backlog_debt_summary, priority_backlog, backlog_md_path, _readiness_snapshot = _build_reporting_backlog_summary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    if backlog_md_path is not None and str(backlog_md_path) not in artifact_list:
        artifact_list.append(str(backlog_md_path))
    ml_tuning_payload: dict[str, Any] = {}
    try:
        ml_md, ml_csv, ml_json, ml_tuning_payload = write_ml_tuning_recommendations(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
        )
        for p in (ml_md, ml_csv, ml_json):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
    except Exception as exc:
        ml_tuning_payload = {
            "recommendations": [
                {
                    "priority": "low",
                    "area": "ml_tuning_artifact",
                    "finding": f"ML tuning recommendation artifact was skipped: {exc}",
                    "recommended_action": "Inspect ablation and model diagnostics manually.",
                    "evidence": "artifact_writer_exception",
                }
            ]
        }
    data_problem_payload: dict[str, Any] = {}
    try:
        dp_md, dp_csv, dp_json, data_problem_payload = write_data_problem_quantification(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
        )
        for p in (dp_md, dp_csv, dp_json):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
    except Exception:
        data_problem_payload = {}
    extra_paths = bundle.get("_written_paths") or []
    combined_artifacts = list(artifact_list) + [p for p in extra_paths if p not in set(artifact_list)]

    md_path = write_diagnostics_index_md(
        diagnostics_dir, run_id=run_id, artifact_list=combined_artifacts
    )
    pr("")
    pr(f"Run ID: {run_id}  |  Profile: {profile_id}")
    pr("")
    research_rq.print_research_questions_terminal(bundle, pr=(print_fn or print), du=du)
    q1 = bundle.get("q1") if isinstance(bundle.get("q1"), dict) else {}
    label_strategy = q1.get("label_strategy") if isinstance(q1.get("label_strategy"), dict) else {}

    if parity:
        du.print_section("FEATURE CONTRACT COMPARISON (headline vs ablation full_fused)")
        pr(f"  headline_feature_column_hash    : {parity.get('headline_feature_column_hash') or '—'}")
        pr(f"  ablation_full_fused_feature_hash: {parity.get('ablation_full_fused_feature_column_hash') or '—'}")
        pr(f"  split_hash                       : {parity.get('split_hash') or '—'}")
        pr(f"  label_target                     : {parity.get('label_target') or '—'}")
        pr(
            "  headline_extra_modalities        : "
            f"{parity.get('headline_extra_non_vendor_permission_feature_count') or 0}"
        )
        am = parity.get("apples_to_apples")
        pr(f"  apples_to_apples                 : {'yes' if am is True else 'no' if am is False else 'unknown'}")
        if am is False:
            pr(f"  → {parity.get('incommensurable_message', '')}")
        pr(
            f"  Files: `{diagnostics_dir / f'headline_vs_ablation_contract_comparison_{run_id}.md'}`"
        )
        pr("")

    du.print_section("TAXONOMY AUTHORITY (type ground truth)")
    pr("  Cohort type_slug is authoritative for type-level reporting; label-derived type is a parser artifact.")
    taxonomy_summary = _read_run_taxonomy_summary(diagnostics_dir, run_id)
    if isinstance(taxonomy_summary, dict):
        type_guard_suppressed = int(taxonomy_summary.get("type_guard_family_suppressed_count", 0) or 0)
        if type_guard_suppressed > 0:
            pr(
                "  Type-guard suppressions: "
                f"{type_guard_suppressed} structured family prediction(s) were demoted for cross-type incompatibility."
            )
        elif manifest_context.get("label_resolution_enabled") is False:
            pr(
                "  Type-guard suppressions: unavailable for this run because structured label resolution was disabled."
            )
    pr(
        f"  Review: `{diagnostics_dir / f'taxonomy_type_authority_review_{run_id}.md'}` "
        f"and `taxonomy_type_authority_review_{run_id}.csv`"
    )
    pr(
        f"  Taxonomy authority split: `{diagnostics_dir / f'taxonomy_authority_split_{run_id}.md'}`"
    )
    pr("")

    surv = resolve_feature_column_survival_path(diagnostics_dir=diagnostics_dir, run_id=run_id)
    raw_pop = _perm_top_from_survival(surv, prefix="perm__android_", top_n=5)
    rf_perm = _rf_perm_importance_top(model_results or {}, top_n=5)
    if raw_pop or rf_perm:
        du.print_subheader("Permission feature survival / RF hints (see diagnostics for full detail)")
        if raw_pop:
            pr("  Top permission columns by training nonzero: " + ", ".join(f"{n}({z})" for n, z in raw_pop))
        if rf_perm:
            pr(
                "  RF top permission-ish importances: "
                + ", ".join(f"{n}={score:.4f}" for n, score in rf_perm)
            )
        pr("")

    data_problem_flags = (
        data_problem_payload.get("issue_flags") if isinstance(data_problem_payload, dict) else []
    )
    if isinstance(data_problem_flags, list) and data_problem_flags:
        du.print_section("DATA PROBLEM QUANTIFICATION")
        priority = (
            data_problem_payload.get("priority_score")
            if isinstance(data_problem_payload.get("priority_score"), dict)
            else {}
        )
        support_gap = (
            data_problem_payload.get("support_gap")
            if isinstance(data_problem_payload.get("support_gap"), dict)
            else {}
        )
        pred_errors = (
            data_problem_payload.get("prediction_errors")
            if isinstance(data_problem_payload.get("prediction_errors"), dict)
            else {}
        )
        support_curve = (
            data_problem_payload.get("support_threshold_curve")
            if isinstance(data_problem_payload.get("support_threshold_curve"), dict)
            else {}
        )
        training_policy = (
            data_problem_payload.get("training_policy_recommendations")
            if isinstance(data_problem_payload.get("training_policy_recommendations"), dict)
            else {}
        )
        pr(
            "  Composite problem score: "
            f"{priority.get('composite_problem_score_0_100', 'n/a')} / 100"
        )
        if support_gap:
            pr(
                "  Support-gap ROI: "
                f"{support_gap.get('families_with_gap_le_5', 0)} family/families within <=5 "
                f"sample(s) of trainability; all-tail closure needs "
                f"{support_gap.get('samples_needed_to_make_all_families_trainable', 0)} sample(s)."
            )
        threshold_20 = (
            support_curve.get("threshold_20")
            if isinstance(support_curve.get("threshold_20"), dict)
            else {}
        )
        exploratory = (
            support_curve.get("recommended_exploratory_threshold")
            if isinstance(support_curve.get("recommended_exploratory_threshold"), dict)
            else {}
        )
        if threshold_20:
            pr(
                "  Conservative support track: "
                f"threshold={threshold_20.get('threshold', 20)} "
                f"classes={threshold_20.get('trainable_classes', 0)} "
                f"retained={threshold_20.get('retained_rows', 0)} "
                f"dropped={threshold_20.get('dropped_rows', 0)}."
            )
        if exploratory:
            pr(
                "  Exploratory expanded-class track: "
                f"threshold={exploratory.get('threshold', '')} "
                f"classes={exploratory.get('trainable_classes', 0)} "
                f"retained={exploratory.get('retained_rows', 0)} "
                f"dropped={exploratory.get('dropped_rows', 0)} "
                "(separate from evidence headline)."
            )
        tracks = training_policy.get("tracks") if isinstance(training_policy.get("tracks"), list) else []
        if tracks:
            for track in tracks[:3]:
                if not isinstance(track, dict):
                    continue
                action = str(track.get("recommended_action", "") or "").strip()
                if action:
                    pr(f"  Training policy `{track.get('track', '')}`: {action}")
        if pred_errors:
            top_pair = pred_errors.get("top_error_pair") if isinstance(pred_errors.get("top_error_pair"), dict) else {}
            if top_pair:
                pr(
                    "  Top error pair: "
                    f"{top_pair.get('expected_family', '')} -> {top_pair.get('predicted_family', '')} "
                    f"n={top_pair.get('count', 0)}"
                )
        for row in data_problem_flags[:6]:
            if not isinstance(row, dict):
                continue
            pr(
                f"  [{str(row.get('severity', 'note')).upper()}] "
                f"{row.get('issue', '')}: value={row.get('value', '')} "
                f"threshold={row.get('threshold', '')}"
            )
            action = str(row.get("recommended_action", "") or "").strip()
            if action:
                pr(f"      Action: {action}")
        pr(f"  File: `{diagnostics_dir / f'data_problem_quantification_{run_id}.md'}`")
        pr("")

    recs = ml_tuning_payload.get("recommendations") if isinstance(ml_tuning_payload, dict) else []
    if isinstance(recs, list) and recs:
        du.print_section("ML TUNING RECOMMENDATIONS")
        for row in recs[:5]:
            if not isinstance(row, dict):
                continue
            pr(f"  [{str(row.get('priority', 'note')).upper()}] {row.get('area', '')}: {row.get('finding', '')}")
            action = str(row.get("recommended_action", "") or "").strip()
            if action:
                pr(f"      Action: {action}")
        pr(f"  File: `{diagnostics_dir / f'ml_tuning_recommendations_{run_id}.md'}`")
        pr("")

    du.print_section("ISSUES FOUND")
    issues = getattr(app_config, "RUNTIME_OPERATOR_ISSUES", []) or []
    if not isinstance(issues, list) or not issues:
        pr("(No structured governance issues queued — tail risks may still exist; see diagnostics.)")
    else:
        dedup_seen: set[str] = set()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            key = issue.get("title", "") + "|" + "".join(str(x) for x in issue.get("lines") or ())
            if key in dedup_seen:
                continue
            dedup_seen.add(key)
            tag = issue.get("tag", "NOTE")
            pr(f"[{tag}] {issue.get('title', '')}")
            for ln in issue.get("lines") or []:
                pr(f"    {ln}")
            pr("")
    if isinstance(backlog_debt_summary, dict) and backlog_debt_summary.get("rows"):
        du.print_section("BACKLOG DEBT")
        for line in build_backlog_terminal_lines(
            debt_summary=backlog_debt_summary,
            priority_backlog=priority_backlog if isinstance(priority_backlog, dict) else {},
            backlog_path=backlog_md_path,
            max_rows=5,
        ):
            pr(f"  {line}")
        pr("")
    readiness_title, readiness_surface = _claim_readiness_context(
        profile_id=str(profile_id or ""),
        manifest_context=manifest_context if isinstance(manifest_context, Mapping) else {},
        samples_df=samples_df,
    )
    du.print_section(readiness_title)

    active_cls = ""
    mc_la = manifest_context.get("label_authority") if isinstance(manifest_context, dict) else None
    if isinstance(mc_la, dict) and mc_la.get("active_training_classes") is not None:
        active_cls = str(mc_la.get("active_training_classes"))
    benchmark_support_floor = int(bundle.get("benchmark_support_floor", 0) or 0)
    benchmark_support_excluded_sample_count = int(bundle.get("benchmark_support_excluded_sample_count", 0) or 0)
    benchmark_support_excluded_family_count = int(bundle.get("benchmark_support_excluded_family_count", 0) or 0)
    family_target = str(label_strategy.get("preferred_family_target", "") or "").strip()
    type_target = str(label_strategy.get("preferred_type_target", "") or "").strip()
    visible_family_count = q1.get("families_represented")

    lines_strong = []
    caution = [
        "Do not generalize benchmark-surface results to every Android malware family in the broad corpus.",
        "Lead with Macro-F1, balanced accuracy, per-family recall, and top confusion pairs.",
        "Treat raw vendor-parsed labels as audit evidence, not primary scientific targets.",
        "Compare headline and ablation metrics only when the sample universe and feature contract match.",
    ]
    unsupported = [
        "Broad claims about every Android malware family in the full corpus.",
        "Runtime behavior or ATT&CK technique confirmation without runtime evidence.",
        "Benign-app comparison claims.",
        "Deep-learning or inference-mode claims.",
    ]
    if readiness_surface == "major_family_benchmark":
        lines_strong.append("Family classification can be reported on the support-gated benchmark surface.")
    elif readiness_surface == "broad_current_corpus":
        lines_strong.append("This run describes current governed Android malware corpus health.")
        lines_strong.append("Family/type models are diagnostic because the current corpus is concentration-heavy.")
        lines_strong.append("Use benchmark profiles for stronger family-classification claims.")
        caution.append(
            "Treat current-corpus results as diagnostic/research evidence, not as a benchmark-quality family leaderboard across the full long-tail family surface."
        )
    elif readiness_surface == "locked_publication_surface":
        lines_strong.append("Family classification can be reported on the locked publication/evidence cohort.")
        unsupported = [
            "Claims outside the locked cohort and frozen split.",
            "Runtime behavior or ATT&CK technique confirmation without runtime evidence.",
            "Benign-app comparison claims.",
            "Deep-learning or inference-mode claims.",
        ]
    elif readiness_surface == "type_taxonomy_surface":
        lines_strong.append("Type-level claims use `type_slug` as the authoritative target.")
        lines_strong.append("Type-level patterns may be stronger and more stable than family-level patterns on this surface.")
        unsupported = [
            "Locked publication claims unless a locked evidence profile is used.",
            "Runtime behavior or ATT&CK technique confirmation without runtime evidence.",
            "Benign-app comparison claims.",
            "Deep-learning or inference-mode claims.",
        ]
    else:
        if str(profile_id or "").strip() == "android_malware_expanded_families":
            lines_strong.append("Expanded family results include major and minor families and require stronger caveats.")
            lines_strong.append("Do not compare directly against locked publication cohorts unless the sample universe matches.")
        else:
            lines_strong.append("Family classification can be reported on the active governed research surface.")
        caution.append("Treat permission-to-behavior or ATT&CK statements as hypotheses unless runtime evidence exists.")
    lines_strong.append(
        "Permission features are available as a first-class capability-analysis layer; strength should be interpreted from the permission-pattern and ablation reports."
    )
    if label_strategy:
        avoid = label_strategy.get("avoid_for_primary_claims", [])
        if family_target and type_target:
            lines_strong.append(
                f"Family/type targets are governed: `{family_target}` for family claims, `{type_target}` for type claims."
            )
        if isinstance(avoid, list) and avoid:
            caution.append(
                "Do not promote raw label surfaces such as "
                + ", ".join(f"`{str(item)}`" for item in avoid)
                + " into primary scientific claim targets."
            )
    nxt = [
        "Review lowest-recall families and top confusion pairs.",
        "Compare permission-only, vendor-safe, and fused feature performance.",
        "Review permission-pattern reports by type_slug, family, and family-within-type.",
    ]
    dl_seed = _dl_seed_readiness_context(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=str(profile_id or ""),
        manifest_context=manifest_context,
    )
    readiness_heading, readiness_blockers = _claim_readiness_posture(
        bundle=bundle,
        runtime_temporal_summary=getattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", None),
    )
    from obsidiandroid.common.run_slots import is_canonical_v3_profile

    if is_canonical_v3_profile(str(profile_id or "")) and dl_seed.get("dl_seed_status") != "ready":
        readiness_blockers = list(readiness_blockers)
        readiness_blockers.append("DL seed handoff incomplete for canonical V3 profile")
    claim_status = _claim_status_code(readiness_heading, readiness_blockers)
    primary_surface_label = _claim_surface_label(
        profile_id=str(profile_id or ""),
        readiness_surface=readiness_surface,
    )
    eligible_family_classes = int(active_cls) if str(active_cls).isdigit() else None
    visible_family_classes = int(visible_family_count) if str(visible_family_count).isdigit() else None
    modeled_family_classes = None
    if readiness_surface == "broad_current_corpus" and visible_family_classes is not None:
        modeled_family_classes = visible_family_classes
    excluded_family_classes = None
    if visible_family_classes is not None and eligible_family_classes is not None:
        excluded_family_classes = max(0, visible_family_classes - eligible_family_classes)
    details_name = (
        "publication_claim_audit.md"
        if readiness_surface == "locked_publication_surface"
        else "benchmark_claim_audit.md"
        if readiness_surface in {"major_family_benchmark", "type_taxonomy_surface"}
        else "research_claim_audit.md"
    )

    block_lines = [
        "",
        f"Claim status                    : {claim_status}",
        f"Claim surface                   : {primary_surface_label}",
        f"DL seed handoff                 : {dl_seed.get('dl_seed_status', 'unknown')}",
    ]
    if dl_seed.get("dataset_hash"):
        block_lines.append(f"Dataset hash                    : {dl_seed.get('dataset_hash')}")
    if dl_seed.get("cohort_persistence_source"):
        block_lines.append(
            f"Cohort persistence source       : {dl_seed.get('cohort_persistence_source')}"
        )
    if dl_seed.get("split_hash"):
        split_ready = "present" if dl_seed.get("split_export_present") else "missing"
        block_lines.append(f"Split export ({dl_seed.get('split_hash')}) : {split_ready}")
    if dl_seed.get("ml_vocabulary_entry_count"):
        block_lines.append(
            f"ML permission vocabulary        : {dl_seed.get('ml_vocabulary_entry_count')} entries"
        )
    if dl_seed.get("dl_seed_missing_refs"):
        block_lines.append(
            "DL seed missing refs            : "
            + ", ".join(str(item) for item in dl_seed.get("dl_seed_missing_refs", []))
        )
    dl_seed_caveats = dl_seed.get("dl_seed_caveats") or []
    if dl_seed_caveats:
        block_lines.append(
            "DL seed caveats                 : " + "; ".join(str(item) for item in dl_seed_caveats[:3])
        )
    if eligible_family_classes is not None:
        block_lines.append(
            f"Claim-eligible family classes   : {eligible_family_classes}"
        )
    if visible_family_classes is not None:
        block_lines.append(
            f"Visible governed families       : {visible_family_classes}"
        )
    if modeled_family_classes is not None:
        block_lines.append(
            f"Modeled family classes          : {modeled_family_classes}"
        )
    if excluded_family_classes not in (None, 0):
        block_lines.append(
            f"Excluded / non-claim families   : {excluded_family_classes}"
        )
        block_lines.append(
            "Note                            : Difference reflects excluded or non-claim family buckets, such as `unknown`."
        )
    if family_target:
        block_lines.append(f"Primary family target           : {family_target}")
    if type_target:
        block_lines.append(f"Primary type target             : {type_target}")
    if benchmark_support_floor > 0:
        block_lines.append(
            f"Benchmark support rule          : n >= {benchmark_support_floor} per family"
        )

    block_lines.extend(
        [
            "",
            "SUPPORTED CLAIMS",
            "----------------",
            *[f"✓ {item}" for item in lines_strong],
            "",
            "CLAIM LIMITS",
            "------------",
            *[f"! {item}" for item in caution[:4]],
        ]
    )
    if readiness_blockers:
        block_lines.extend(f"! {blocker}." for blocker in readiness_blockers[:3])
    block_lines.extend(
        [
            "",
            "NOT SUPPORTED BY THIS RUN",
            "-------------------------",
            *[f"× {item}" for item in unsupported[:4]],
            "",
            "NEXT REVIEW",
            "-----------",
            *[f"→ {item}" for item in nxt],
            "",
            f"Details                         : diagnostics/{details_name}",
        ]
    )
    _emit_structured_block(block_lines, print_fn)
    claim_readiness_payload = {
        "claim_status": claim_status,
        "claim_surface": primary_surface_label,
        "primary_surface": readiness_surface,
        "dl_seed_status": dl_seed.get("dl_seed_status"),
        "dl_seed_missing_refs": dl_seed.get("dl_seed_missing_refs"),
        "dl_seed_caveats": dl_seed.get("dl_seed_caveats"),
        "v3_dl_handoff_summary": f"v3_dl_handoff_summary_{run_id}.json",
        "dataset_hash": dl_seed.get("dataset_hash"),
        "cohort_persistence_source": dl_seed.get("cohort_persistence_source"),
        "ml_vocabulary_entry_count": dl_seed.get("ml_vocabulary_entry_count"),
        "benchmark_family_support_floor": benchmark_support_floor if benchmark_support_floor > 0 else None,
        "family_claim_surface": family_target or None,
        "type_claim_surface": type_target or None,
        "permission_claim_status": "capability_analysis_layer_available",
        "publication_ready": _publication_mode_active(manifest_context),
        "paper_locked": bool(manifest_context.get("paper_locked")),
        "claim_eligible_family_classes": eligible_family_classes,
        "visible_governed_family_classes": visible_family_classes,
        "modeled_family_classes": modeled_family_classes,
        "excluded_non_claim_family_classes": excluded_family_classes,
        "benchmark_support_excluded_samples": benchmark_support_excluded_sample_count,
        "benchmark_support_excluded_families": benchmark_support_excluded_family_count,
        "details_artifact": details_name,
        "supported_claims": list(lines_strong),
        "claim_limits": caution[:4],
        "unsupported_claims": unsupported[:4],
        "next_review": list(nxt),
        "run_mode": str(manifest_context.get("run_mode", "") or getattr(app_config, "RUNTIME_RUN_MODE", "") or ""),
        "profile_id": str(profile_id or ""),
    }
    claim_readiness_path = _write_claim_readiness_summary_json(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        payload=claim_readiness_payload,
    )
    combined_artifacts.append(claim_readiness_path)
    du.print_section("ARTIFACT POINTER")
    if print_fn is None:
        print(f"[Diagnostics] {du.format_console_path(md_path)}")
    else:
        print_fn(f"[Diagnostics] {du.format_console_path(md_path)}")
    rr = getattr(app_config, "RUNTIME_RUN_ROOT", "") or ""
    if rr:
        if print_fn is None:
            print(f"[Run] {du.format_console_path(rr)}")
        else:
            print_fn(f"[Run] {du.format_console_path(rr)}")
    diag_base = diagnostics_dir
    start_candidates = [
        diagnostics_dir / f"v3_label_contract_{run_id}.md",
        diagnostics_dir / f"permission_pattern_contract_{run_id}.md",
        diagnostics_dir / f"ml_run_manifest_{run_id}.json",
        diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json",
        diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv",
        diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json",
        diagnostics_dir / "dataset_foundation_summary.md",
        diagnostics_dir / "modality_contribution_summary.md",
        diagnostics_dir / "model_and_family_failure_summary.md",
        diagnostics_dir / f"backlog_debt_summary_{run_id}.md",
        diagnostics_dir / f"taxonomy_authority_split_{run_id}.md",
        diagnostics_dir / f"taxonomy_type_authority_review_{run_id}.md",
    ]
    start_here = [
        f"`{_artifact_label(path, base=diag_base)}`"
        for path in start_candidates
        if path.is_file()
    ]
    pr("Start here        : " + " | ".join(start_here))
    pr(
        "Operator debt    : "
        + f"`{_artifact_label(diagnostics_dir / f'backlog_debt_summary_{run_id}.md', base=diag_base)}`"
    )
    pr(
        "Skeptic audits    : "
        + " | ".join(
            [
                f"`{_artifact_label(diagnostics_dir / 'headline_score_scope.md', base=diag_base)}`",
                f"`{_artifact_label(diagnostics_dir / 'split_contamination_audit.md', base=diag_base)}`",
                f"`{_artifact_label(diagnostics_dir / 'smote_effect_check.md', base=diag_base)}`",
                f"`{_artifact_label(diagnostics_dir / 'recommended_validation_plan.md', base=diag_base)}`",
            ]
        )
    )
    from obsidiandroid.observability.pipeline_observability.finalize import (
        patch_observability_post_operator_artifacts,
    )

    patch_observability_post_operator_artifacts(
        diagnostics_dir=diagnostics_dir,
        manifest=read_json_dict(diagnostics_dir.parent / "run_manifest.json"),
    )
