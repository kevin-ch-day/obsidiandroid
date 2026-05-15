"""Data diagnostics submenu actions and control flow."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Callable

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.repo_paths import repo_operator_script
from obsidiandroid.diagnostics.diagnostic_provenance import (
    latest_post_run_entry,
    latest_post_run_enrichment_dir,
)
from obsidiandroid.governance import paper_cohort_contract

from .menu import diagnostics_banners
from .menu import vendor_diagnostics
from .menu.display_mode import resolve_display_mode
from .menu.operator_state import build_operator_state
from .ui import display as du
from .ui import menu as mu


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
) -> int:
    """Invoke the post-run family taxonomy audit script."""
    script_path = operator_script_resolver("family_label_taxonomy_audit.py")
    if not script_path.is_file():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1

    du.print_section("Family label taxonomy audit")
    du.print_info(
        "Loads the labeled cohort from the database using a profile's gates (same path as pipeline samples; no training)."
    )
    du.print_info(
        "Writes taxonomy audit CSV/MD under the diagnostics dir below. "
        "When targeting a latest run, post-run artifacts are isolated under "
        "`diagnostics/post_run_enrichments/<audit_id>/` instead of being mixed into canonical run evidence. "
        "If cohort snapshot export is enabled, analysis_snapshot_*.csv/.meta.txt land in the same audit directory."
    )
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    latest_manifest, _, _ = resolve_latest_manifest_payload(output_base=output_root)
    latest_profile = ""
    if isinstance(latest_manifest.get("profile_params"), dict):
        latest_profile = str(latest_manifest["profile_params"].get("profile_id", "") or "").strip()
    diag_args: list[str] = []
    if rid:
        rdiag = output_root / "runs" / rid / "diagnostics"
        rdiag.mkdir(parents=True, exist_ok=True)
        diag_args = ["--diagnostics-dir", str(rdiag.resolve())]
        du.print_info(
            f"Target diagnostics dir: runs/{rid}/diagnostics/post_run_enrichments/<audit_id>/ "
            "(taxonomy audit + cohort snapshot artifacts when snapshot export is on)."
        )
    else:
        du.print_note(
            "No latest run id — the script will use output/diagnostics/taxonomy_audit_<timestamp>/ instead."
        )

    du.print_stat("Latest run profile", latest_profile or "unknown")
    profile_id: str | None = None
    if latest_profile:
        choice = mu.display_menu(
            [
                f"Use same profile as latest run ({latest_profile})",
                "Choose a different profile",
            ],
            title="Taxonomy audit profile",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics › Cohort › Taxonomy audit",
            subtitle="Default is the same profile as the latest run.",
            default_choice=1,
        )
        if choice == 0:
            du.print_warning("[MENU] Taxonomy audit cancelled (no profile).")
            return 1
        if choice == 1:
            profile_id = latest_profile
        elif choice == 2:
            profile_id = resolve_and_validate_profile(
                prefer_quick=True,
                menu_breadcrumb="Main menu › Data Diagnostics › Cohort › Taxonomy audit",
                menu_title="Profile for post-run audit",
                menu_subtitle=(
                    "Choose a different cohort definition for this post-run audit. "
                    "Blank Enter selects the default highlighted row; 0 = Back."
                ),
            )
    else:
        profile_id = resolve_and_validate_profile(
            prefer_quick=True,
            menu_breadcrumb="Main menu › Data Diagnostics › Cohort › Taxonomy audit",
            menu_title="Profile for post-run audit",
            menu_subtitle=(
                "Choose which cohort definition to audit. Blank Enter selects the default highlighted row; 0 = Back."
            ),
        )
    if not profile_id:
        du.print_warning("[MENU] Taxonomy audit cancelled (no profile).")
        return 1
    if latest_profile and profile_id != latest_profile:
        du.print_warning("[MENU] Different profile than latest run.")
        du.print_stat("Latest run profile", latest_profile)
        du.print_stat("Audit profile", profile_id)
        if not mu.confirm_prompt("Continue with a different profile? [y/N]"):
            du.print_warning("[MENU] Taxonomy audit cancelled.")
            return 1
    try:
        selected_profile = load_profile(profile_id)
    except Exception as exc:
        du.print_error(f"[MENU] Failed to load selected profile '{profile_id}': {exc}")
        return 1
    contract = paper_cohort_contract.build_declared_contract(selected_profile)
    if bool(contract.get("paper_locked", False)):
        du.print_stat("Cohort lock enforcement", str(contract.get("cohort_lock_status", "unknown")))
        du.print_info("[MENU] Locked profile selected: the audit will enforce the cohort lock.")
    else:
        du.print_stat("Cohort lock enforcement", "not locked")
    cmd = [sys.executable, str(script_path), "--profile", profile_id, *diag_args]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


def open_run_science_index(
    *,
    output_root: Path | None = None,
    read_latest_run_id: Callable[[], str | None] | None = None,
) -> int:
    """Print the best available authoritative run index path for the latest run."""
    rid = str(read_latest_run_id() or "").strip() if read_latest_run_id is not None else ""
    shared = build_operator_state(output_base=output_root, run_id=rid or None)
    rid = rid or str(shared.get("latest_run_id", "") or "")
    if not rid:
        du.print_warning("[MENU] No latest run — run science index is unavailable.")
        return 1
    path_obj = shared.get("best_run_index_path")
    path = path_obj if isinstance(path_obj, Path) else Path(str(path_obj or ""))
    root = output_root or canonical_output_root()
    canonical = root / "runs" / rid / "diagnostics" / "run_science_index.md"
    du.print_section("Run science index")
    du.print_stat("Latest run", rid)
    du.print_stat("Open run science index", str(path.resolve()))
    if canonical.is_file():
        return 0
    if path.is_file():
        du.print_note("Canonical run_science_index.md is missing for this run.")
        du.print_info("Using the best available authoritative run index instead.")
        return 1
    du.print_warning("[MENU] No authoritative run index was found for this run.")
    return 0


def print_cohort_family_artifact_paths(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """List canonical and enrichment cohort/family artifact paths for the latest run."""
    du.print_section("Cohort / family artifact paths")
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run — nothing to resolve.")
        return
    rdiag = (output_root / "runs" / rid / "diagnostics").resolve()
    gdiag = (output_root / "diagnostics").resolve()

    def stat(label: str, path: Path) -> None:
        du.print_stat(label, "present" if path.is_file() else "missing")

    du.print_stat("Run diagnostics dir", str(rdiag))

    rows: list[tuple[str, Path]] = [
        ("family_label_taxonomy_audit.csv", rdiag / "family_label_taxonomy_audit.csv"),
        ("family_label_taxonomy_audit.md", rdiag / "family_label_taxonomy_audit.md"),
        ("support_threshold_preview.md", rdiag / "support_threshold_preview.md"),
        ("support_threshold_preview.csv", rdiag / "support_threshold_preview.csv"),
        ("family_distribution.csv", rdiag / "family_distribution.csv"),
        ("low_support_families.csv", rdiag / "low_support_families.csv"),
        ("dataset_foundation_summary.md", rdiag / "dataset_foundation_summary.md"),
        ("dataset_foundation_summary.json", rdiag / "dataset_foundation_summary.json"),
        (f"cohort_filter_contract_{rid}.json", rdiag / f"cohort_filter_contract_{rid}.json"),
        (f"cohort_gate_counts_{rid}.csv", rdiag / f"cohort_gate_counts_{rid}.csv"),
        ("cohort_lock_summary.json", rdiag / "cohort_lock_summary.json"),
        ("cohort_membership.csv", rdiag / "cohort_membership.csv"),
        (f"analysis_snapshot_filter_summary_{rid}.csv", rdiag / f"analysis_snapshot_filter_summary_{rid}.csv"),
        (f"analysis_snapshot_{rid}.csv", rdiag / f"analysis_snapshot_{rid}.csv"),
        (f"analysis_snapshot_{rid}.meta.txt", rdiag / f"analysis_snapshot_{rid}.meta.txt"),
        (
            f"analysis_snapshot_label_conflicts_{rid}.csv",
            rdiag / f"analysis_snapshot_label_conflicts_{rid}.csv",
        ),
        ("paper_cohort_sample_ids.csv", rdiag / "paper_cohort_sample_ids.csv"),
        ("dataset_time_contract (resolved)", oh.resolve_dataset_time_contract_path(rdiag, rid)),
        ("family_distribution_2020_present.csv", rdiag / "family_distribution_2020_present.csv"),
        ("family_distribution_by_year.csv", rdiag / "family_distribution_by_year.csv"),
    ]
    for label, path in rows:
        stat(label, path)

    latest_enrichment = latest_post_run_enrichment_dir(rdiag)
    if latest_enrichment is not None:
        latest_entry = latest_post_run_entry(rdiag) or {}
        du.print_subheader(f"Latest post-run enrichment audit ({latest_enrichment.name})")
        du.print_stat("Audit dir", str(latest_enrichment))
        if latest_entry:
            du.print_stat("Audit profile", str(latest_entry.get("audit_profile", "") or "unknown"))
            du.print_stat("Target run profile", str(latest_entry.get("target_run_profile", "") or "unknown"))
            du.print_stat(
                "Same profile as target",
                "yes" if bool(latest_entry.get("same_profile_as_target", False)) else "no",
            )
            du.print_stat("Cohort lock status", str(latest_entry.get("cohort_lock_status", "") or "unknown"))
        for label in (
            "family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit.md",
            "support_threshold_preview.md",
            "support_threshold_preview.csv",
        ):
            stat(label, latest_enrichment / label)

    primary_snap = rdiag / f"analysis_snapshot_{rid}.csv"
    primary_filter = rdiag / f"analysis_snapshot_filter_summary_{rid}.csv"
    extra_snaps = sorted(
        p
        for p in rdiag.glob("analysis_snapshot_*.csv")
        if p.is_file() and p not in {primary_snap, primary_filter}
    )
    if extra_snaps:
        du.print_subheader("Other analysis_snapshot_*.csv (adhoc / taxonomy audit)")
        for p in extra_snaps[:10]:
            stat(p.name, p)
        if len(extra_snaps) > 10:
            du.print_note(f"… plus {len(extra_snaps) - 10} more under this diagnostics dir")

    latest_snap = gdiag / "analysis_snapshot.latest.csv"
    latest_meta = gdiag / "analysis_snapshot.latest.meta.txt"
    if latest_snap.is_file() or latest_meta.is_file():
        du.print_subheader("Global diagnostics (operator .latest mirrors)")
        stat(str(gdiag / "analysis_snapshot.latest.csv"), latest_snap)
        stat(str(gdiag / "analysis_snapshot.latest.meta.txt"), latest_meta)

    print("")


def launch_cohort_family_audit_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    open_run_science_index_action: Callable[[], int],
    run_family_label_taxonomy_audit_action: Callable[[], int],
) -> None:
    """Launch the cohort/family audit submenu."""
    while True:
        opts = [
            "Show cohort / family artifact paths (canonical run + enrichments + mirrors)",
            "Open run science index",
            "Generate post-run audit",
        ]
        choice = mu.display_menu(
            opts,
            title="Cohort / family label audit",
            exit_label="Back",
            breadcrumb="Main menu › Data Diagnostics › Cohort",
        )
        if choice == 0:
            return
        if choice == 1:
            print_cohort_family_artifact_paths(read_latest_run_id=read_latest_run_id)
            continue
        if choice == 2:
            open_run_science_index_action()
            continue
        if choice == 3:
            run_family_label_taxonomy_audit_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


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
    du.print_section("Permission intelligence coverage")
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"

    rows: list[tuple[str, list[Path]]] = [
        ("Permission coverage summary", [rdiag / "permission_coverage_summary.csv", gdiag / "permission_coverage_summary.csv"]),
        ("Dataset foundation (JSON)", [rdiag / "dataset_foundation_summary.json", gdiag / "dataset_foundation_summary.json"]),
        ("Dataset foundation (gates + cohort)", [rdiag / "dataset_foundation_summary.md", gdiag / "dataset_foundation_summary.md"]),
        ("Modality contribution (Markdown)", [rdiag / "modality_contribution_summary.md", gdiag / "modality_contribution_summary.md"]),
        ("Modality contribution (JSON, Q2 metrics)", [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"]),
        ("Feature-set ablation (CSV)", [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"]),
        ("Feature-set ablation (Markdown)", [rdiag / "feature_set_ablation_summary.md", gdiag / "feature_set_ablation_summary.md"]),
        ("Vendor feature coverage summary", [rdiag / "vendor_feature_coverage_summary.csv", gdiag / "vendor_feature_coverage_summary.csv"]),
        ("Feature group survival (from column survival)", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
        (
            "Permission feature audit",
            [rdiag / "permission_feature_audit.csv", rdiag / f"permission_feature_audit_{rid}.csv"],
        ),
        ("Vendor leakage safety audit", [rdiag / "vendor_leakage_safety_audit.csv", gdiag / "vendor_leakage_safety_audit.csv"]),
        ("Permission signal quality (CSV)", [rdiag / "permission_signal_quality.csv", gdiag / "permission_signal_quality.csv"]),
        (
            "Permission signal quality (report)",
            [rdiag / "permission_signal_quality_report.md", gdiag / "permission_signal_quality_report.md"],
        ),
    ]
    for label, candidates in rows:
        hit = first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")

    q2 = read_json_dict(rdiag / "modality_contribution_summary.json") or read_json_dict(
        gdiag / "modality_contribution_summary.json"
    )
    if isinstance(q2, dict) and q2:
        du.print_subheader("Q2 snapshot (modality contribution)")
        gov_n = governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2=q2)
        du.print_stat("Governed cohort (denominator)", str(gov_n) if gov_n is not None else "—")
        du.print_stat(
            "Permission signal",
            f"{q2.get('permission_signal_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('permission_signal_pct'))})",
        )
        du.print_stat(
            "Vendor merge authority",
            f"{q2.get('vendor_merge_n', '—')} rows ({diagnostics_banners.format_percent_for_menu(q2.get('vendor_merge_pct'))})",
        )
        pcols = q2.get("permission_feature_columns")
        du.print_stat(
            "Permission columns (fused / contract)",
            "—" if pcols is None or pcols == "" else str(pcols),
        )
        du.print_stat(
            "AV engines (observed / included in contract)",
            f"{q2.get('av_engines_observed', '—')} / {q2.get('av_engines_included', '—')}",
        )
        notes = q2.get("interpretation_notes")
        if isinstance(notes, list) and notes:
            du.print_subheader("Q2 interpretation (from JSON)")
            for line in notes[:5]:
                if isinstance(line, str) and line.strip():
                    du.print_note(line.strip())
        du.print_note(
            "Definitions: `permission_signal_pct` = cohort rows with permission-bag signal ÷ governed cohort; "
            "`vendor_merge_pct` = rows with parsed vendor merge authority ÷ the same denominator."
        )
    else:
        du.print_note(
            "No modality_contribution_summary.json found for this run (or global mirror). "
            "Generate Q1–Q3 diagnostics for the run to populate Q2 permission intelligence."
        )

    du.print_info(
        "[MENU] Prefer run paths above; global output/diagnostics/ holds .latest mirrors when hygiene mode omits duplicates inside runs/. "
        "Per-column survival lives under Data Diagnostics → Feature matrix / modality coverage."
    )
    print("")


def launch_feature_matrix_modality_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Launch the feature matrix/modality coverage view."""
    du.print_section("Feature matrix / modality coverage")
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    entries: list[tuple[str, list[Path]]] = [
        ("Feature contract", [rdiag / "feature_contract.json", gdiag / "feature_contract.json"]),
        (
            "Modality contribution (JSON)",
            [rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"],
        ),
        (
            "Feature-set ablation summary",
            [rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"],
        ),
        (
            "Feature column survival",
            [
                rdiag / f"feature_column_survival_{rid}.csv",
                rdiag / "feature_column_survival.latest.csv",
                gdiag / "feature_column_survival.latest.csv",
            ],
        ),
        ("Feature group survival", [rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"]),
    ]
    for label, candidates in entries:
        hit = first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")
    print("")


def launch_taxonomy_consistency_review_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Launch the taxonomy consistency review view."""
    du.print_section("Taxonomy consistency review")
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    summary_path = first_existing_path(
        [rdiag / f"taxonomy_consistency_summary_{rid}.json", gdiag / "taxonomy_consistency_summary.latest.json"]
    )
    summary = read_json_dict(summary_path) if summary_path else {}
    if summary:
        du.print_subheader("Compact summary")
        du.print_stat("Rows evaluated", str(summary.get("rows_evaluated", "—")))
        du.print_stat("Taxonomy mismatches", str(summary.get("taxonomy_mismatch_count", "—")))
        du.print_stat("Type mismatches", str(summary.get("type_mismatch_count", "—")))
        du.print_stat("Missing type labels", str(summary.get("type_missing_label_count", "—")))
        du.print_stat("Family label mismatches", str(summary.get("family_label_mismatch_count", "—")))
        print("")
    rows: list[tuple[str, list[Path]]] = [
        (
            "Taxonomy consistency summary (JSON)",
            [rdiag / f"taxonomy_consistency_summary_{rid}.json", gdiag / "taxonomy_consistency_summary.latest.json"],
        ),
        (
            "Taxonomy mismatches (CSV)",
            [rdiag / f"taxonomy_consistency_mismatches_{rid}.csv", gdiag / "taxonomy_consistency_mismatches.latest.csv"],
        ),
        ("Prediction errors (CSV)", [rdiag / f"prediction_errors_{rid}.csv"]),
    ]
    for label, candidates in rows:
        hit = first_existing_path(candidates)
        du.print_stat(label, str(hit.resolve()) if hit else "missing")
    du.print_info(
        "[MENU] Prefer run-scoped names; global `*.latest.*` under output/diagnostics/ mirrors when hygiene omits duplicates."
    )
    print("")


def launch_taxonomy_support_tuning_compact_menu(*, read_latest_run_id: Callable[[], str | None]) -> None:
    """Compact taxonomy/support tuning screen for next-run decisions."""
    du.print_section("Taxonomy & support tuning")
    output_root = canonical_output_root()
    rid = read_latest_run_id()
    if not rid:
        du.print_warning("[MENU] No latest run.")
        return
    rdiag = output_root / "runs" / rid / "diagnostics"
    gdiag = output_root / "diagnostics"
    taxonomy_path = first_existing_path([rdiag / f"taxonomy_consistency_summary_{rid}.json", gdiag / "taxonomy_consistency_summary.latest.json"])
    taxonomy = read_json_dict(taxonomy_path) if taxonomy_path else {}
    fam_audit_path = first_existing_path([rdiag / "family_label_taxonomy_audit.csv"])
    support_preview_path = first_existing_path([rdiag / "support_threshold_preview.csv"])
    low_support_path = first_existing_path([rdiag / "low_support_families.csv"])
    trained_registry_path = first_existing_path([rdiag / f"trained_family_registry_{rid}.csv"])
    family_distribution_path = first_existing_path([rdiag / "family_distribution.csv"])
    authority_review_path = first_existing_path([rdiag / f"taxonomy_type_authority_review_{rid}.md", rdiag / "taxonomy_type_authority_review.latest.md"])

    tax_total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) if taxonomy else 0
    type_issues = (
        int(taxonomy.get("type_mismatch_count", 0) or 0)
        + int(taxonomy.get("type_noncanonical_count", 0) or 0)
        + int(taxonomy.get("type_missing_label_count", 0) or 0)
    ) if taxonomy else 0
    family_mismatch = int(taxonomy.get("family_label_mismatch_count", 0) or 0) if taxonomy else 0
    du.print_stat("Taxonomy health", "YELLOW" if tax_total > 0 else ("GREEN" if taxonomy else "RED"))
    du.print_stat("Taxonomy mismatch total", tax_total if taxonomy else "—")
    du.print_stat("Type/rendering issue count", type_issues if taxonomy else "—")
    du.print_stat("Family mismatch count", family_mismatch if taxonomy else "—")

    min_support = "—"
    families_before = retained = dropped = dropped_samples = near_threshold = "—"
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty:
            if "configured_min_samples_per_family" in fam_df.columns:
                min_support = int(pd.to_numeric(fam_df["configured_min_samples_per_family"], errors="coerce").dropna().iloc[0])
            families_before = int(len(fam_df))
            if "support_status" in fam_df.columns:
                retained = int((fam_df["support_status"].astype(str) == "retained").sum())
                dropped = int((fam_df["support_status"].astype(str).str.contains("dropped", na=False)).sum())
            if "aligned_rows" in fam_df.columns and "support_status" in fam_df.columns:
                dropped_samples = int(pd.to_numeric(fam_df.loc[fam_df["support_status"].astype(str).str.contains("dropped", na=False), "aligned_rows"], errors="coerce").fillna(0).sum())
            if isinstance(min_support, int) and "aligned_rows" in fam_df.columns:
                counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0)
                near_threshold = int(((counts >= max(0, min_support - 2)) & (counts < min_support)).sum())
    du.print_stat("min_samples_per_family", min_support)
    du.print_stat("Families before threshold", families_before)
    du.print_stat("Families retained", retained)
    du.print_stat("Families dropped", dropped)
    du.print_stat("Samples dropped (estimate)", dropped_samples)
    du.print_stat("Families just below threshold", near_threshold)

    du.print_subheader("Tune next")
    if tax_total > 0:
        du.print_info("1) Review taxonomy mismatches first; separate family mismatches from type/rendering issues.")
    if isinstance(near_threshold, int) and near_threshold > 0:
        du.print_info("2) Review families just below threshold before changing cohort/profile support settings.")
    du.print_info("3) Cross-check retained/dropped families with trained_family_registry and support_threshold_preview.")
    du.print_stat("taxonomy_consistency_summary", str(taxonomy_path.resolve()) if taxonomy_path else "missing")
    du.print_stat("taxonomy_type_authority_review", str(authority_review_path.resolve()) if authority_review_path else "missing")
    du.print_stat("family_label_taxonomy_audit", str(fam_audit_path.resolve()) if fam_audit_path else "missing")
    du.print_stat("support_threshold_preview", str(support_preview_path.resolve()) if support_preview_path else "missing")
    if resolve_display_mode() != "compact":
        du.print_stat("low_support_families", str(low_support_path.resolve()) if low_support_path else "missing")
        du.print_stat("trained_family_registry", str(trained_registry_path.resolve()) if trained_registry_path else "missing")
        du.print_stat("family_distribution", str(family_distribution_path.resolve()) if family_distribution_path else "missing")
    print("")


def build_taxonomy_support_tuning_snapshot(*, run_id: str, output_root: Path) -> dict[str, object]:
    """Build compact taxonomy/support tuning snapshot from existing diagnostics artifacts."""
    rdiag = output_root / "runs" / run_id / "diagnostics"
    gdiag = output_root / "diagnostics"
    taxonomy_path = first_existing_path([rdiag / f"taxonomy_consistency_summary_{run_id}.json", gdiag / "taxonomy_consistency_summary.latest.json"])
    taxonomy = read_json_dict(taxonomy_path) if taxonomy_path else {}
    fam_audit_path = first_existing_path([rdiag / "family_label_taxonomy_audit.csv"])
    support_preview_path = first_existing_path([rdiag / "support_threshold_preview.csv"])

    tax_total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0) if taxonomy else 0
    type_issues = (
        int(taxonomy.get("type_mismatch_count", 0) or 0)
        + int(taxonomy.get("type_noncanonical_count", 0) or 0)
        + int(taxonomy.get("type_missing_label_count", 0) or 0)
    ) if taxonomy else 0
    family_mismatch = int(taxonomy.get("family_label_mismatch_count", 0) or 0) if taxonomy else 0

    min_support: int | str = "—"
    families_before: int | str = "—"
    retained: int | str = "—"
    dropped: int | str = "—"
    dropped_samples: int | str = "—"
    near_threshold: int | str = "—"
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty:
            if "configured_min_samples_per_family" in fam_df.columns:
                vals = pd.to_numeric(fam_df["configured_min_samples_per_family"], errors="coerce").dropna()
                if not vals.empty:
                    min_support = int(vals.iloc[0])
            families_before = int(len(fam_df))
            if "support_status" in fam_df.columns:
                retained = int((fam_df["support_status"].astype(str) == "retained").sum())
                dropped = int((fam_df["support_status"].astype(str).str.contains("dropped", na=False)).sum())
            if "aligned_rows" in fam_df.columns and "support_status" in fam_df.columns:
                dropped_samples = int(
                    pd.to_numeric(
                        fam_df.loc[fam_df["support_status"].astype(str).str.contains("dropped", na=False), "aligned_rows"],
                        errors="coerce",
                    ).fillna(0).sum()
                )
            if isinstance(min_support, int) and "aligned_rows" in fam_df.columns:
                counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0)
                near_threshold = int(((counts >= max(0, min_support - 2)) & (counts < min_support)).sum())

    threshold_sensitivity: list[dict[str, int]] = []
    if fam_audit_path is not None:
        fam_df = pd.read_csv(fam_audit_path)
        if not fam_df.empty and "aligned_rows" in fam_df.columns:
            counts = pd.to_numeric(fam_df["aligned_rows"], errors="coerce").fillna(0).astype(int)
            for t in (5, 10, 15, 20, 25):
                retained_mask = counts >= t
                retained_families = int(retained_mask.sum())
                dropped_families = int((~retained_mask).sum())
                retained_samples = int(counts[retained_mask].sum())
                dropped_samples_t = int(counts[~retained_mask].sum())
                threshold_sensitivity.append(
                    {
                        "threshold": int(t),
                        "retained_families": retained_families,
                        "dropped_families": dropped_families,
                        "retained_samples": retained_samples,
                        "dropped_samples": dropped_samples_t,
                    }
                )

    return {
        "taxonomy_health": "YELLOW" if tax_total > 0 else ("GREEN" if taxonomy else "RED"),
        "taxonomy_mismatch_total": tax_total if taxonomy else "—",
        "type_rendering_issue_count": type_issues if taxonomy else "—",
        "family_mismatch_count": family_mismatch if taxonomy else "—",
        "min_samples_per_family": min_support,
        "families_before_threshold": families_before,
        "families_retained": retained,
        "families_dropped": dropped,
        "samples_dropped_estimate": dropped_samples,
        "families_just_below_threshold": near_threshold,
        "taxonomy_consistency_summary_path": str(taxonomy_path.resolve()) if taxonomy_path else "missing",
        "family_label_taxonomy_audit_path": str(fam_audit_path.resolve()) if fam_audit_path else "missing",
        "support_threshold_preview_path": str(support_preview_path.resolve()) if support_preview_path else "missing",
        "threshold_sensitivity": threshold_sensitivity,
    }


def build_permission_coverage_tuning_snapshot(*, run_id: str, output_root: Path) -> dict[str, object]:
    """Build compact permission-coverage tuning snapshot from existing artifacts."""
    rdiag = output_root / "runs" / run_id / "diagnostics"
    gdiag = output_root / "diagnostics"
    q2_path = first_existing_path([rdiag / "modality_contribution_summary.json", gdiag / "modality_contribution_summary.json"])
    q2 = read_json_dict(q2_path) if q2_path else {}
    perm_cov_path = first_existing_path([rdiag / "permission_coverage_summary.csv", gdiag / "permission_coverage_summary.csv"])
    feature_group_path = first_existing_path([rdiag / "feature_group_survival.csv", gdiag / "feature_group_survival.csv"])
    ablation_path = first_existing_path([rdiag / "feature_set_ablation_summary.csv", gdiag / "feature_set_ablation_summary.csv"])

    weak_types = weak_families = 0
    if perm_cov_path is not None:
        df = pd.read_csv(perm_cov_path)
        if not df.empty:
            cols = {str(c).lower(): c for c in df.columns}
            bucket_col = cols.get("group_kind") or cols.get("scope") or cols.get("bucket_type")
            cov_col = cols.get("coverage_pct") or cols.get("coverage")
            if bucket_col and cov_col:
                work = df.copy()
                work[cov_col] = pd.to_numeric(work[cov_col], errors="coerce").fillna(0.0)
                b = work[bucket_col].astype(str).str.lower()
                weak_types = int(((b.str.contains("type")) & (work[cov_col] <= 1.0)).sum())
                weak_families = int(((b.str.contains("famil")) & (work[cov_col] <= 1.0)).sum())

    permission_feature_survival = "n/a"
    if feature_group_path is not None:
        fg = pd.read_csv(feature_group_path)
        if not fg.empty:
            text = fg.to_string(index=False).lower()
            permission_feature_survival = "present" if "permission" in text else "not_explicit"

    permission_only_ablation = "n/a"
    if ablation_path is not None:
        ab = pd.read_csv(ablation_path)
        if not ab.empty:
            txt = ab.to_string(index=False).lower()
            permission_only_ablation = "present" if "permission" in txt else "not_found"

    return {
        "global_permission_signal_pct": q2.get("permission_signal_pct", "—") if q2 else "—",
        "global_permission_signal_n": q2.get("permission_signal_n", "—") if q2 else "—",
        "weak_or_zero_coverage_types": weak_types,
        "weak_or_zero_coverage_families": weak_families,
        "permission_feature_survival": permission_feature_survival,
        "permission_only_ablation_signal": permission_only_ablation,
    }

def launch_data_diagnostics_menu(
    *,
    read_latest_run_id: Callable[[], str | None],
    show_profile_tuning_snapshot: Callable[[], int],
    open_run_science_index_action: Callable[[], int],
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
            "Taxonomy & Support Tuning",
            "Taxonomy Consistency Review",
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
            launch_taxonomy_support_tuning_compact_menu(read_latest_run_id=read_latest_run_id)
            continue
        if choice == 4:
            launch_taxonomy_consistency_review_action()
            continue
        if choice == 5:
            launch_parser_vendor_coverage_action()
            continue
        if choice == 6:
            launch_permission_intelligence_coverage_action()
            continue
        if choice == 7:
            launch_feature_matrix_modality_action()
            continue
        if choice == 8:
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
    "launch_feature_matrix_modality_menu",
    "launch_parser_vendor_coverage_menu",
    "launch_permission_intelligence_coverage_menu",
    "launch_taxonomy_consistency_review_menu",
    "launch_taxonomy_support_tuning_compact_menu",
    "open_run_science_index",
    "print_cohort_family_artifact_paths",
    "run_family_label_taxonomy_audit_script",
]
