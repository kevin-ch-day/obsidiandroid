"""Primary operator review flow for the latest run."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.cohort_methodology import resolve_cohort_lock_status, safe_int
from obsidiandroid.common.publication_readiness import publication_ready_display
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot

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


def _run_class(*, evidence_mode: bool, locked_status: str, publication_ready_status: str) -> str:
    pub = str(publication_ready_status or "").strip().lower()
    locked = locked_status in {"locked", "count-only", "missing-lock"}
    if pub in {"ready", "pass"}:
        return "Publication-ready"
    if locked:
        return "Cohort-locked"
    if evidence_mode:
        return "Evidence"
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


def build_review_latest_run_summary(*, output_root: Path, latest_run_id: str | None) -> dict[str, object]:
    """Build operator-first summary for the latest run."""
    shared = build_operator_state(output_base=output_root, run_id=latest_run_id)
    rid = str(shared.get("latest_run_id", "") or "").strip()
    mode = str(shared.get("display_mode", "") or resolve_display_mode())
    run_root = output_root / "runs" / rid if rid else Path()
    rdiag = run_root / "diagnostics" if rid else Path()
    gdiag = output_root / "diagnostics"
    manifest = shared.get("manifest_payload") if isinstance(shared.get("manifest_payload"), dict) else {}
    profile_id = str(shared.get("profile_id", "") or "unknown")
    lock_status = str(shared.get("cohort_lock_status", "") or "").strip() or resolve_cohort_lock_status(manifest)
    publication_ready_status = str(shared.get("publication_ready_status", "") or "unknown")
    run_class = _run_class(
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
    readiness_signal = infer_cohort_readiness_signal(profile_id)

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
    if lock_status == "count-only":
        _append_warning(
            warnings,
            problem="Cohort lock: count-only lock.",
            why="row counts are governed, but exact sample-id membership is not fully reproducible from a locked snapshot",
            next_action="open the run science index and cohort funnel, then confirm whether this run is acceptable for exploratory review only",
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
    if rescued_unknown_consensus > 0:
        tuning_actions.append("Review rescued missing-consensus malware rows before raising or lowering the malicious-detection threshold.")
    if lock_status == "count-only":
        tuning_actions.append("Confirm that count-only cohort lock is acceptable for this review before using the run as a reproducible evidence baseline.")
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
        "permission_tuning_summary": permission_tuning,
        "cohort_readiness_summary": cohort_readiness,
        "cohort_readiness_signal": readiness_signal,
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
        du.print_stat("  min_samples_per_family", str(tax.get("min_samples_per_family", "—")))
        du.print_stat(
            "  Families retained/dropped",
            f"{tax.get('families_retained', '—')} / {tax.get('families_dropped', '—')}",
        )
        du.print_stat("  Samples dropped (estimate)", str(tax.get("samples_dropped_estimate", "—")))
        du.print_stat("  Families just below threshold", str(tax.get("families_just_below_threshold", "—")))
        sens = tax.get("threshold_sensitivity", [])
        if isinstance(sens, list) and sens:
            preview = []
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
