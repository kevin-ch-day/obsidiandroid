"""State banners for Data Diagnostics vs Tools / Maintenance operator menus."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.common.backlog_semantics import (
    assess_backlog_triage_health,
    choose_priority_triage,
    read_android_missing_resolution_snapshot,
    read_blank_resolved_triage_snapshot,
    read_false_positive_triage_snapshot,
    read_missing_primary_triage_snapshot,
    read_profile_family_mapping_debt_snapshot,
    triage_detail,
    triage_status,
)
from obsidiandroid.common.cohort_presentation import cohort_methodology_notes
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.publication_readiness import publication_ready_status_light
from obsidiandroid.cli.menu import run_locator
from obsidiandroid.cli.menu.operator_state import build_operator_state
from obsidiandroid.cli.menu.vendor_parser_state import resolve_vendor_parser_coverage_csv
from obsidiandroid.cli.menu.run_locator import resolve_latest_manifest_payload
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.diagnostics.diagnostic_provenance import latest_post_run_enrichment_dir
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot


def format_percent_for_menu(value: object, *, decimals: int = 2) -> str:
    """Format a 0–100 percentage scalar for operator-facing lines (stable width)."""
    if value in (None, "", "—"):
        return "—"
    try:
        f = float(str(value))
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return "—"
    return f"{f:.{decimals}f}%"


def _status_light(ok: bool | None, *, warn: bool = False) -> str:
    if ok is True and not warn:
        return "GREEN"
    if ok is False:
        return "RED"
    return "YELLOW"


def _severity_rank(status: str) -> int:
    token = str(status or "").strip().upper()
    if token == "RED":
        return 0
    if token == "YELLOW":
        return 1
    if token == "GREEN":
        return 2
    return 3


def _taxonomy_split_warn_count(payload: dict[str, object]) -> int:
    """Return the combined warning count from the taxonomy split payload."""
    if not isinstance(payload, dict) or not payload:
        return 0
    split = payload.get("taxonomy_split")
    if not isinstance(split, dict):
        return 0
    rendering = split.get("type_authority_vs_rendering_mismatch")
    counts = rendering.get("counts") if isinstance(rendering, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    model_prediction = split.get("model_prediction_error")
    model_count = int(model_prediction.get("count", 0) or 0) if isinstance(model_prediction, dict) else 0
    return model_count + sum(
        int(counts.get(key, 0) or 0)
        for key in (
            "type_mapping_mismatch",
            "type_label_missing",
            "type_label_noncanonical",
            "label_family_mismatch",
        )
    )


def _select_focus_row(
    *,
    rows: list[dict[str, object]],
    priority_triage: dict[str, object] | None,
) -> dict[str, str]:
    """Choose the highest-value operator focus item for diagnostics overview."""
    diagnostics_priority = {
        "Cohort / labels": 0,
        "Taxonomy consistency": 1,
        "Permission signal": 2,
        "Feature matrix": 3,
        "Evidence/provenance": 4,
        "Vendor/parser coverage": 5,
        "Claim readiness": 6,
        "Benchmark / publication readiness": 6,
        "Publication readiness": 6,
        "Missing-primary label triage": 6,
        "Blank resolved-family residue": 7,
        "Android missing-resolution triage": 8,
        "VT false-positive triage": 9,
        "Policy-held family noise": 10,
        "Profile family-mapping split": 11,
    }
    actionable: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "") or "").strip()
        status = str(row.get("status", "") or "").strip().upper()
        detail = str(row.get("detail", "") or "").strip()
        row_count = row.get("row_count")
        warning_flag = bool(row.get("warning", False))
        is_actionable = False
        if status in {"RED", "YELLOW"}:
            is_actionable = True
        elif isinstance(row_count, int) and row_count > 0:
            is_actionable = True
        elif warning_flag:
            is_actionable = True
        if not is_actionable:
            continue
        actionable.append(
            {
                "label": label,
                "status": status,
                "action": str(row.get("action", "") or "").strip(),
                "detail": detail,
                "_priority": diagnostics_priority.get(label, 99),
            }
        )
    if actionable:
        actionable.sort(
            key=lambda row: (
                _severity_rank(str(row.get("status", ""))),
                int(row.get("_priority", 99)),
                str(row.get("label", "")),
            )
        )
        top = actionable[0]
        return {
            "label": str(top.get("label", "") or ""),
            "reason": f"{str(top.get('status', '') or '').upper()}; {str(top.get('action', '') or '').strip()}",
            "action": str(top.get("action", "") or "").strip(),
        }
    if isinstance(priority_triage, dict) and priority_triage:
        return {
            "label": str(priority_triage.get("label", "") or ""),
            "reason": f"{str(priority_triage.get('freshness', '') or '').strip() or 'current'}; {str(priority_triage.get('action', '') or '').strip()}",
            "action": str(priority_triage.get("action", "") or "").strip(),
        }
    return {
        "label": "None — no actionable diagnostic backlog",
        "reason": "All tracked queues are green or empty.",
        "action": "Open run science index",
    }


def build_diagnostics_overview(*, output_root: Path, latest_run_id: str | None) -> dict[str, object]:
    """Build compact traffic-light overview for the latest run diagnostics."""
    shared = build_operator_state(output_base=output_root, run_id=latest_run_id)
    rid = str(latest_run_id or shared.get("latest_run_id") or "").strip()
    run_root = output_root / "runs" / rid if rid else Path()
    rdiag = run_root / "diagnostics" if rid else Path()
    gdiag = output_root / "diagnostics"
    publication_ready = str(shared.get("publication_ready_status", "") or "unknown")
    taxonomy_split = read_json_dict(rdiag / f"taxonomy_authority_split_{rid}.json") if rid else {}
    if not taxonomy_split:
        taxonomy_split = read_json_dict(gdiag / "taxonomy_authority_split.latest.json")
    taxonomy = read_json_dict(rdiag / f"taxonomy_consistency_summary_{rid}.json") if rid else {}
    if not taxonomy:
        taxonomy = read_json_dict(gdiag / "taxonomy_consistency_summary.latest.json")
    q2 = read_json_dict(rdiag / "modality_contribution_summary.json") if rid else {}
    if not q2:
        q2 = read_json_dict(gdiag / "modality_contribution_summary.json")
    parser_state = shared.get("parser_summary") if isinstance(shared.get("parser_summary"), dict) else {}
    evidence_mode = bool(shared.get("evidence_mode", False))
    publication_mode = bool(shared.get("publication_ready_mode", False))
    fp_triage = read_false_positive_triage_snapshot(output_root=output_root)
    android_triage = read_android_missing_resolution_snapshot(output_root=output_root)
    missing_primary_triage = read_missing_primary_triage_snapshot(output_root=output_root)
    blank_resolved_triage = read_blank_resolved_triage_snapshot(output_root=output_root)
    profile_mapping_debt = read_profile_family_mapping_debt_snapshot(output_root=output_root)
    fp_triage_count = int(fp_triage.get("row_count", 0)) if fp_triage else None
    android_triage_count = int(android_triage.get("row_count", 0)) if android_triage else None
    fp_triage_top_lane = (
        (str(fp_triage.get("top_lane", "") or ""), int(fp_triage.get("top_lane_count", 0)))
        if fp_triage and str(fp_triage.get("top_lane", "") or "").strip()
        else None
    )
    android_triage_top_lane = (
        (str(android_triage.get("top_lane", "") or ""), int(android_triage.get("top_lane_count", 0)))
        if android_triage and str(android_triage.get("top_lane", "") or "").strip()
        else None
    )
    fp_triage_freshness = str(fp_triage.get("freshness", "") or "").strip() if fp_triage else "missing"
    android_triage_freshness = (
        str(android_triage.get("freshness", "") or "").strip() if android_triage else "missing"
    )
    priority_triage = choose_priority_triage(
        android_missing_triage=android_triage,
        fp_triage=fp_triage,
        missing_primary_triage=missing_primary_triage,
    )
    readiness_payload: dict[str, object] = {}
    try:
        readiness_payload = get_cohort_readiness_snapshot()
    except Exception:
        readiness_payload = {}
    taxonomy_signals = (
        readiness_payload.get("taxonomy_signals", {})
        if isinstance(readiness_payload, dict)
        else {}
    )
    if not isinstance(taxonomy_signals, dict):
        taxonomy_signals = {}
    policy_held_family_samples = int(taxonomy_signals.get("policy_held_family_samples", 0) or 0)
    blank_resolved_family_samples = int(taxonomy_signals.get("blank_resolved_family_samples", 0) or 0)
    missing_primary_samples = int(taxonomy_signals.get("missing_primary_label_samples", 0) or 0)
    backlog_triage_health = assess_backlog_triage_health(
        readiness=readiness_payload,
        android_missing_triage=android_triage,
        fp_triage=fp_triage,
        missing_primary_triage=missing_primary_triage,
        profile_mapping_debt=profile_mapping_debt,
        blank_resolved_triage=blank_resolved_triage,
    )
    policy_held_generic_count = 0
    token_kind_counts = taxonomy_signals.get("policy_held_family_token_kind_counts", {})
    if isinstance(token_kind_counts, dict):
        policy_held_generic_count = int(token_kind_counts.get("generic_family_token", 0) or 0)
    readiness_label = "Publication readiness" if (publication_mode or evidence_mode) else "Claim readiness"

    overview_rows = [
        {
            "label": "Cohort / labels",
            "status": _status_light((rdiag / "cohort_foundation.json").is_file() if rid else False),
            "action": "Open run science index",
        },
        {
            "label": "Taxonomy consistency",
            "status": _status_light(
                bool(taxonomy_split or taxonomy),
                warn=(bool(taxonomy_split) and _taxonomy_split_warn_count(taxonomy_split) > 0) or (
                    bool(taxonomy) and int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) > 0
                ),
            ),
            "action": "Review taxonomy authority split or post-run audit",
        },
        {
            "label": "Permission signal",
            "status": _status_light(bool(q2) and q2.get("permission_signal_pct") not in (None, "", "—")),
            "action": "View profile tuning snapshot",
        },
        {
            "label": "Missing-primary label triage",
            "status": triage_status(
                row_count=int(missing_primary_triage.get("row_count", 0) or 0) if missing_primary_triage else None,
                freshness=str(missing_primary_triage.get("freshness", "") or "").strip() if missing_primary_triage else "missing",
            ),
            "action": (
                "Refresh missing-primary label triage export first"
                if str(missing_primary_triage.get("freshness", "") or "").strip() == "stale"
                else "Open missing-primary label triage"
            ),
            "row_count": int(missing_primary_triage.get("row_count", 0) or 0) if missing_primary_triage else 0,
            "detail": triage_detail(
                int(missing_primary_triage.get("row_count", 0) or 0) if missing_primary_triage else None,
                noun="active residual row(s)",
                top_bucket=(
                    (str(missing_primary_triage.get("top_lane", "") or ""), int(missing_primary_triage.get("top_lane_count", 0)))
                    if missing_primary_triage and str(missing_primary_triage.get("top_lane", "") or "").strip()
                    else None
                ),
                freshness=str(missing_primary_triage.get("freshness", "") or "").strip() if missing_primary_triage else "missing",
            ),
        },
        {
            "label": "Blank resolved-family residue",
            "status": triage_status(
                row_count=int(blank_resolved_triage.get("row_count", 0) or 0) if blank_resolved_triage else None,
                freshness=str(blank_resolved_triage.get("freshness", "") or "").strip() if blank_resolved_triage else "missing",
            ),
            "action": "Open blank-resolved family triage",
            "row_count": int(blank_resolved_triage.get("row_count", 0) or 0) if blank_resolved_triage else 0,
            "detail": (
                f"{int(blank_resolved_triage.get('row_count', 0) or 0)} outside missing-resolution view; "
                f"live blank_resolved={blank_resolved_family_samples}"
                if blank_resolved_triage
                else f"live blank_resolved={blank_resolved_family_samples}"
            ),
        },
        {
            "label": "Android missing-resolution triage",
                "status": triage_status(
                    row_count=android_triage_count,
                    freshness=android_triage_freshness,
                ),
                "action": (
                    "Refresh Android missing-resolution triage export first"
                    if android_triage_freshness == "stale"
                    else "Open Android missing-resolution triage"
                ),
                "row_count": android_triage_count if android_triage_count is not None else 0,
                "detail": triage_detail(
                    android_triage_count,
                    noun="queued row(s)",
                    top_bucket=android_triage_top_lane,
                    freshness=android_triage_freshness,
                ),
        },
        {
            "label": "VT false-positive triage",
                "status": triage_status(
                    row_count=fp_triage_count,
                    freshness=fp_triage_freshness,
                ),
                "action": (
                    "Refresh VT false-positive triage export first"
                    if fp_triage_freshness == "stale"
                    else "Open VT false-positive triage"
                ),
                "row_count": fp_triage_count if fp_triage_count is not None else 0,
                "detail": triage_detail(
                    fp_triage_count,
                    noun="review row(s)",
                    top_bucket=fp_triage_top_lane,
                    freshness=fp_triage_freshness,
                ),
        },
        {
            "label": "Profile family-mapping split",
            "status": "YELLOW" if int(profile_mapping_debt.get("excluded_unmapped_family_rows", 0) or 0) > 0 else "GREEN",
            "action": "Open profile family-mapping debt export",
            "row_count": int(profile_mapping_debt.get("excluded_unmapped_family_rows", 0) or 0),
            "detail": (
                f"blank={int(profile_mapping_debt.get('blank_resolved_slug_rows', 0) or 0)}; "
                f"policy_held={int(profile_mapping_debt.get('policy_held_resolved_slug_rows', 0) or 0)}; "
                f"true_unmapped={int(profile_mapping_debt.get('true_unmapped_resolved_slug_rows', 0) or 0)}"
                if profile_mapping_debt
                else "export missing"
            ),
        },
        {
            "label": "Policy-held family noise",
            "status": "YELLOW" if policy_held_generic_count > 0 else "GREEN",
            "action": "Review policy-held token risk export",
            "row_count": policy_held_family_samples,
            "warning": policy_held_generic_count > 0,
            "detail": (
                f"{policy_held_family_samples} rows, review only"
                if policy_held_family_samples > 0
                else "0 rows"
            ),
        },
        {
            "label": "Vendor/parser coverage",
            "status": _status_light(
                bool(parser_state.get("csv_ready", False)),
                warn=bool(parser_state.get("csv_ready", False)) and not bool(parser_state.get("workbook_ready", False)),
            ),
            "action": "Open parser summary",
        },
        {
            "label": "Feature matrix",
            "status": _status_light(
                oh.resolve_feature_build_coverage_path(rdiag, rid).is_file()
                or (rdiag / "feature_contract.json").is_file()
                if rid
                else False
            ),
            "action": "Open feature matrix / modality coverage",
        },
        {
            "label": "Evidence/provenance",
            "status": _status_light(
                bool(shared.get("best_run_index_path")) and (rdiag / "diagnostic_provenance.json").is_file(),
                warn=rid and (not bool(shared.get("has_canonical_run_science", False))) and bool(shared.get("best_run_index_path")),
            ),
            "action": "Open run science index",
        },
        {
            "label": readiness_label,
            "status": publication_ready_status_light(publication_ready),
            "action": "Open evidence readiness summary",
        },
    ]
    cohort_membership_mode = str(shared.get("cohort_membership_mode", "") or "").strip()
    rescued_unknown_consensus = int(
        shared.get("min_malicious_detections_rescued_unknown_consensus", 0) or 0
    )
    return {
        "latest_run_id": rid,
        "run_science_index_path": str(shared.get("best_run_index_path", "") or ""),
        "run_science_index_canonical": bool(shared.get("has_canonical_run_science", False)),
        "cohort_membership_mode": cohort_membership_mode or "standard_contract_filters",
        "rescued_unknown_consensus": rescued_unknown_consensus,
        "priority_triage": priority_triage,
        "backlog_triage_health": backlog_triage_health,
        "focus_item": _select_focus_row(rows=overview_rows, priority_triage=priority_triage),
        "rows": overview_rows,
    }


def print_compact_diagnostics_overview(*, output_root: Path, latest_run_id: str | None) -> None:
    """Print compact traffic-light overview with next actions."""

    def _row_is_actionable(row: dict[str, object]) -> bool:
        status = str(row.get("status", "") or "").strip().upper()
        row_count = row.get("row_count")
        warning_flag = bool(row.get("warning", False))
        if status in {"RED", "YELLOW"}:
            return True
        if isinstance(row_count, int) and row_count > 0:
            return True
        return warning_flag

    overview = build_diagnostics_overview(output_root=output_root, latest_run_id=latest_run_id)
    du.print_subheader("Diagnostics overview")
    du.print_stat("Latest run", str(overview.get("latest_run_id") or "None yet"))
    focus_item = overview.get("focus_item", {})
    if isinstance(focus_item, dict) and focus_item:
        du.print_stat("Focus first", str(focus_item.get("label", "—")))
        reason = str(focus_item.get("reason", "") or "").strip()
        if reason:
            print(f"  Reason: {reason}")
        action = str(focus_item.get("action", "") or "").strip()
        if action:
            label = "Suggested next" if str(focus_item.get("label", "")).startswith("None ") else "Next"
            print(f"  {label}: {action}")
    rows = overview.get("rows") if isinstance(overview.get("rows"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        du.print_stat(str(row.get("label", "")), str(row.get("status", "")))
        detail = str(row.get("detail", "") or "").strip()
        detail = detail.replace("top=real_malware_family_or_class_review", "top=real malware family/class…")
        if detail:
            print(f"  Backlog: {detail}")
        action = str(row.get("action", "") or "").strip()
        if action and _row_is_actionable(row):
            print(f"  Next: {action}")
    for note in cohort_methodology_notes(
        {
            "cohort_membership_mode": overview.get("cohort_membership_mode", ""),
            "min_malicious_detections_rescued_unknown_consensus": overview.get("rescued_unknown_consensus", 0),
        }
    ):
        du.print_note(note)
    path = str(overview.get("run_science_index_path", "") or "")
    du.print_stat("Run science index", du.format_console_path(path) if path else "missing")
    if path and not bool(overview.get("run_science_index_canonical", False)):
        du.print_note("Canonical run_science_index.md is missing; showing the best available authoritative run index.")
    print("")


def print_data_diagnostics_banner(*, output_root: Path, latest_run_id: str | None) -> None:
    """Summarize data-quality artifact availability for the latest run."""
    from obsidiandroid.cli.ui import display as du

    rid = str(latest_run_id or "").strip() or "None yet"
    du.print_subheader("Data diagnostics state")
    du.print_stat("Latest run", rid)
    provenance = False
    if latest_run_id:
        diag = run_locator.resolve_run_root_for_run_id(latest_run_id, output_base=output_root) / "diagnostics"
        provenance = (diag / f"split_freeze_headline_{latest_run_id}.csv").exists()
    du.print_stat("Diagnostics ready", "Yes" if provenance else "No")

    cov_path = resolve_vendor_parser_coverage_csv()
    du.print_stat("Vendor coverage CSV", "Available" if cov_path is not None else "Missing")

    fam_audit = False
    sup_prev = False
    fam_audit_post = False
    sup_prev_post = False
    tax_n: str | int = "—"
    perm_pct: str | float = "—"
    vendor_pct: str | float = "—"
    frozen_profile = "—"
    if latest_run_id:
        rdiag = run_locator.resolve_run_root_for_run_id(latest_run_id, output_base=output_root) / "diagnostics"
        fam_audit = (rdiag / "family_label_taxonomy_audit.csv").is_file()
        sup_prev = (rdiag / "support_threshold_preview.md").is_file()
        latest_enrichment = latest_post_run_enrichment_dir(rdiag)
        if latest_enrichment is not None:
            fam_audit_post = (latest_enrichment / "family_label_taxonomy_audit.csv").is_file()
            sup_prev_post = (latest_enrichment / "support_threshold_preview.md").is_file()
        latest_tax = output_root / "diagnostics" / "taxonomy_consistency_summary.latest.json"
        tax = read_json_dict(rdiag / f"taxonomy_consistency_summary_{latest_run_id}.json") or read_json_dict(
            latest_tax
        )
        tax_n = tax.get("taxonomy_mismatch_count", tax.get("total_mismatch_count", "—"))
        q2 = read_json_dict(rdiag / "modality_contribution_summary.json") or read_json_dict(
            output_root / "diagnostics" / "modality_contribution_summary.json"
        )
        perm_pct = q2.get("permission_signal_pct", "—")
        vendor_pct = q2.get("vendor_merge_pct", "—")
        man, _, _ = resolve_latest_manifest_payload(output_base=output_root)
        pp = man.get("profile_params") if isinstance(man.get("profile_params"), dict) else {}
        frozen_profile = "Available" if pp else "Missing"

    du.print_stat("Family label taxonomy audit (pipeline-native)", "Available" if fam_audit else "Missing")
    du.print_stat("Support threshold preview (pipeline-native)", "Available" if sup_prev else "Missing")
    du.print_stat("Family taxonomy audit (post-run)", "Available" if fam_audit_post else "Missing")
    du.print_stat("Support threshold preview (post-run)", "Available" if sup_prev_post else "Missing")
    du.print_stat("Taxonomy mismatches (summary)", str(tax_n))
    du.print_stat(
        "Permission signal % (Q2)",
        format_percent_for_menu(perm_pct) if latest_run_id else "—",
    )
    du.print_stat(
        "Vendor merge % (Q2)",
        format_percent_for_menu(vendor_pct) if latest_run_id else "—",
    )
    du.print_stat(
        "Frozen profile_params (manifest)",
        frozen_profile,
    )
    du.print_info(
        "[MENU] Structural diagnostics bundle: generate under Research Reports → Structural Analysis (not here)."
    )
    print("")


def print_tools_maintenance_banner(*, output_root: Path, latest_run_id: str | None, locked_run_id: str | None) -> None:
    """Operational context: outputs, run inventory, evidence lock."""
    from obsidiandroid.cli.ui import display as du

    runs_root = output_root / "runs"
    run_count = 0
    if runs_root.is_dir():
        run_count = sum(1 for p in runs_root.iterdir() if p.is_dir())

    pointer_stale = "Unknown"
    latest_pointer = output_root / "diagnostics" / "run_manifest.latest.json"
    if latest_pointer.is_file() and latest_run_id:
        ptr = read_json_dict(latest_pointer)
        ptr_rid = str(ptr.get("run_id", "") or "").strip()
        pointer_stale = "Maybe" if ptr_rid and ptr_rid != latest_run_id else "Aligned"

    du.print_subheader("Tools / maintenance state")
    du.print_stat("Latest run", str(latest_run_id or "None yet"))
    du.print_stat("Output root", str(output_root.resolve()))
    du.print_stat("Run folders (count)", str(run_count))
    du.print_stat("run_manifest.latest vs newest run", pointer_stale)
    du.print_stat("Evidence-locked run", str(locked_run_id or "none"))
    du.print_stat(
        "Cleanup / disk",
        "Smart Output Cleanup and Show Disk Usage Summary in this menu.",
    )
    print("")


__all__ = [
    "build_diagnostics_overview",
    "format_percent_for_menu",
    "print_compact_diagnostics_overview",
    "print_data_diagnostics_banner",
    "print_tools_maintenance_banner",
]
