"""Cohort/family audit helpers for the Data Diagnostics menu."""

from __future__ import annotations

from pathlib import Path
import sys

from obsidiandroid.cli.menu.operator_state import build_operator_state
from obsidiandroid.cli.ui import display as du
from obsidiandroid.cli.ui import menu as mu
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.governance import paper_cohort_contract


def run_family_label_taxonomy_audit_script(
    *,
    read_latest_run_id,
    resolve_latest_manifest_payload,
    resolve_and_validate_profile,
    load_profile,
    output_root: Path,
    operator_script_resolver,
    subprocess_run,
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
    proc = subprocess_run(cmd, check=False)
    return int(proc.returncode)


def open_run_science_index(
    *,
    output_root: Path,
    read_latest_run_id,
) -> int:
    """Print the best available authoritative run index path for the latest run."""
    rid = str(read_latest_run_id() or "").strip()
    shared = build_operator_state(output_base=output_root, run_id=rid or None)
    rid = rid or str(shared.get("latest_run_id", "") or "")
    if not rid:
        du.print_warning("[MENU] No latest run — run science index is unavailable.")
        return 1
    path_obj = shared.get("best_run_index_path")
    path = path_obj if isinstance(path_obj, Path) else Path(str(path_obj or ""))
    canonical = output_root / "runs" / rid / "diagnostics" / "run_science_index.md"
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


def print_cohort_family_artifact_paths(
    *,
    read_latest_run_id,
    output_root: Path,
    latest_post_run_enrichment_dir_fn,
    latest_post_run_entry_fn,
) -> None:
    """List canonical and enrichment cohort/family artifact paths for the latest run."""
    du.print_section("Cohort / family artifact paths")
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
        (f"cohort_filter_contract_{rid}.json", oh.resolve_cohort_filter_contract_path(rdiag, rid)),
        (f"cohort_gate_counts_{rid}.csv", oh.resolve_cohort_gate_counts_path(rdiag, rid)),
        ("cohort_lock_summary.json", rdiag / "cohort_lock_summary.json"),
        ("cohort_membership.csv", rdiag / "cohort_membership.csv"),
        (
            f"analysis_snapshot_filter_summary_{rid}.csv",
            oh.resolve_analysis_snapshot_filter_summary_path(rdiag, rid),
        ),
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

    latest_enrichment = latest_post_run_enrichment_dir_fn(rdiag)
    if latest_enrichment is not None:
        latest_entry = latest_post_run_entry_fn(rdiag) or {}
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
    primary_filter = oh.resolve_analysis_snapshot_filter_summary_path(rdiag, rid)
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
    read_latest_run_id,
    open_run_science_index_action,
    run_family_label_taxonomy_audit_action,
    print_cohort_family_artifact_paths_action,
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
            print_cohort_family_artifact_paths_action(read_latest_run_id=read_latest_run_id)
            continue
        if choice == 2:
            open_run_science_index_action()
            continue
        if choice == 3:
            run_family_label_taxonomy_audit_action()
            continue
        du.print_warning("[MENU] Invalid choice received.")


__all__ = [
    "launch_cohort_family_audit_menu",
    "open_run_science_index",
    "print_cohort_family_artifact_paths",
    "run_family_label_taxonomy_audit_script",
]
