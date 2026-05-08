"""State banners for Data Diagnostics vs Tools / Maintenance operator menus."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.cli.menu import vendor_diagnostics
from obsidiandroid.common.json_io import read_json_dict


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
    tax_n: str | int = "—"
    perm_pct: str | float = "—"
    vendor_pct: str | float = "—"
    if latest_run_id:
        rdiag = output_root / "runs" / latest_run_id / "diagnostics"
        fam_audit = (rdiag / "family_label_taxonomy_audit.csv").is_file()
        sup_prev = (rdiag / "support_threshold_preview.md").is_file()
        latest_tax = output_root / "diagnostics" / "taxonomy_consistency_summary.latest.json"
        tax = read_json_dict(rdiag / f"taxonomy_consistency_summary_{latest_run_id}.json") or read_json_dict(
            latest_tax
        )
        tax_n = tax.get("taxonomy_mismatch_count", tax.get("total_mismatch_count", "—"))
        q2 = read_json_dict(rdiag / "modality_contribution_summary.json")
        perm_pct = q2.get("permission_signal_pct", "—")
        vendor_pct = q2.get("vendor_merge_pct", "—")

    du.print_stat("Family label taxonomy audit", "Available" if fam_audit else "Missing")
    du.print_stat("Support threshold preview", "Available" if sup_prev else "Missing")
    du.print_stat("Taxonomy mismatches (summary)", str(tax_n))
    du.print_stat("Permission signal % (Q2)", str(perm_pct))
    du.print_stat("Vendor merge % (Q2)", str(vendor_pct))
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


__all__ = ["print_data_diagnostics_banner", "print_tools_maintenance_banner"]
