"""Primary operator review flow for the latest run."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.authority_taxonomy_terms import (
    AUTHORITY_TAXONOMY_SPLIT_PROBLEM_LABEL,
    live_taxonomy_backlog_detail,
    policy_held_only_note,
    taxonomy_count_drift_note,
)
from obsidiandroid.common.backlog_semantics import build_taxonomy_curation_posture
from obsidiandroid.common.backlog_semantics import (
    build_backlog_debt_summary,
    build_backlog_terminal_lines,
    choose_priority_triage,
    read_run_backlog_snapshot_counts,
    read_android_missing_resolution_snapshot,
    read_false_positive_triage_snapshot,
    read_policy_held_token_risk_snapshot,
)
from obsidiandroid.common.cohort_methodology import resolve_cohort_lock_status, safe_int
from obsidiandroid.common.publication_readiness import publication_ready_display
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.cli.menu.run_artifact_state import resolve_model_comparison_summary_csv

from .menu import diagnostics_banners
from .menu.display_mode import is_compact_mode, is_debug_mode, is_detailed_mode, resolve_display_mode
from .menu.operator_state import build_operator_state
from .ui import display as du
from .ui import menu as mu
from . import startup_menu_diagnostics as diagnostics_menu
from .profile_manager import infer_cohort_readiness_signal


def _read_first_json(candidates: list[Path]) -> dict:
    for path in candidates:
        payload = read_json_dict(path)
        if payload:
            return payload
    return {}


def _status_row_map(rows: list[dict[str, object]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        label = str(row.get("label", "") or "").strip()
        if not label:
            continue
        out[label] = str(row.get("status", "") or "")
    return out


def _run_class(
    *,
    profile_id: str,
    evidence_mode: bool,
    locked_status: str,
    publication_ready_status: str,
) -> str:
    pub = str(publication_ready_status or "").strip().lower()
    locked = locked_status in {"locked", "taxonomy-drift", "count-only", "missing-lock"}
    profile_token = str(profile_id or "").strip().lower()
    if pub in {"ready", "pass"}:
        return "Publication-ready"
    if locked:
        return "Cohort-locked"
    if evidence_mode:
        return "Evidence"
    if profile_token in {
        "malicious_temporal_stability",
        "banker",
        "malicious_temporal_consensus10",
        "malicious_temporal_family300",
    }:
        return "Research"
    return "Exploratory"


def _health_status_map(rows: list[dict[str, object]]) -> dict[str, str]:
    return {
        str(row.get("label", "")).strip(): str(row.get("status", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("label", "")).strip()
    }


def _status_rank(status: str) -> int:
    """Rank status severity for stable operator prioritization."""
    token = str(status or "").strip().upper()
    if token == "RED":
        return 0
    if token == "YELLOW":
        return 1
    if token == "GREEN":
        return 2
    return 3


def _taxonomy_split_report_path(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Return the run-scoped taxonomy authority split Markdown path."""
    return diagnostics_dir / f"taxonomy_authority_split_{run_id}.md"


def _append_warning(
    warnings: list[str],
    *,
    problem: str,
    why: str,
    next_action: str,
    open_label: str,
) -> None:
    warnings.append(f"{problem} Why it matters: {why} Next: {next_action} Open: {open_label}.")


def _observed_readiness_note(readiness: dict[str, object], bucket: str | None) -> str | None:
    token = str(bucket or "").strip()
    if not token:
        return None
    buckets = readiness.get("buckets", {}) if isinstance(readiness, dict) else {}
    payload = buckets.get(token, {}) if isinstance(buckets, dict) else {}
    sample_count = payload.get("sample_count") if isinstance(payload, dict) else None
    family_count = payload.get("family_count") if isinstance(payload, dict) else None
    if sample_count is None:
        return f"Observed readiness for `{token}` is unavailable in the live DB snapshot."
    note = f"Observed readiness for `{token}`: samples={sample_count}"
    if family_count is not None:
        note += f", families={family_count}"
    if "permission_obs" in token and int(sample_count or 0) <= 0:
        note += ". Live DB currently shows no matching PI-observation-ready cohort for this bucket."
    return note


def _read_model_comparison_snapshot(*, output_root: Path, run_id: str) -> dict[str, object]:
    path = resolve_model_comparison_summary_csv(output_root=output_root, run_id=run_id)
    if path is None:
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    if df.empty:
        return {}
    top_row = df.iloc[0]
    if "Top" in df.columns:
        starred = df[df["Top"].astype(str).str.strip() == "*"]
        if not starred.empty:
            top_row = starred.iloc[0]
    model = str(top_row.get("Model", "") or "").strip()
    try:
        macro_f1 = float(top_row.get("Macro F1-Score"))
    except (TypeError, ValueError):
        macro_f1 = None
    try:
        weighted_f1 = float(top_row.get("F1-Score"))
    except (TypeError, ValueError):
        weighted_f1 = None
    try:
        accuracy = float(top_row.get("Accuracy"))
    except (TypeError, ValueError):
        accuracy = None
    return {
        "path": path,
        "top_model": model,
        "top_macro_f1": macro_f1,
        "top_weighted_f1": weighted_f1,
        "top_accuracy": accuracy,
    }


def _read_label_strategy_snapshot(*, diagnostics_dir: Path, output_root: Path, run_id: str) -> dict[str, object]:
    payload = _read_first_json(
        [
            diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json",
            output_root / "diagnostics" / "taxonomy_target_surfaces.latest.json",
        ]
    )
    label_strategy = payload.get("label_strategy") if isinstance(payload.get("label_strategy"), dict) else {}
    return label_strategy if isinstance(label_strategy, dict) else {}


