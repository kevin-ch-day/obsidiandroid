"""Data diagnostics submenu actions and control flow."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable


from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.repo_paths import repo_operator_script
from obsidiandroid.database.db_cohort_readiness import get_cohort_readiness_snapshot
from obsidiandroid.diagnostics.diagnostic_provenance import (
    latest_post_run_entry,
    latest_post_run_enrichment_dir,
)
import obsidiandroid.cli.profile_manager as profile_manager

from .menu.diagnostics import readiness_inventory as _readiness_inventory
from .menu.diagnostics import artifact_views as _artifact_views
from .menu.diagnostics import cohort_audit as _cohort_audit
from .menu.diagnostics import taxonomy_tuning as _taxonomy_tuning
from .menu import diagnostics_banners
from .menu import vendor_diagnostics
from .menu.display_mode import resolve_display_mode
from .ui import display as du
from .ui import menu as mu


def show_profile_readiness_mapping_inventory() -> int:
    """Print bundled profile-to-readiness mapping inventory (advisory only)."""
    return _readiness_inventory.show_profile_readiness_mapping_inventory(
        profile_manager_module=profile_manager,
        get_cohort_readiness_snapshot_fn=get_cohort_readiness_snapshot,
        display_module=du,
    )


def first_existing_path(candidates: list[Path]) -> Path | None:
    """Return the first existing regular file from a candidate list."""
    for path in candidates:
        if path.is_file():
            return path
    return None


def governed_cohort_n_for_q2(*, rdiag: Path, gdiag: Path, q2: dict) -> int | None:
    """Resolve the governed cohort denominator for compact Q2 menu summaries."""

    def _as_nonneg_int(val: object) -> int | None:
        if isinstance(val, bool):
            return None
        if isinstance(val, int) and val >= 0:
            return val
        if isinstance(val, float) and val >= 0 and val == int(val):
            return int(val)
        return None

    n = _as_nonneg_int(q2.get("governed_cohort_n"))
    if n is not None:
        return n
    q1 = read_json_dict(rdiag / "dataset_foundation_summary.json") or read_json_dict(
        gdiag / "dataset_foundation_summary.json"
    )
    gs = q1.get("governed_samples") if isinstance(q1, dict) else None
    n = _as_nonneg_int(gs)
    if n is not None:
        return n
    try:
        pn = int(q2.get("permission_signal_n") or 0)
        pp = float(q2.get("permission_signal_pct") or 0)
    except (TypeError, ValueError):
        return None
    if pn > 0 and pp > 0:
        return int(round(pn * 100.0 / pp))
    return None


def run_family_label_taxonomy_audit_script(
    *,
    read_latest_run_id: Callable[[], str | None],
    resolve_latest_manifest_payload: Callable[..., tuple[dict, str | None, Path]],
    resolve_and_validate_profile: Callable[..., str | None],
    load_profile: Callable[[str], object],
    operator_script_resolver: Callable[[str], Path] = repo_operator_script,
    subprocess_run: Callable[..., object] = subprocess.run,
) -> int:
    """Invoke the post-run family taxonomy audit script."""
    return _cohort_audit.run_family_label_taxonomy_audit_script(
        read_latest_run_id=read_latest_run_id,
        resolve_latest_manifest_payload=resolve_latest_manifest_payload,
        resolve_and_validate_profile=resolve_and_validate_profile,
        load_profile=load_profile,
        output_root=canonical_output_root(),
        operator_script_resolver=operator_script_resolver,
        subprocess_run=subprocess_run,
    )


def open_run_science_index(
    *,
    output_root: Path | None = None,
    read_latest_run_id: Callable[[], str | None] | None = None,
) -> int:
    """Print the best available authoritative run index path for the latest run."""
    read_latest_run_id_fn = read_latest_run_id or (lambda: None)
    return _cohort_audit.open_run_science_index(
        output_root=output_root or canonical_output_root(),
        read_latest_run_id=read_latest_run_id_fn,
    )


def print_cohort_family_artifact_paths(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """List canonical and enrichment cohort/family artifact paths for the latest run."""
    return _cohort_audit.print_cohort_family_artifact_paths(
        read_latest_run_id=read_latest_run_id,
        output_root=canonical_output_root(),
        latest_post_run_enrichment_dir_fn=latest_post_run_enrichment_dir,
        latest_post_run_entry_fn=latest_post_run_entry,
    )


def launch_cohort_family_audit_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    open_run_science_index_action: Callable[[], int],
    run_family_label_taxonomy_audit_action: Callable[[], int],
) -> None:
    """Launch the cohort/family audit submenu."""
    return _cohort_audit.launch_cohort_family_audit_menu(
        read_latest_run_id=read_latest_run_id,
        open_run_science_index_action=open_run_science_index_action,
        run_family_label_taxonomy_audit_action=run_family_label_taxonomy_audit_action,
        print_cohort_family_artifact_paths_action=print_cohort_family_artifact_paths,
    )


def launch_parser_vendor_coverage_menu() -> None:
    """Launch the parser/vendor coverage submenu."""
    last_state_sig: tuple[object, ...] | None = None
    while True:
        state = vendor_diagnostics.get_parser_summary_state()
        state_sig = (
            state.get("csv_ready"),
            state.get("workbook_ready"),
            state.get("observed_engines"),
            state.get("parser_mapped_vendors"),
            state.get("unmapped_vendors"),
            state.get("selected_vendors"),
            state.get("engine_scoring_universe"),
        )
        if last_state_sig != state_sig:
            vendor_diagnostics.print_parser_diagnostics_state()
            last_state_sig = state_sig
        display_mode = str(state.get("display_mode", "compact"))
        opts = [
            "Parser summary",
            "Parser onboarding workflow",
            "Selected vendor signal quality",
            "Workbook drill-down requirements",
            "Single-vendor parser drill-down",
        ]
        if display_mode != "compact":
            opts.extend(
                [
                    "Top unmapped vendors",
                    "Export paths",
                ]
            )
        choice = mu.display_menu(
            opts,
            title="Parser & vendor tuning",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics › Parser vendor",
        )
        if choice == 0:
            return
        if choice == 1:
            vendor_diagnostics.print_compact_vendor_coverage_snapshot()
            continue
        if choice == 2:
            vendor_diagnostics.print_parser_onboarding_candidates()
            continue
        if choice == 3:
            vendor_diagnostics.print_selected_vendors_for_latest_run()
            continue
        if choice == 4:
            vendor_diagnostics.print_workbook_requirements()
            continue
        if choice == 5:
            vendor_diagnostics.run_single_vendor_parser_check()
            continue
        if display_mode != "compact":
            if choice == 6:
                vendor_diagnostics.print_top_unmapped_vendors()
                continue
            if choice == 7:
                vendor_diagnostics.print_parser_export_paths()
                continue
        du.print_warning("[MENU] Invalid choice received.")


def launch_permission_intelligence_coverage_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Launch the permission intelligence coverage view."""
    return _artifact_views.launch_permission_intelligence_coverage_menu(
        read_latest_run_id=read_latest_run_id,
        output_root=canonical_output_root(),
        first_existing_path_fn=first_existing_path,
        governed_cohort_n_for_q2_fn=governed_cohort_n_for_q2,
    )


