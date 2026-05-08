"""Structural analysis context banner and prompts for the startup menu."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from config import app_config

from obsidiandroid.common import output_hygiene as oh

from .startup_menu_run_context import read_latest_run_id
from .ui import display as du


def print_structural_analysis_banner() -> None:
    """Print current structural-analysis mode and pruning contract."""
    paper_mode = bool(
        getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))
    )
    figure_mode = str(getattr(app_config, "FIGURE_MODE", "analysis"))
    analysis_scope = str(getattr(app_config, "ANALYSIS_SCOPE", "all"))
    max_perms = int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30))
    selection_method = str(getattr(app_config, "PERMISSION_SELECTION_METHOD", "discriminability"))
    min_family_support = int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 50))
    min_family_support_model = int(getattr(app_config, "MIN_FAMILY_SUPPORT", 3))
    exclude_unknown = bool(getattr(app_config, "EXCLUDE_UNKNOWN_TYPE_IN_VISUALS", True))
    latest_run_id = read_latest_run_id() or "No run selected"
    layer_map = {
        "type": "Type-Level",
        "family": "Family-Level",
        "banker": "Banker-Specific",
        "all": "Mixed (Type + Family + Banker)",
    }
    structural_layer = layer_map.get(analysis_scope, analysis_scope)

    snapshot_path: Path | None = None
    rid_disp = str(latest_run_id).strip()
    if rid_disp and rid_disp != "No run selected":
        stable_root = oh.resolve_stable_output_root_for_mirrors()
        snapshot_path = oh.resolve_analysis_snapshot_csv_path(
            stable_root / "runs" / rid_disp / "diagnostics",
            rid_disp,
        )
    type_count: str | int = "Not available"
    unknown_count: str | int = "Not computed yet"
    family_visual_count: str | int = "Not available"
    try:
        if snapshot_path is not None:
            snap_df = pd.read_csv(snapshot_path)
            if "type_slug" in snap_df.columns:
                types = (
                    snap_df["type_slug"]
                    .fillna("unknown")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
                unknown_count = int((types == "unknown").sum())
                included_types = sorted(set(types.tolist()))
                if exclude_unknown:
                    included_types = [t for t in included_types if t != "unknown"]
                type_count = len(included_types)
            if "family_canonical" in snap_df.columns:
                fam_counts = (
                    snap_df["family_canonical"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .value_counts()
                )
                family_visual_count = int((fam_counts >= min_family_support).sum())
    except Exception:
        pass

    short_run_id = latest_run_id
    du.print_section("Structural Analysis Context")
    print("")
    print("Run")
    du.print_stat("  Active Run ID", short_run_id)
    du.print_stat("  Evidence Export Mode", "ON" if paper_mode else "OFF")
    du.print_stat("  Structural View Mode", "Publication" if str(figure_mode).lower() == "paper" else "Analysis")
    print("")
    print("Scope")
    du.print_stat("  Structural Layer", structural_layer)
    du.print_stat("  Analysis Scope", str(analysis_scope).title())
    du.print_stat("  Types Included", type_count)
    du.print_stat("  Exclude Unknown Type", "Yes" if exclude_unknown else "No")
    print("")
    print("Thresholds")
    du.print_stat("  Min Family Support", f"Visual >= {min_family_support} | Model >= {min_family_support_model}")
    du.print_stat("  Max Permissions", max_perms)
    du.print_stat("  Permission Selection", str(selection_method).title())
    print("")
    print("Cohort Snapshot")
    du.print_stat("  Unknown Samples", unknown_count)
    du.print_stat("  Families >= Visual", family_visual_count)


def print_structural_result_card(*, action: str, status: str, output_path: str = "") -> None:
    """Print a compact action result card."""
    print("-" * 32 + " RESULT " + "-" * 31)
    du.print_stat("Action", action)
    if output_path:
        normalized = output_path.replace("\\", "/")
        du.print_stat("Output", normalized)
    du.print_stat("Status", status.upper())
    print("-" * 72)


def warn_if_no_latest_run_context(*, area: str) -> None:
    """Warn users when entering run-dependent areas without a latest run."""
    if read_latest_run_id():
        return
    du.print_warning(
        f"[MENU] {area}: no run selected yet. Some actions may be unavailable until a pipeline run completes."
    )


def prompt_structural_analysis_action(options: List[str]) -> str:
    """Prompt for structural-analysis action with context refresh control."""
    du.print_subheader("Structural Analysis and Publication Figures")
    for idx, opt in enumerate(options, 1):
        print(f"  [{idx}] {opt}")
    print("  [I] View Context Card")
    print("  [0] Back\n")
    print("Controls: [I] Context  [0] Back")
    while True:
        try:
            raw = input(f"Enter your selection [0-{len(options)} or I]: ").strip()
        except KeyboardInterrupt:
            return "0"
        if not raw:
            du.print_warning("Invalid input. Please enter a selection.")
            continue
        selection_upper = raw.upper()
        if selection_upper == "I":
            return selection_upper
        if selection_upper.isdigit() and 0 <= int(selection_upper) <= len(options):
            return selection_upper
        du.print_warning("Invalid input. Enter a valid number or I.")