def _temporal_generalization_notes(
    *,
    profile_id: str,
    manifest: dict[str, object],
    model_snapshot: dict[str, object],
) -> list[str]:
    profile_token = str(profile_id or "").strip().lower()
    if not profile_token.startswith("malicious_temporal_"):
        return []
    split_blob = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    split_algorithm = str(split_blob.get("split_algorithm", "") or "").strip()
    split_algo_norm = split_algorithm.lower()
    out: list[str] = []
    if split_algorithm and "temporal" not in split_algo_norm and "year_holdout" not in split_algo_norm:
        out.append(
            f"Temporal profile used non-temporal split algorithm `{split_algorithm}`; interpret the leaderboard as non-forward holdout evidence."
        )
        return out
    temporal_summary = (
        split_blob.get("temporal_split_summary")
        if isinstance(split_blob.get("temporal_split_summary"), dict)
        else {}
    )
    dropped_future_only = int(temporal_summary.get("test_rows_dropped_unseen_train_classes", 0) or 0)
    test_year_floor = int(temporal_summary.get("test_year_floor", 0) or 0)
    observed_min = int(temporal_summary.get("observed_year_min", 0) or 0)
    observed_max = int(temporal_summary.get("observed_year_max", 0) or 0)
    if dropped_future_only > 0 and test_year_floor > 0:
        out.append(
            f"Temporal holdout dropped {dropped_future_only} future-only row(s) from families unseen in train years < {test_year_floor} (observed year span {observed_min}-{observed_max})."
        )
    top_model = str(model_snapshot.get("top_model", "") or "").strip()
    macro_f1 = model_snapshot.get("top_macro_f1")
    if macro_f1 is not None and float(macro_f1) < 0.40:
        model_text = top_model or "top model"
        out.append(
            f"Forward-in-time family generalization remains weak: {model_text} reached Macro-F1 {float(macro_f1):.4f} on the review leaderboard."
        )
    return out


def _readiness_gap_notes(
    *,
    readiness: dict[str, object],
    bucket: str | None,
    paper_locked: bool,
) -> list[str]:
    token = str(bucket or "").strip()
    buckets = readiness.get("buckets", {}) if isinstance(readiness, dict) else {}
    payload = buckets.get(token, {}) if isinstance(buckets, dict) else {}
    warnings = readiness.get("warnings", []) if isinstance(readiness, dict) else []
    taxonomy = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}

    out: list[str] = []
    sample_count = payload.get("sample_count") if isinstance(payload, dict) else None
    permission_obs_available = bool(readiness.get("permission_obs_available", False))
    if "permission_obs" in token and (
        sample_count in (None, 0) or not permission_obs_available
    ):
        out.append(
            "Declared readiness intent names `permission_obs`, but the live DB does not currently verify a matching PI-observed cohort."
        )
    repair_candidate_count = int(taxonomy.get("repair_candidate_count") or 0)
    unresolved_family_count = int(taxonomy.get("unresolved_family_count") or 0)
    known_unresolved_count = int(taxonomy.get("known_unresolved_family_count") or 0)
    policy_held_count = int(taxonomy.get("policy_held_family_count") or 0)
    posture = build_taxonomy_curation_posture(readiness=readiness)
    if repair_candidate_count > 0 or known_unresolved_count > 0 or policy_held_count > 0:
        message = live_taxonomy_backlog_detail(
            repair_candidate_count=repair_candidate_count,
            known_unresolved_count=known_unresolved_count,
            policy_held_count=policy_held_count,
        )
        if paper_locked:
            message += " This run is lock-bound, so Erebus-side family authority improvements may not appear here until the lock is refreshed."
        else:
            message += " Compare against an unlocked/current cohort before concluding the new Erebus curation had no effect."
        out.append(message)
    unresolved_family_count_value = taxonomy.get("unresolved_family_count")
    if unresolved_family_count_value is not None and unresolved_family_count == 0 and policy_held_count > 0:
        out.append(policy_held_only_note())
    curation_note = str(posture.get("note", "") or "").strip() or None
    if curation_note:
        out.append(curation_note)
    for warning in warnings[:2]:
        warning_text = str(warning).strip()
        if warning_text:
            out.append(warning_text)
    return out