def launch_feature_matrix_modality_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Launch the feature matrix/modality coverage view."""
    return _artifact_views.launch_feature_matrix_modality_menu(
        read_latest_run_id=read_latest_run_id,
        output_root=canonical_output_root(),
        first_existing_path_fn=first_existing_path,
    )


def launch_taxonomy_consistency_review_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Launch the taxonomy consistency review view."""
    return _artifact_views.launch_taxonomy_consistency_review_menu(
        read_latest_run_id=read_latest_run_id,
        output_root=canonical_output_root(),
        first_existing_path_fn=first_existing_path,
    )


def launch_family_type_authority_coverage_menu() -> int:
    """Launch the family/type authority coverage view backed by the Erebus authority view."""
    return _artifact_views.launch_family_type_authority_coverage_menu(
        output_root=canonical_output_root(),
    )


def launch_taxonomy_support_tuning_compact_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Compact taxonomy/support tuning screen for next-run decisions."""
    return _taxonomy_tuning.launch_taxonomy_support_tuning_compact_menu(
        read_latest_run_id=read_latest_run_id,
        output_root=canonical_output_root(),
        first_existing_path_fn=first_existing_path,
        resolve_display_mode_fn=resolve_display_mode,
    )


def build_taxonomy_support_tuning_snapshot(*, run_id: str, output_root: Path) -> dict[str, object]:
    """Build compact taxonomy/support tuning snapshot from existing diagnostics artifacts."""
    return _taxonomy_tuning.build_taxonomy_support_tuning_snapshot(
        run_id=run_id,
        output_root=output_root,
        first_existing_path_fn=first_existing_path,
    )


def build_permission_coverage_tuning_snapshot(*, run_id: str, output_root: Path) -> dict[str, object]:
    """Build compact permission-coverage tuning snapshot from existing artifacts."""
    return _taxonomy_tuning.build_permission_coverage_tuning_snapshot(
        run_id=run_id,
        output_root=output_root,
        first_existing_path_fn=first_existing_path,
    )

def launch_data_diagnostics_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    show_profile_tuning_snapshot: Callable[[], int],
    open_run_science_index_action: Callable[[], int],
    launch_family_type_authority_coverage_action: Callable[[], int],
    launch_taxonomy_consistency_review_action: Callable[[], None],
    launch_parser_vendor_coverage_action: Callable[[], None],
    launch_permission_intelligence_coverage_action: Callable[[], None],
    launch_feature_matrix_modality_action: Callable[[], None],
    launch_cohort_family_audit_action: Callable[[], None],
) -> None:
    """Launch the top-level Data Diagnostics submenu."""
    output_root = canonical_output_root()
    last_overview_signature: tuple[object, ...] | None = None
    while True:
        latest_run_id = read_latest_run_id()
        overview = diagnostics_banners.build_diagnostics_overview(
            output_root=output_root,
            latest_run_id=latest_run_id,
        )
        signature = (
            overview.get("latest_run_id"),
            overview.get("run_science_index_path"),
            overview.get("run_science_index_canonical"),
            tuple(
                (str(row.get("label", "")), str(row.get("status", "")))
                for row in (overview.get("rows") if isinstance(overview.get("rows"), list) else [])
                if isinstance(row, dict)
            ),
        )
        if last_overview_signature != signature:
            diagnostics_banners.print_compact_diagnostics_overview(
                output_root=output_root,
                latest_run_id=latest_run_id,
            )
            last_overview_signature = signature
        data_sections = [
            "Open run science index",
            "Pipeline profile tuning (latest manifest)",
            "Profile readiness mapping inventory",
            "Taxonomy & Support Tuning",
            "Taxonomy Consistency Review",
            "Family/Type Authority Coverage",
            "Parser & Vendor Coverage",
            "Permission Intelligence Coverage",
            "Feature Matrix / Modality Coverage",
            "Cohort / Family Label Audit",
        ]
        choice = mu.display_menu(
            data_sections,
            title="Data diagnostics",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics",
            subtitle="View summaries first. Generate post-run audits only when needed.",
        )
        if choice == 0:
            return
        if choice == 1:
            open_run_science_index_action()
            continue
        if choice == 2:
            show_profile_tuning_snapshot()
            continue
        if choice == 3:
            show_profile_readiness_mapping_inventory()
            continue
        if choice == 4:
            launch_taxonomy_support_tuning_compact_menu(read_latest_run_id=read_latest_run_id)
            continue
        if choice == 5:
            launch_taxonomy_consistency_review_action()
            continue
        if choice == 6:
            launch_family_type_authority_coverage_action()
            continue
        if choice == 7:
            launch_parser_vendor_coverage_action()
            continue
        if choice == 8:
            launch_permission_intelligence_coverage_action()
            continue
        if choice == 9:
            launch_feature_matrix_modality_action()
            continue
        if choice == 10:
            launch_cohort_family_audit_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


__all__ = [
    "build_taxonomy_support_tuning_snapshot",
    "build_permission_coverage_tuning_snapshot",
    "first_existing_path",
    "governed_cohort_n_for_q2",
    "launch_cohort_family_audit_menu",
    "launch_data_diagnostics_menu",
    "launch_family_type_authority_coverage_menu",
    "launch_feature_matrix_modality_menu",
    "launch_parser_vendor_coverage_menu",
    "launch_permission_intelligence_coverage_menu",
    "launch_taxonomy_consistency_review_menu",
    "launch_taxonomy_support_tuning_compact_menu",
    "open_run_science_index",
    "print_cohort_family_artifact_paths",
    "run_family_label_taxonomy_audit_script",
    "show_profile_readiness_mapping_inventory",
]
