"""State banners for Data Diagnostics vs Tools / Maintenance operator menus."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.cli.menu import vendor_diagnostics
from obsidiandroid.cli.menu.operator_state import build_operator_state
from obsidiandroid.cli.menu.run_locator import resolve_latest_manifest_payload
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.diagnostics.diagnostic_provenance import latest_post_run_enrichment_dir


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


def build_diagnostics_overview(*, output_root: Path, latest_run_id: str | None) -> dict[str, object]:
    """Build compact traffic-light overview for the latest run diagnostics."""
    shared = build_operator_state(output_base=output_root, run_id=latest_run_id)
    rid = str(latest_run_id or shared.get("latest_run_id") or "").strip()
    run_root = output_root / "runs" / rid if rid else Path()
    rdiag = run_root / "diagnostics" if rid else Path()
    gdiag = output_root / "diagnostics"
    publication_ready = str(shared.get("publication_ready_status", "") or "unknown")
    taxonomy = read_json_dict(rdiag / f"taxonomy_consistency_summary_{rid}.json") if rid else {}
    if not taxonomy:
        taxonomy = read_json_dict(gdiag / "taxonomy_consistency_summary.latest.json")
    q2 = read_json_dict(rdiag / "modality_contribution_summary.json") if rid else {}
    if not q2:
        q2 = read_json_dict(gdiag / "modality_contribution_summary.json")
    parser_state = shared.get("parser_summary") if isinstance(shared.get("parser_summary"), dict) else {}

    overview_rows = [
        {
            "label": "Cohort / labels",
            "status": _status_light((rdiag / "cohort_foundation.json").is_file() if rid else False),
            "action": "Open run science index",
        },
        {
            "label": "Taxonomy consistency",
            "status": _status_light(
                bool(taxonomy),
                warn=bool(taxonomy) and int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) > 0,
            ),
            "action": "Review taxonomy summary or generate post-run audit",
        },
        {
            "label": "Permission signal",
            "status": _status_light(bool(q2) and q2.get("permission_signal_pct") not in (None, "", "—")),
            "action": "View profile tuning snapshot",
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
                (rdiag / "feature_build_coverage.latest.json").is_file()
                or (rdiag / f"feature_build_coverage_{rid}.json").is_file()
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
            "label": "Publication readiness",
            "status": (
                "GREEN"
                if publication_ready in {"PASS", "ready"}
                else "RED"
                if publication_ready in {"FAIL", "not_ready"}
                else "YELLOW"
            ),
            "action": "Open evidence readiness summary",
        },
    ]
    return {
        "latest_run_id": rid,
        "run_science_index_path": str(shared.get("best_run_index_path", "") or ""),
        "run_science_index_canonical": bool(shared.get("has_canonical_run_science", False)),
        "rows": overview_rows,
    }


def print_compact_diagnostics_overview(*, output_root: Path, latest_run_id: str | None) -> None:
    """Print compact traffic-light overview with next actions."""
    from obsidiandroid.cli.ui import display as du

    overview = build_diagnostics_overview(output_root=output_root, latest_run_id=latest_run_id)
    du.print_subheader("Diagnostics overview")
    du.print_stat("Latest run", str(overview.get("latest_run_id") or "None yet"))
    rows = overview.get("rows") if isinstance(overview.get("rows"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        du.print_stat(str(row.get("label", "")), str(row.get("status", "")))
        du.print_info(f"  Recommended next action: {row.get('action', '')}")
    path = str(overview.get("run_science_index_path", "") or "")
    du.print_stat("Run science index", path or "missing")
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
        diag = output_root / "runs" / latest_run_id / "diagnostics"
        provenance = (diag / f"split_freeze_headline_{latest_run_id}.csv").exists() or (
            diag / f"split_freeze_audit_{latest_run_id}.csv"
        ).exists()
    du.print_stat("Diagnostics ready", "Yes" if provenance else "No")

    cov_path = vendor_diagnostics.resolve_vendor_parser_coverage_csv()
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
        rdiag = output_root / "runs" / latest_run_id / "diagnostics"
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