def build_review_latest_run_summary(*, output_root: Path, latest_run_id: str | None) -> dict[str, object]:
    """Build operator-first summary for the latest run."""
    shared = build_operator_state(output_base=output_root, run_id=latest_run_id)
    rid = str(shared.get("latest_run_id", "") or "").strip()
    mode = str(shared.get("display_mode", "") or resolve_display_mode())
    run_root = output_root / "runs" / rid if rid else Path()
    rdiag = run_root / "diagnostics" if rid else Path()
    gdiag = output_root / "diagnostics"
    manifest = shared.get("manifest_payload") if isinstance(shared.get("manifest_payload"), dict) else {}
    cohort_contract = (
        manifest.get("paper_cohort_contract")
        if isinstance(manifest.get("paper_cohort_contract"), dict)
        else manifest.get("cohort_contract")
        if isinstance(manifest.get("cohort_contract"), dict)
        else {}
    )
    sample_id_lock = (
        cohort_contract.get("sample_id_lock")
        if isinstance(cohort_contract.get("sample_id_lock"), dict)
        else {}
    )
    taxonomy_drift = (
        sample_id_lock.get("taxonomy_label_drift")
        if isinstance(sample_id_lock.get("taxonomy_label_drift"), dict)
        else {}
    )
    profile_id = str(shared.get("profile_id", "") or "unknown")
    lock_status = str(shared.get("cohort_lock_status", "") or "").strip() or resolve_cohort_lock_status(manifest)
    publication_ready_status = str(shared.get("publication_ready_status", "") or "unknown")
    run_class = _run_class(
        profile_id=profile_id,
        evidence_mode=bool(shared.get("evidence_mode", False)),
        locked_status=lock_status,
        publication_ready_status=publication_ready_status,
    )
    publication_ready_display_value = publication_ready_display(
        publication_ready_status,
        run_class=run_class,
        evidence_mode=bool(shared.get("evidence_mode", False)),
    )

    overview = diagnostics_banners.build_diagnostics_overview(output_root=output_root, latest_run_id=rid)
    rows = overview.get("rows") if isinstance(overview.get("rows"), list) else []
    status_map = _status_row_map([row for row in rows if isinstance(row, dict)])

    ablation_csv = rdiag / "feature_set_ablation_summary.csv"
    ablation_md = rdiag / "feature_set_ablation_summary.md"
    figure_md = rdiag / "figure_validity_audit.md"
    cohort_funnel_md = rdiag / "cohort_funnel.md"
    trained_family_registry = rdiag / f"trained_family_registry_{rid}.csv" if rid else Path()
    low_support_csv = rdiag / "low_support_families.csv"
    taxonomy = read_json_dict(oh.resolve_taxonomy_consistency_summary_path(rdiag, rid)) if rid else {}
    q2 = _read_first_json(
        [
            rdiag / "modality_contribution_summary.json",
            gdiag / "modality_contribution_summary.json",
        ]
    )
    model_snapshot = _read_model_comparison_snapshot(output_root=output_root, run_id=rid) if rid else {}
    label_strategy = _read_label_strategy_snapshot(diagnostics_dir=rdiag, output_root=output_root, run_id=rid) if rid else {}
    fp_triage = read_false_positive_triage_snapshot(output_root=output_root)
    android_missing_triage = read_android_missing_resolution_snapshot(output_root=output_root)
    policy_held_triage = read_policy_held_token_risk_snapshot(output_root=output_root)
    backlog_priority = choose_priority_triage(
        fp_triage=fp_triage,
        android_missing_triage=android_missing_triage,
    )
    taxonomy_support = diagnostics_menu.build_taxonomy_support_tuning_snapshot(run_id=rid, output_root=output_root) if rid else {}
    permission_tuning = diagnostics_menu.build_permission_coverage_tuning_snapshot(run_id=rid, output_root=output_root) if rid else {}
    try:
        cohort_readiness = get_cohort_readiness_snapshot()
    except Exception as exc:
        cohort_readiness = {
            "status": "degraded",
            "warnings": [f"Cohort readiness unavailable: {exc}"],
            "buckets": {},
        }
    debt_summary = build_backlog_debt_summary(
        readiness=cohort_readiness,
        fp_triage=fp_triage,
        android_missing_triage=android_missing_triage,
        policy_held_triage=policy_held_triage,
    )
    backlog_snapshot_warning: dict[str, str] | None = None
    if isinstance(debt_summary, dict) and debt_summary:
        debt_summary["source_note"] = "live DB now (reviewing an older run may differ)"
        run_backlog_counts = read_run_backlog_snapshot_counts(
            rdiag / f"backlog_debt_summary_{rid}.md"
        ) if rid else {}
        live_missing = 0
        for row in list(debt_summary.get("rows", [])):
            if isinstance(row, dict) and str(row.get("label", "") or "") == "Missing primary labels":
                live_missing = safe_int(row.get("count", 0), 0)
                break
        run_missing = safe_int(run_backlog_counts.get("Missing primary labels", 0), 0)
        if run_missing > 0 and run_missing != live_missing:
            debt_summary["snapshot_compare_note"] = (
                f"missing primary labels were {run_missing} at run time; live DB now shows {live_missing}"
            )
            backlog_snapshot_warning = {
                "problem": "Backlog debt: run snapshot differs from current live DB.",
                "why": (
                    f"the saved run reported missing primary labels={run_missing}, "
                    f"but live DB now shows {live_missing}"
                ),
                "next_action": (
                    "treat backlog rows in review mode as live operator debt, "
                    "and use the saved run bundle only as historical context"
                ),
                "open_label": "Backlog debt",
            }
    cohort_membership_mode = str(shared.get("cohort_membership_mode", "") or "").strip()
    cohort_membership_note = str(shared.get("cohort_membership_authority_note", "") or "").strip()
    rescued_unknown_consensus = safe_int(
        shared.get("min_malicious_detections_rescued_unknown_consensus", 0),
        0,
    )
    rescued_unknown_threshold = safe_int(
        shared.get("min_malicious_detections_threshold", 0),
        0,
    )
    readiness_signal = infer_cohort_readiness_signal(profile_id)
    readiness_observed_note = _observed_readiness_note(cohort_readiness, readiness_signal.get("bucket"))
    readiness_gap_notes = _readiness_gap_notes(
        readiness=cohort_readiness,
        bucket=readiness_signal.get("bucket"),
        paper_locked=cohort_membership_mode == "paper_locked_snapshot_membership",
    )
    temporal_gap_notes = _temporal_generalization_notes(
        profile_id=profile_id,
        manifest=manifest,
        model_snapshot=model_snapshot,
    )

    health_rows = [
        {"label": "Cohort / labels", "status": status_map.get("Cohort / labels", "RED")},
        {"label": "Taxonomy consistency", "status": status_map.get("Taxonomy consistency", "RED")},
        {"label": "Permission signal", "status": status_map.get("Permission signal", "RED")},
        {"label": "Vendor/parser", "status": status_map.get("Vendor/parser coverage", "RED")},
        {"label": "Feature matrix", "status": status_map.get("Feature matrix", "RED")},
        {
            "label": "Ablation / signal contribution",
            "status": "GREEN" if ablation_csv.is_file() or ablation_md.is_file() else "YELLOW",
        },
        {
            "label": "Figure validity",
            "status": "GREEN" if figure_md.is_file() else "YELLOW",
        },
        {"label": "Evidence/provenance", "status": status_map.get("Evidence/provenance", "RED")},
    ]
    health_map = _health_status_map(health_rows)

    warnings: list[str] = []
    if isinstance(backlog_snapshot_warning, dict):
        _append_warning(
            warnings,
            problem=str(backlog_snapshot_warning.get("problem", "") or ""),
            why=str(backlog_snapshot_warning.get("why", "") or ""),
            next_action=str(backlog_snapshot_warning.get("next_action", "") or ""),
            open_label=str(backlog_snapshot_warning.get("open_label", "") or ""),
        )
    if lock_status == "count-only":
        _append_warning(
            warnings,
            problem="Cohort lock: count-only lock.",
            why="row counts are governed, but exact sample-id membership is not fully reproducible from a locked snapshot",
            next_action="open the run science index and cohort funnel, then confirm whether this run is acceptable for exploratory review only",
            open_label="Run science index",
        )
    elif lock_status == "taxonomy-drift":
        drift_detail = taxonomy_count_drift_note(taxonomy_drift) if taxonomy_drift else ""
        why = "the preserved sample-id set still matches, but live family/type labels changed inside the locked cohort"
        if drift_detail:
            why += f"; {drift_detail}"
        _append_warning(
            warnings,
            problem="Cohort lock: locked sample membership with taxonomy-label drift.",
            why=why,
            next_action="open the cohort contract and taxonomy authority artifacts, then decide whether to reconcile records or refresh the paper lock",
            open_label="Run science index",
        )
    elif lock_status == "missing-lock":
        _append_warning(
            warnings,
            problem="Cohort lock: missing or mismatched lock for an evidence/publication-intended run.",
            why="membership cannot be trusted as a publication-grade locked cohort until the sample-id lock is present and aligned",
            next_action="open the run science index, inspect the cohort contract details, and treat the run as blocked for publication claims",
            open_label="Run science index",
        )
    tax_mismatch = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) if taxonomy else 0
    claim_facing_tax_mismatch = int(
        taxonomy.get("paper_facing_taxonomy_mismatch_count", tax_mismatch) or 0
    ) if taxonomy else 0
    family_label_mismatch = int(taxonomy.get("family_label_mismatch_count", 0) or 0) if taxonomy else 0
    type_issue_count = (
        int(taxonomy.get("type_mismatch_count", 0) or 0)
        + int(taxonomy.get("type_noncanonical_count", 0) or 0)
        + int(taxonomy.get("type_missing_label_count", 0) or 0)
    ) if taxonomy else 0
    parser_summary = shared.get("parser_summary") if isinstance(shared.get("parser_summary"), dict) else {}
    if health_map.get("Cohort / labels") == "RED":
        _append_warning(
            warnings,
            problem="Cohort / labels: run-scoped cohort foundation is missing.",
            why="cohort identity and label lineage are not auditable from the review surface",
            next_action="open the best available run science index and verify cohort foundation exports",
            open_label="Run science index",
        )
    if cohort_membership_mode == "paper_locked_snapshot_membership":
        _append_warning(
            warnings,
            problem="Cohort membership: locked sample-id snapshot is authoritative for this run.",
            why=cohort_membership_note
            or "sample-stage membership came from a governed locked cohort before normal shrinking gates",
            next_action="open the run science index and confirm that lock-authoritative membership is the intended methodology for this run",
            open_label="Run science index",
        )
    if readiness_gap_notes:
        _append_warning(
            warnings,
            problem=f"{AUTHORITY_TAXONOMY_SPLIT_PROBLEM_LABEL}: observed DB state does not fully match the profile-ready story.",
            why="; ".join(readiness_gap_notes[:2]),
            next_action="compare the live readiness snapshot, true authority debt, and policy-held token residue against this run before treating the cohort as absorbing the latest Erebus-side curation",
            open_label="Run science index",
        )
    if temporal_gap_notes:
        _append_warning(
            warnings,
            problem="Temporal generalization gap: forward holdout evidence remains weaker than the cohort/build surfaces suggest.",
            why="; ".join(temporal_gap_notes[:2]),
            next_action="review the split-freeze headline and model comparison leaderboard before retuning models or judging Erebus-side curation impact",
            open_label="Feature-set ablation summary",
        )
    for label, payload in (
        ("VT false-positive triage", fp_triage),
        ("Android missing-resolution triage", android_missing_triage),
    ):
        if not isinstance(payload, dict) or not payload:
            continue
        freshness = str(payload.get("freshness", "") or "").strip()
        if freshness != "stale":
            continue
        _append_warning(
            warnings,
            problem=f"{label}: latest export is stale.",
            why="the visible backlog may not reflect current DB state or the latest suppression/authority repairs",
            next_action=f"refresh the {label.lower()} export before using it as the main cleanup surface",
            open_label=label,
        )
    if backlog_priority:
        backlog_label = str(backlog_priority.get("label", "") or "").strip()
        backlog_rows = safe_int(backlog_priority.get("row_count", 0), 0)
        backlog_lane = str(backlog_priority.get("top_lane", "") or "").strip()
        backlog_lane_count = safe_int(backlog_priority.get("top_lane_count", 0), 0)
        backlog_freshness = str(backlog_priority.get("freshness", "") or "").strip()
        why = f"{backlog_rows} queued row(s) currently dominate operator cleanup pressure"
        if backlog_lane:
            why += f"; top lane `{backlog_lane}` carries {backlog_lane_count} row(s)"
        if backlog_freshness:
            why += f"; export freshness is {backlog_freshness}"
        _append_warning(
            warnings,
            problem=f"Priority backlog: {backlog_label} is currently the main cleanup surface.",
            why=why,
            next_action=str(backlog_priority.get("action", "") or "Open the dominant backlog queue."),
            open_label=backlog_label,
        )
    if rescued_unknown_consensus > 0:
        _append_warning(
            warnings,
            problem=f"Malware rescue: {rescued_unknown_consensus} rows were retained with missing VT consensus.",
            why=(
                f"the min_malicious_detections gate (threshold={rescued_unknown_threshold}) "
                "rescued rows using malware taxonomy or other malicious evidence"
            ),
            next_action="open the run science index and review cohort gate counts before treating consensus-based malware support as complete",
            open_label="Run science index",
        )
    if health_map.get("Taxonomy consistency") in {"YELLOW", "RED"} and tax_mismatch > 0:
        _append_warning(
            warnings,
            problem=(
                f"Taxonomy consistency: {tax_mismatch} total mismatches detected "
                f"({claim_facing_tax_mismatch} claim-facing)."
            ),
            why=(
                f"type authority/rendering issues={type_issue_count}; "
                f"model prediction errors={taxonomy_support.get('model_prediction_error_count', family_label_mismatch)}"
            ),
            next_action="review taxonomy authority split, then inspect any remaining rendering mismatch and prediction-error CSVs",
            open_label="Taxonomy authority split",
        )
    if health_map.get("Vendor/parser") in {"YELLOW", "RED"}:
        _append_warning(
            warnings,
            problem=f"Vendor/parser: {parser_summary.get('needs_attention') or 'coverage needs review'}.",
            why="vendor parsing affects family signal quality and single-vendor inspection depth",
            next_action="review parser onboarding queue and selected vendor context",
            open_label="Parser summary",
        )
    if health_map.get("Feature matrix") == "RED":
        _append_warning(
            warnings,
            problem="Feature matrix: modality coverage export is missing.",
            why="feature availability by modality is harder to verify before tuning",
            next_action="open feature matrix / modality coverage and confirm fused-matrix coverage",
            open_label="Feature matrix / modality coverage",
        )
    if health_map.get("Ablation / signal contribution") in {"YELLOW", "RED"}:
        _append_warning(
            warnings,
            problem="Ablation / signal contribution: summary is missing.",
            why="it is harder to tell which signal family is carrying the result",
            next_action="open the ablation summary after the next run",
            open_label="Feature-set ablation summary",
        )
    if health_map.get("Figure validity") in {"YELLOW", "RED"}:
        _append_warning(
            warnings,
            problem="Figure validity: audit summary is missing.",
            why="figure-safe interpretation is weaker without explicit caveat review",
            next_action="review figure validity audit",
            open_label="Figure validity audit",
        )
    if health_map.get("Evidence/provenance") in {"YELLOW", "RED"}:
        _append_warning(
            warnings,
            problem="Evidence/provenance: canonical run science package is incomplete.",
            why="authoritative review artifacts may require fallback indexes",
            next_action="open the run science index and verify diagnostic provenance",
            open_label="Run science index",
        )
    if not warnings:
        warnings.append("No major operator warnings surfaced for the latest run.")

    open_first = [
        {
            "label": "Run science index",
            "path": Path(str(shared.get("best_run_index_path", "") or "")),
        },
        {"label": "Cohort funnel", "path": cohort_funnel_md},
        {
            "label": "Taxonomy authority split",
            "path": _taxonomy_split_report_path(diagnostics_dir=rdiag, run_id=rid) if rid else Path(),
        },
        {"label": "Feature-set ablation summary", "path": ablation_md if ablation_md.is_file() else ablation_csv},
        {"label": "Figure validity audit", "path": figure_md},
    ]
    row_to_open_label = {
        "Cohort / labels": "Run science index",
        "Taxonomy consistency": "Taxonomy authority split",
        "Permission signal": "Permission and feature health",
        "Vendor/parser": "Parser & Vendor Coverage",
        "Feature matrix": "Feature matrix / modality coverage",
        "Ablation / signal contribution": "Feature-set ablation summary",
        "Figure validity": "Figure validity audit",
        "Evidence/provenance": "Run science index",
    }
    ranked_issues = sorted(
        [row for row in health_rows if isinstance(row, dict)],
        key=lambda row: _status_rank(str(row.get("status", ""))),
    )
    tune_next_priority: list[str] = []
    for row in ranked_issues:
        label = str(row.get("label", "") or "")
        token = row_to_open_label.get(label)
        if token and token not in tune_next_priority:
            tune_next_priority.append(token)

    tuning_actions: list[str] = []
    if health_map.get("Taxonomy consistency") in {"YELLOW", "RED"} and tax_mismatch > 0:
        tuning_actions.append("Review taxonomy authority split before reading the older mismatch summary.")
    if health_map.get("Vendor/parser") in {"YELLOW", "RED"} and parser_summary.get("unmapped_vendors", 0):
        tuning_actions.append("Review parser onboarding candidates and top unmapped vendors.")
    if health_map.get("Permission signal") in {"YELLOW", "RED"} and q2 and q2.get("permission_signal_pct") not in (None, "", "—"):
        tuning_actions.append("Review permission signal and feature survival before changing feature settings.")
    if health_map.get("Ablation / signal contribution") in {"YELLOW", "RED"}:
        tuning_actions.append("Review ablation summary to identify which signal family is carrying the result.")
    elif ablation_csv.is_file() or ablation_md.is_file():
        tuning_actions.append("Review ablation summary to identify which signal family is carrying the result.")
    if health_map.get("Cohort / labels") in {"YELLOW", "RED"} or low_support_csv.is_file() or trained_family_registry.is_file():
        tuning_actions.append("Review support-threshold effects and trained-family coverage.")
    if cohort_membership_mode == "paper_locked_snapshot_membership":
        tuning_actions.append("Confirm that locked sample-id membership is the intended authority before comparing this run against contract-shrunk cohorts.")
    if readiness_gap_notes:
        tuning_actions.append("Check live readiness mismatch, true authority debt, and policy-held token residue before deciding that recent Erebus-side curation failed to help this run.")
    if temporal_gap_notes:
        tuning_actions.append("Review temporal holdout caveats and leaderboard weakness before changing models; this run may be limited more by forward-time family drift than by missing features.")
    if rescued_unknown_consensus > 0:
        tuning_actions.append("Review rescued missing-consensus malware rows before raising or lowering the malicious-detection threshold.")
    if backlog_priority:
        tuning_actions.append(str(backlog_priority.get("action", "") or "Open the dominant backlog queue."))
    if str(fp_triage.get("freshness", "") or "").strip() == "stale":
        tuning_actions.append("Refresh the VT false-positive triage export before using it to drive suppression or review work.")
    if str(android_missing_triage.get("freshness", "") or "").strip() == "stale":
        tuning_actions.append("Refresh the Android missing-resolution triage export before treating it as the current backlog.")
    if lock_status == "count-only":
        tuning_actions.append("Confirm that count-only cohort lock is acceptable for this review before using the run as a reproducible evidence baseline.")
    elif lock_status == "taxonomy-drift":
        drift_detail = taxonomy_count_drift_note(taxonomy_drift) if taxonomy_drift else ""
        if drift_detail:
            tuning_actions.append(f"Review taxonomy-label drift inside the locked sample set before comparing family/type counts to the historical paper contract: {drift_detail}")
        else:
            tuning_actions.append("Review taxonomy-label drift inside the locked sample set before comparing family/type counts to the historical paper contract.")
    elif lock_status == "missing-lock":
        tuning_actions.append("Do not treat this run as publication-grade until the sample-id cohort lock is restored and revalidated.")
    if health_map.get("Figure validity") in {"YELLOW", "RED"}:
        tuning_actions.append("Review figure validity before using plots as research claims.")
    if not tuning_actions:
        tuning_actions.append("Open run science index and inspect cohort funnel first.")
    tax_recommended_action = (
        "Review taxonomy mismatches first, then near-threshold families before adjusting support settings."
        if safe_int(taxonomy_support.get("taxonomy_mismatch_total", 0), 0) > 0
        else "Cross-check retained/dropped families with support threshold preview before profile changes."
    )
    if tune_next_priority:
        tuning_actions.insert(0, "Prioritize screens in this order: " + " -> ".join(tune_next_priority[:3]) + ".")
    if label_strategy:
        family_target = str(label_strategy.get("preferred_family_target", "") or "").strip()
        type_target = str(label_strategy.get("preferred_type_target", "") or "").strip()
        avoid = label_strategy.get("avoid_for_primary_claims", [])
        if family_target and type_target:
            tuning_actions.insert(
                1 if tuning_actions else 0,
                f"Keep supervision anchored on {family_target} for family and {type_target} for coarse taxonomy before retuning models."
            )
        if isinstance(avoid, list) and avoid:
            tuning_actions.append(
                "Avoid promoting raw audit-only surfaces into primary claim targets: "
                + ", ".join(str(x) for x in avoid)
                + "."
            )

    return {
        "display_mode": mode,
        "run_id": rid,
        "profile_id": profile_id,
        "run_class": run_class,
        "cohort_lock_status": lock_status,
        "cohort_membership_mode": cohort_membership_mode or "standard_contract_filters",
        "evidence_mode": bool(shared.get("evidence_mode", False)),
        "publication_ready_status": publication_ready_display_value,
        "rescued_unknown_consensus": rescued_unknown_consensus,
        "health_rows": health_rows,
        "warnings": warnings[:5],
        "open_first": open_first,
        "tuning_actions": tuning_actions[:5],
        "taxonomy_support_summary": taxonomy_support,
        "label_strategy_summary": label_strategy,
        "permission_tuning_summary": permission_tuning,
        "false_positive_triage_summary": fp_triage,
        "android_missing_resolution_summary": android_missing_triage,
        "policy_held_token_risk_summary": policy_held_triage,
        "priority_backlog_summary": backlog_priority,
        "backlog_debt_summary": debt_summary,
        "cohort_readiness_summary": cohort_readiness,
        "cohort_readiness_signal": readiness_signal,
        "cohort_readiness_observed_note": readiness_observed_note,
        "cohort_readiness_gap_notes": readiness_gap_notes[:3],
        "temporal_generalization_notes": temporal_gap_notes[:3],
        "taxonomy_support_recommended_action": tax_recommended_action,
        "run_science_index_path": shared.get("best_run_index_path"),
        "run_science_index_canonical": bool(shared.get("has_canonical_run_science", False)),
        "cohort_funnel_path": cohort_funnel_md,
        "advanced_paths": {
            "diagnostics_dir": rdiag,
            "trained_family_registry": trained_family_registry,
            "low_support_families": low_support_csv,
            "feature_set_ablation_summary_csv": ablation_csv,
            "figure_validity_audit": figure_md,
        },
    }


