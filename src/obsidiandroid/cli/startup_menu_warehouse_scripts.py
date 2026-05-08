"""Warehouse and script-driven menu actions (backfill, diagnostics, evidence checks)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config import app_config

from obsidiandroid.database import db_engine

from .startup_menu_prompts import prompt_run_id
from .startup_menu_run_context import latest_run_paper_mode_enabled, read_latest_run_id
from .ui import display as du


def run_backfill_results_warehouse() -> int:
    """Backfill warehouse tables from existing permission bundle artifacts."""
    du.print_section("Backfill Results Warehouse from Existing Artifacts")
    latest_run_id = read_latest_run_id()
    run_id = prompt_run_id(default_run_id=latest_run_id)
    if not run_id:
        du.print_warning("[MENU] Backfill cancelled (no run_id provided).")
        return 1

    script_path = Path("scripts/backfill_permission_trends_warehouse.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1

    cmd = [sys.executable, str(script_path), "--run-id", run_id]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] Backfill failed with exit code {proc.returncode}.")
        return int(proc.returncode)

    du.print_success(f"[MENU] Warehouse backfill completed for run_id={run_id}.")
    return 0


def run_results_warehouse_status() -> int:
    """Show whether key warehouse tables are populated for a selected run."""
    du.print_section("Results Warehouse Status")
    latest_run_id = read_latest_run_id()
    run_id = prompt_run_id(default_run_id=latest_run_id)
    if not run_id:
        du.print_warning("[MENU] Status check cancelled (no run_id provided).")
        return 1

    table_names = [
        "analysis_snapshot",
        "analysis_snapshot_sample",
        "permission_coverage_report",
        "dangerous_distribution_by_type",
        "type_permission_prevalence",
        "family_permission_profile",
        "group_permission_entropy",
        "family_jsd_matrix",
        "banker_permission_enrichment",
        "permission_discriminability_rank",
        "consensus_distribution",
        "per_family_performance_spread",
        "banker_permission_family_heterogeneity",
        "family_permission_cohesion",
        "banker_permission_trends_over_time",
    ]
    rows: list[dict[str, object]] = []
    total_rows = 0
    for table in table_names:
        query = f"SELECT COUNT(*) AS row_count FROM {table} WHERE run_id = %s"
        try:
            result = db_engine.execute_query(
                query,
                params=(run_id,),
                fetch=True,
                as_dataframe=True,
            )
            row_count = int(result.iloc[0]["row_count"]) if not result.empty else 0
        except Exception as exc:
            rows.append({"table_name": table, "row_count": "ERROR", "status": str(exc)})
            continue

        total_rows += row_count
        status = "OK" if row_count > 0 else "MISSING"
        rows.append({"table_name": table, "row_count": row_count, "status": status})

    du.print_table(
        rows,
        title=f"Warehouse table coverage for run_id={run_id}",
        show_index=False,
    )
    if total_rows == 0:
        du.print_warning(
            "[MENU] No rows found for this run_id. Use 'Backfill Results Warehouse from Existing Artifacts'."
        )
        return 1

    du.print_success(f"[MENU] Warehouse rows detected for run_id={run_id}: total={total_rows}")
    return 0
def run_paper_structural_diagnostics() -> int:
    """Generate consolidated structural diagnostics from latest artifacts."""
    du.print_section("Generate Structural Diagnostics")
    script_path = Path("scripts/research/generate_structural_diagnostics.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path)]
    env = os.environ.copy()
    evidence_mode = bool(
        getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))
    )
    env["SCYTALEDROID_EVIDENCE_MODE"] = "1" if evidence_mode else "0"
    env["SCYTALEDROID_FIGURE_MODE"] = str(getattr(app_config, "FIGURE_MODE", "publication"))
    env["SCYTALEDROID_ANALYSIS_SCOPE"] = str(getattr(app_config, "ANALYSIS_SCOPE", "all"))
    latest_run_id = read_latest_run_id() or ""
    if latest_run_id:
        env["SCYTALEDROID_RUN_ID"] = latest_run_id
    env["SCYTALEDROID_OUTPUT_ROOT"] = str(Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))).resolve())
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    du.print_info(
        "[MENU] Structural export context: "
        f"evidence_mode={env['SCYTALEDROID_EVIDENCE_MODE']} "
        f"figure_mode={env['SCYTALEDROID_FIGURE_MODE']} "
        f"analysis_scope={env['SCYTALEDROID_ANALYSIS_SCOPE']}"
    )
    proc = subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        du.print_error(f"[MENU] Diagnostics script failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    output_path = ""
    for line in (proc.stdout or "").splitlines():
        if line.strip().lower().startswith("wrote:"):
            output_path = line.split(":", 1)[1].strip()
            break
    setattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", output_path)
    if output_path:
        du.print_success(f"[MENU] Structural diagnostics exported to {output_path}")
    else:
        du.print_success("[MENU] Structural diagnostics exported.")
    return 0


def run_claim_artifact_map_scaffold() -> int:
    """Generate claim_artifact_map.csv from run path manifests."""
    du.print_section("Generate Claim Artifact Map Scaffold")
    script_path = Path("scripts/research/generate_claim_artifact_map.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    latest = read_latest_run_id() or ""
    try:
        run_ids = input(f"Enter run IDs (comma-separated) [{latest}]: ").strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Input interrupted.")
        return 1
    run_ids = run_ids or latest
    if not run_ids:
        du.print_warning("[MENU] No run IDs provided.")
        return 1
    cmd = [sys.executable, str(script_path), "--run-ids", run_ids]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] claim_artifact_map generation failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    return 0


def run_paper2_freeze_checker() -> int:
    """Run strict reproducibility checks for supplied evidence run IDs."""
    du.print_section("Run Evidence Bundle Checker")
    if not latest_run_paper_mode_enabled():
        du.print_info(
            "[MENU] Latest run is not in evidence/paper mode. "
            "This script validates strict evidence bundles—pass evidence-mode run IDs if defaults look sparse."
        )
    script_path = Path("scripts/research/check_evidence_bundle.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    latest = read_latest_run_id() or ""
    try:
        run_ids = input(f"Enter run IDs (comma-separated) [{latest}]: ").strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Input interrupted.")
        return 1
    run_ids = run_ids or latest
    if not run_ids:
        du.print_warning("[MENU] No run IDs provided.")
        return 1
    cmd = [sys.executable, str(script_path), "--run-ids", run_ids]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_warning(
            "[MENU] Evidence bundle checker reported issues; inspect output/diagnostics/evidence_bundle_check.latest.json"
        )
        return int(proc.returncode)
    du.print_success("[MENU] Evidence bundle checker passed for supplied run IDs.")
    return 0


def run_retrain_from_cached_alignment() -> int:
    """Retrain models quickly from cached aligned feature/label artifacts."""
    du.print_section("Retrain Models from Cached Alignment")
    script_path = Path("scripts/retrain_models_from_cached_alignment.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path)]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] Cached retrain failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    return 0