def print_compact_review_latest_run(*, output_root: Path, latest_run_id: str | None) -> None:
    """Print compact operator-first review block for the latest run."""
    summary = build_review_latest_run_summary(output_root=output_root, latest_run_id=latest_run_id)
    du.print_section("REVIEW LATEST RUN")
    du.print_stat("Run", str(summary.get("run_id") or "None yet"))
    du.print_stat("Profile", str(summary.get("profile_id") or "unknown"))
    du.print_stat("Class", str(summary.get("run_class") or "unknown"))
    du.print_stat("Cohort lock", str(summary.get("cohort_lock_status") or "unknown"))
    du.print_stat("Evidence mode", "Yes" if bool(summary.get("evidence_mode", False)) else "No")
    du.print_stat("Publication-ready", str(summary.get("publication_ready_status") or "Not applicable"))
    print("")
    print("Cohort Readiness")
    readiness = summary.get("cohort_readiness_summary", {})
    if isinstance(readiness, dict):
        buckets = readiness.get("buckets", {})
        if isinstance(buckets, dict) and buckets:
            for name in (
                "all_catalog",
                "android_platform",
                "android_with_permission_obs",
                "android_high_or_strong_vt_with_permission_obs",
                "android_labeled_primary_with_permission_obs",
                "android_banker_with_permission_obs",
                "android_family_ready_min3_permission_obs",
            ):
                bucket = buckets.get(name, {})
                if not isinstance(bucket, dict):
                    continue
                sample_count = bucket.get("sample_count")
                family_count = bucket.get("family_count")
                if sample_count is None or family_count is None:
                    value = "unavailable"
                else:
                    value = f"{sample_count} samples / {family_count} families"
                du.print_stat(f"  {name}", value)
        signal = summary.get("cohort_readiness_signal", {})
        if isinstance(signal, dict):
            du.print_info(f"  {str(signal.get('summary', '') or '').strip()}")
            detail = str(signal.get("detail", "") or "").strip()
            if detail:
                du.print_note(f"  {detail}")
        observed_note = str(summary.get("cohort_readiness_observed_note", "") or "").strip()
        if observed_note:
            du.print_note(f"  {observed_note}")
        for note in summary.get("cohort_readiness_gap_notes", [])[:3]:
            du.print_note(f"  {note}")
        for note in summary.get("temporal_generalization_notes", [])[:3]:
            du.print_note(f"  {note}")
        for note in readiness.get("warnings", [])[:3]:
            du.print_note(f"  {note}")
    print("")
    print("Taxonomy & Support Tuning")
    tax = summary.get("taxonomy_support_summary", {})
    if isinstance(tax, dict) and tax:
        du.print_stat("  Taxonomy health", str(tax.get("taxonomy_health", "—")))
        du.print_stat("  Taxonomy mismatches", str(tax.get("taxonomy_mismatch_total", "—")))
        du.print_stat(
            "  Model prediction errors vs type/rendering",
            f"{tax.get('model_prediction_error_count', tax.get('family_mismatch_count', '—'))} vs {tax.get('type_rendering_issue_count', '—')}",
        )
        du.print_stat(
            "  Authority gap rows (run/global)",
            f"{tax.get('authority_gap_run_count', '—')} / {tax.get('authority_gap_global_count', '—')}",
        )
        provenance_parts = [
            f"split={tax.get('taxonomy_authority_split_json_origin')}"
            for _key in ("taxonomy_authority_split_json_origin",)
            if str(tax.get("taxonomy_authority_split_json_origin", "") or "").strip()
        ]
        summary_origin = str(tax.get("taxonomy_consistency_summary_origin", "") or "").strip()
        if summary_origin:
            provenance_parts.append(f"summary={summary_origin}")
        target_origin = str(tax.get("taxonomy_target_surfaces_origin", "") or "").strip()
        if target_origin:
            provenance_parts.append(f"target_surfaces={target_origin}")
        if provenance_parts:
            du.print_info("  Artifact provenance: " + ", ".join(provenance_parts))
        if any("global_latest_mirror" in part for part in provenance_parts):
            du.print_note(
                "  Taxonomy/support summary is using at least one global latest mirror artifact; treat it as cross-run guidance until the run-scoped export exists."
            )
        du.print_stat("  min_samples_per_family", str(tax.get("min_samples_per_family", "—")))
        du.print_stat(
            "  Families retained/dropped",
            f"{tax.get('families_retained', '—')} / {tax.get('families_dropped', '—')}",
        )
        du.print_stat("  Samples dropped (estimate)", str(tax.get("samples_dropped_estimate", "—")))
        du.print_stat("  Families just below threshold", str(tax.get("families_just_below_threshold", "—")))
        preview: list[str] = []
        sens = tax.get("threshold_sensitivity", [])
        if isinstance(sens, list) and sens:
            for row in sens[:5]:
                if not isinstance(row, dict):
                    continue
                preview.append(
                    f"t{row.get('threshold')}: fam {row.get('retained_families')}/{row.get('dropped_families')} kept/dropped; "
                    f"samples {row.get('retained_samples')}/{row.get('dropped_samples')}"
                )
        if preview:
            du.print_info("  Threshold sensitivity (5/10/15/20/25): " + " | ".join(preview))
        du.print_info(f"  Recommended next action: {summary.get('taxonomy_support_recommended_action', 'Review taxonomy/support artifacts.')}")
    label_strategy = summary.get("label_strategy_summary", {})
    if isinstance(label_strategy, dict) and label_strategy:
        du.print_stat("  Preferred family target", str(label_strategy.get("preferred_family_target", "—") or "—"))
        du.print_stat("  Preferred type target", str(label_strategy.get("preferred_type_target", "—") or "—"))
        avoid = label_strategy.get("avoid_for_primary_claims", [])
        du.print_stat(
            "  Avoid for primary claims",
            ", ".join(str(x) for x in avoid) if isinstance(avoid, list) and avoid else "—",
        )
        interp = str(label_strategy.get("alignment_interpretation", "") or "").strip()
        if interp:
            du.print_info(f"  Label strategy note: {interp}")
    print("")
    fp_triage = summary.get("false_positive_triage_summary", {})
    if isinstance(fp_triage, dict) and fp_triage:
        print("False-Positive Triage")
        du.print_stat("  Triage rows", str(fp_triage.get("row_count", "—")))
        freshness = str(fp_triage.get("freshness", "") or "").strip()
        if freshness:
            du.print_info(f"  Export freshness: {freshness}")
        lane_counts = fp_triage.get("lane_counts", {})
        if isinstance(lane_counts, dict) and lane_counts:
            top_lanes = ", ".join(
                f"{lane}={count}" for lane, count in list(lane_counts.items())[:3]
            )
            du.print_info(f"  Lane summary: {top_lanes}")
        global_policy_counts = fp_triage.get("global_policy_counts", {})
        if isinstance(global_policy_counts, dict) and global_policy_counts:
            policy_text = ", ".join(
                f"{bucket}={count}" for bucket, count in list(global_policy_counts.items())[:3]
            )
            du.print_info(f"  Global policy: {policy_text}")
        print("")
    debt_summary = summary.get("backlog_debt_summary", {})
    if isinstance(debt_summary, dict) and debt_summary:
        print("Backlog Debt")
        lines = build_backlog_terminal_lines(debt_summary=debt_summary, max_rows=5)
        if lines:
            first = str(lines[0])
            if first.startswith("Focus area: "):
                du.print_info(f"  {first}")
                for line in lines[1:]:
                    if "Recommended next action:" in line:
                        du.print_info(f"  {line}")
                    else:
                        du.print_note(f"  {line}")
        print("")
    priority_backlog = summary.get("priority_backlog_summary", {})
    if isinstance(priority_backlog, dict) and priority_backlog:
        print("Priority Backlog")
        du.print_stat("  Focus first", str(priority_backlog.get("label", "—")))
        du.print_stat("  Rows", str(priority_backlog.get("row_count", "—")))
        freshness = str(priority_backlog.get("freshness", "") or "").strip()
        if freshness:
            du.print_info(f"  Export freshness: {freshness}")
        top_lane = str(priority_backlog.get("top_lane", "") or "").strip()
        if top_lane:
            du.print_info(
                f"  Dominant lane: {top_lane} ({priority_backlog.get('top_lane_count', '—')})"
            )
        action = str(priority_backlog.get("action", "") or "").strip()
        if action:
            du.print_info(f"  Recommended next action: {action}")
        print("")
    android_missing_triage = summary.get("android_missing_resolution_summary", {})
    if isinstance(android_missing_triage, dict) and android_missing_triage:
        print("Android Missing-Resolution Triage")
        du.print_stat("  Triage rows", str(android_missing_triage.get("row_count", "—")))
        freshness = str(android_missing_triage.get("freshness", "") or "").strip()
        if freshness:
            du.print_info(f"  Export freshness: {freshness}")
        lane_counts = android_missing_triage.get("lane_counts", {})
        if isinstance(lane_counts, dict) and lane_counts:
            top_lanes = ", ".join(
                f"{lane}={count}" for lane, count in list(lane_counts.items())[:3]
            )
            du.print_info(f"  Lane summary: {top_lanes}")
        cluster_counts = android_missing_triage.get("cluster_counts", {})
        if isinstance(cluster_counts, dict) and cluster_counts:
            top_clusters = ", ".join(
                f"{cluster}={count}" for cluster, count in list(cluster_counts.items())[:3]
            )
            du.print_info(f"  Package clusters: {top_clusters}")
        print("")
    policy_held_triage = summary.get("policy_held_token_risk_summary", {})
    if isinstance(policy_held_triage, dict) and policy_held_triage:
        print("Policy-Held Token Risk")
        du.print_stat("  Triage rows", str(policy_held_triage.get("row_count", "—")))
        freshness = str(policy_held_triage.get("freshness", "") or "").strip()
        if freshness:
            du.print_info(f"  Export freshness: {freshness}")
        lane_counts = policy_held_triage.get("lane_counts", {})
        if isinstance(lane_counts, dict) and lane_counts:
            top_lanes = ", ".join(
                f"{lane}={count}" for lane, count in list(lane_counts.items())[:3]
            )
            du.print_info(f"  Lane summary: {top_lanes}")
        token_kind_counts = policy_held_triage.get("token_kind_counts", {})
        if isinstance(token_kind_counts, dict) and token_kind_counts:
            top_kinds = ", ".join(
                f"{kind}={count}" for kind, count in list(token_kind_counts.items())[:3]
            )
            du.print_info(f"  Token classes: {top_kinds}")
        du.print_note("  Treat this as hold-policy review, not safe family-authority promotion.")
        print("")
    print("Permission Coverage Tuning")
    perm = summary.get("permission_tuning_summary", {})
    if isinstance(perm, dict) and perm:
        du.print_stat(
            "  Global permission signal",
            f"{perm.get('global_permission_signal_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(perm.get('global_permission_signal_pct'))})",
        )
        du.print_stat("  Weak/zero coverage types", str(perm.get("weak_or_zero_coverage_types", "—")))
        du.print_stat("  Weak/zero coverage families", str(perm.get("weak_or_zero_coverage_families", "—")))
        du.print_stat("  Permission feature survival", str(perm.get("permission_feature_survival", "—")))
        du.print_stat("  Permission-only ablation signal", str(perm.get("permission_only_ablation_signal", "—")))
        du.print_info("  Tune next: inspect weak/zero coverage groups before changing permission feature settings.")
    print("")
    print("Status")
    for row in summary.get("health_rows", []):
        if isinstance(row, dict):
            du.print_stat(f"  {row.get('label', '')}", str(row.get("status", "")))
    print("")
    print("Needs Attention")
    for warning in summary.get("warnings", []):
        du.print_note(str(warning))
    print("")
    print("Open First")
    open_first = summary.get("open_first", [])
    for idx, item in enumerate(open_first, start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "") or "")
        path = item.get("path")
        if idx == 1 and isinstance(path, Path) and path:
            du.print_stat(f"  {idx}. {label}", str(path))
        else:
            if is_compact_mode(str(summary.get("display_mode", ""))):
                du.print_stat(f"  {idx}. {label}", "available" if isinstance(path, Path) and path.exists() else "missing")
            else:
                du.print_stat(f"  {idx}. {label}", str(path) if isinstance(path, Path) and path else "missing")
    print("")
    print("Tune Next")
    for action in summary.get("tuning_actions", []):
        du.print_info(f"  {action}")
    if is_detailed_mode(str(summary.get("display_mode", ""))) or is_debug_mode(str(summary.get("display_mode", ""))):
        print("")
        print("Detailed paths")
        print("--------------")
        for label, path in (summary.get("advanced_paths") or {}).items():
            du.print_stat(label.replace("_", " "), str(path) if isinstance(path, Path) and path else "missing")


def launch_review_latest_run_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    open_run_science_index_action: Callable[[], int],
    launch_cohort_family_audit_action: Callable[[], None],
    launch_parser_vendor_coverage_action: Callable[[], None],
    launch_permission_intelligence_coverage_action: Callable[[], None],
    launch_feature_matrix_modality_action: Callable[[], None],
    launch_taxonomy_consistency_review_action: Callable[[], None],
    launch_run_overview_action: Callable[[], None],
    launch_compare_runs_action: Callable[[], None],
    launch_data_diagnostics_action: Callable[[], None],
    launch_reproducibility_action: Callable[[], None],
) -> None:
    """Primary operator decision flow for the latest run."""
    def _launch_review_history_compare_menu() -> None:
        while True:
            sub_choice = mu.display_menu(
                [
                    "Run history",
                    "Compare runs",
                ],
                title="Run history / compare runs",
                exit_label="Back",
                breadcrumb="Main menu › Review Latest Run › History / Compare",
            )
            if sub_choice == 0:
                return
            if sub_choice == 1:
                launch_run_overview_action()
                continue
            if sub_choice == 2:
                launch_compare_runs_action()
                continue
            du.print_warning("[MENU] Invalid choice received.")

    output_root = canonical_output_root()
    last_signature: tuple[object, ...] | None = None
    while True:
        latest_run_id = read_latest_run_id()
        summary = build_review_latest_run_summary(output_root=output_root, latest_run_id=latest_run_id)
        signature = (
            summary.get("run_id"),
            summary.get("profile_id"),
            summary.get("run_class"),
            summary.get("cohort_lock_status"),
            tuple((str(r.get("label", "")), str(r.get("status", ""))) for r in summary.get("health_rows", []) if isinstance(r, dict)),
            tuple(str(x) for x in summary.get("warnings", [])),
        )
        if signature != last_signature:
            print_compact_review_latest_run(output_root=output_root, latest_run_id=latest_run_id)
            last_signature = signature
        choice = mu.display_menu(
            [
                "Open run science index",
                "What needs attention?",
                "Cohort and label health",
                "Vendor/parser health",
                "Permission and feature health",
                "Ablation and signal contribution",
                "Figure/table validity",
                "Evidence and artifact provenance",
                "Run history / compare runs",
                "Advanced diagnostics",
            ],
            title="Review latest run",
            exit_label="Back",
            breadcrumb="Main menu › Review Latest Run",
            subtitle="Start here to understand what changed, what matters, and what to tune next.",
        )
        if choice == 0:
            return
        if choice == 1:
            open_run_science_index_action()
            continue
        if choice == 2:
            print_compact_review_latest_run(output_root=output_root, latest_run_id=latest_run_id)
            continue
        if choice == 3:
            launch_cohort_family_audit_action()
            continue
        if choice == 4:
            launch_parser_vendor_coverage_action()
            continue
        if choice == 5:
            launch_permission_intelligence_coverage_action()
            continue
        if choice == 6:
            launch_feature_matrix_modality_action()
            continue
        if choice == 7:
            launch_reproducibility_action()
            continue
        if choice == 8:
            launch_reproducibility_action()
            continue
        if choice == 9:
            _launch_review_history_compare_menu()
            continue
        if choice == 10:
            launch_data_diagnostics_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


__all__ = [
    "build_review_latest_run_summary",
    "launch_review_latest_run_menu",
    "print_compact_review_latest_run",
]
