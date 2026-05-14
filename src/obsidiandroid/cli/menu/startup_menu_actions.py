"""Operational action handlers extracted from startup menu.

These functions keep behavior stable while reducing complexity in
``obsidiandroid.cli.startup_menu``.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

from config import app_config
from obsidiandroid.common.repo_paths import repo_operator_script
from . import run_locator
from ..ui import display as du
from ..ui import menu as mu


def _read_json_object(path: Path) -> dict:
    """Read JSON file as dict; return empty dict on failure."""
    return run_locator.read_json_object(path)


def _read_latest_run_id() -> str | None:
    """Return latest run_id from diagnostics manifest when available."""
    return run_locator.read_latest_run_id()


def _resolve_latest_manifest_payload() -> tuple[dict, str | None, Path]:
    """Resolve latest manifest payload, following pointer manifest when needed."""
    return run_locator.resolve_latest_manifest_payload()


def _format_model_label(token: str) -> str:
    """Convert normalized model token to user-facing label."""
    mapping = {
        "logistic_regression": "Logistic Regression",
        "random_forest": "Random Forest",
        "balanced_random_forest": "Balanced Random Forest",
        "xgboost": "XGBoost",
    }
    return mapping.get(token, token.replace("_", " ").title())


def run_output_cleanup() -> int:
    """Run output cleanup in dry-run or apply mode."""
    du.print_section("Cleanup Output Artifacts")
    script_path = repo_operator_script("cleanup_output_artifacts.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1

    apply_changes = mu.confirm_prompt("Apply deletion now? (No = dry-run)")
    cmd = [sys.executable, str(script_path), "--keep-latest-runs", "1", "--keep-runtime-logs", "5"]
    if apply_changes:
        cmd.append("--apply")
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] Cleanup script failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    return 0


def show_within_cross_type_error_snapshot() -> int:
    """Show latest within-type vs cross-type error summary when available."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    run_id = _read_latest_run_id() or ""
    candidate_paths: list[Path] = []
    if run_id:
        candidate_paths.extend(
            [
                output_root / "runs" / run_id / "diagnostics" / "confusion_within_vs_cross_type.latest.csv",
                output_root / "runs" / run_id / "bundles" / "permission_trends" / "tables" / "confusion_within_vs_cross_type.latest.csv",
            ]
        )
    candidate_paths.extend(
        [
            output_root / "bundles" / "latest" / "permission_trends" / "tables" / "confusion_within_vs_cross_type.latest.csv",
        ]
    )
    chosen_path = next((path for path in candidate_paths if path.exists()), None)
    if chosen_path is None:
        du.print_warning("[MENU] Missing within-vs-cross-type confusion artifact.")
        return 1
    try:
        df = pd.read_csv(chosen_path)
    except Exception as exc:
        du.print_error(f"[MENU] Failed to read confusion summary: {exc}")
        return 1
    if df.empty:
        du.print_warning("[MENU] Confusion summary is empty.")
        return 1

    if "error_type" not in df.columns or "count" not in df.columns:
        du.print_warning("[MENU] Confusion summary schema is missing required columns.")
        return 1

    indexed = df.set_index("error_type")
    total_errors = float(pd.to_numeric(indexed["count"], errors="coerce").get("total_error", 0.0))
    within_errors = float(pd.to_numeric(indexed["count"], errors="coerce").get("within_type_error", 0.0))
    cross_errors = float(pd.to_numeric(indexed["count"], errors="coerce").get("cross_type_error", 0.0))

    if total_errors <= 0:
        du.print_warning("[MENU] Total errors are zero; no breakdown available.")
        return 0

    within_ratio = float(indexed["count"].get("within_type_error_ratio", within_errors / total_errors))
    cross_ratio = float(indexed["count"].get("cross_type_error_ratio", cross_errors / total_errors))
    run_id_value = str(df["run_id"].iloc[0]) if "run_id" in df.columns and not df.empty else (run_id or "n/a")
    predictions = int(pd.to_numeric(indexed["count"], errors="coerce").get("total_predictions", 0.0))
    if predictions <= 0:
        predictions = 0
    error_rate = (total_errors / predictions) if predictions > 0 else 0.0

    def _bar(ratio: float, width: int = 24) -> str:
        filled = int(round(max(0.0, min(1.0, ratio)) * width))
        return ("#" * filled).ljust(width, ".")

    delta = abs(within_ratio - cross_ratio)
    if delta <= 0.05:
        interpretation = "Errors are nearly balanced between within-type and cross-type confusion."
    elif within_ratio > cross_ratio:
        interpretation = "Within-type confusion dominates; family-level differentiation is the primary challenge."
    else:
        interpretation = "Cross-type confusion dominates; broad malware-type separation needs improvement."

    du.print_section("Within vs Cross-Type Error Analysis")
    du.print_stat("Run ID", run_id_value)
    if predictions > 0:
        du.print_stat("Total Predictions", predictions)
        du.print_stat("Overall Error Rate", f"{error_rate:.2%}")
    du.print_stat("Total Errors", int(total_errors))
    print("")
    print("Error Breakdown")
    du.print_stat("  Within-Type Errors", f"{int(within_errors)} ({within_ratio:.2%})")
    du.print_stat("  Cross-Type Errors", f"{int(cross_errors)} ({cross_ratio:.2%})")
    print("")
    print("Error Distribution")
    du.print_stat("  Within-Type", f"{_bar(within_ratio)} {within_ratio:.0%}")
    du.print_stat("  Cross-Type", f"{_bar(cross_ratio)} {cross_ratio:.0%}")
    print("")
    print("Interpretation")
    du.print_info(f"  {interpretation}")
    du.print_stat("Export", str(chosen_path).replace("\\", "/"))
    return 0


def show_model_comparison_snapshot() -> int:
    """Show latest model-comparison snapshot from diagnostics when available."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    diagnostics_dir = output_root / "diagnostics"
    latest_run_id = _read_latest_run_id() or ""
    run_scoped_dir = output_root / "runs" / latest_run_id / "diagnostics" if latest_run_id else output_root / "runs"
    candidate_paths: list[Path] = []
    if latest_run_id:
        candidate_paths.append(run_scoped_dir / f"model_comparison_summary_{latest_run_id}.csv")
        candidate_paths.append(diagnostics_dir / f"model_comparison_summary_{latest_run_id}.csv")
    candidate_paths.extend(sorted(run_scoped_dir.glob("model_comparison_summary_*.csv"), reverse=True))
    candidate_paths.extend(sorted(diagnostics_dir.glob("model_comparison_summary_*.csv"), reverse=True))
    chosen = next((path for path in candidate_paths if path and path.exists()), None)
    if not chosen:
        du.print_warning("[MENU] No model comparison summary found in diagnostics.")
        return 1
    try:
        df = pd.read_csv(chosen)
    except Exception as exc:
        du.print_error(f"[MENU] Failed to read model comparison summary: {exc}")
        return 1
    du.print_stat("Source", str(chosen))
    if df.empty:
        du.print_warning("[MENU] Model comparison summary is empty.")
        return 1
    du.print_table(df.head(10), title="Top model comparison rows", show_index=False)
    return 0


def handle_confusion_matrix_export() -> int:
    """Export primary confusion matrix to run paper2 pack for the latest run."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    _, run_id, _ = _resolve_latest_manifest_payload()
    if not run_id:
        du.print_warning("[MENU] No latest run found. Run pipeline first.")
        return 1
    run_root = output_root / "runs" / run_id
    conf_dir = run_root / "conf_matrices"
    if not conf_dir.exists():
        du.print_warning("[MENU] No confusion matrices found for latest run.")
        return 1

    matrix_files = sorted(
        [
            path
            for path in conf_dir.glob("confusion_matrix_*.png")
            if path.name not in {"confusion_matrix_primary.png"}
        ]
    )
    pack_dir = run_root / "paper2_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    canonical_manifest = _read_json_object(run_root / "run_manifest.json")
    top_model = str(
        (
            canonical_manifest.get("model_summary", {})
            if isinstance(canonical_manifest.get("model_summary"), dict)
            else {}
        ).get("top_model", "")
    ).strip()
    normalized_top = top_model.lower().replace("-", "_").replace(" ", "_")

    if len(matrix_files) != 1:
        du.print_section("Confusion Matrix Export")
        du.print_stat("Run ID", run_id)
        du.print_stat("Model Selection Mode", "Pipeline Auto-Selection")
        du.print_stat("Detected Models", len(matrix_files))
        print("")
        print("This export is restricted to single-model runs to avoid ambiguity.")
        if matrix_files:
            print("")
            print("Current run contains multiple trained models:")
            for model_path in matrix_files:
                token = model_path.stem.replace("confusion_matrix_", "")
                print(f"  - {_format_model_label(token)}")
        if normalized_top:
            print("")
            du.print_stat("Primary Model Selected", _format_model_label(normalized_top))
        print("")
        print("Next Steps")
        print("  Option 1: Run a single-model experiment and export the confusion matrix.")
        print("  Option 2: Use 'Model Comparison Summary' to review results across models.")
        du.print_info("[MENU] No confusion matrix exported.")
        return 0

    source_path = matrix_files[0]
    if normalized_top:
        preferred = conf_dir / f"confusion_matrix_{normalized_top}.png"
        if preferred.exists():
            source_path = preferred
    target_path = pack_dir / "confusion_matrix_primary.png"
    try:
        shutil.copy2(source_path, target_path)
    except Exception as exc:
        du.print_error(f"[MENU] Failed to export confusion matrix: {exc}")
        return 1

    du.print_success("[MENU] Confusion matrix exported successfully.")
    du.print_stat("Output", str(target_path).replace("\\", "/"))
    return 0


def show_disk_usage_summary() -> int:
    """Show compact disk-usage summary for output workspace directories."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    targets = [
        output_root / "runs",
        output_root / "diagnostics",
        output_root / "bundles",
        output_root / "latest",
    ]
    rows: list[dict[str, object]] = []
    for path in targets:
        if not path.exists():
            rows.append({"path": str(path), "size_mb": 0.0, "status": "MISSING"})
            continue
        total = 0
        for file_path in path.rglob("*"):
            if file_path.is_file():
                try:
                    total += int(file_path.stat().st_size)
                except Exception:
                    continue
        rows.append({"path": str(path), "size_mb": round(float(total) / (1024.0 * 1024.0), 2), "status": "OK"})
    du.print_table(rows, title="Output Disk Usage Summary", show_index=False)
    return 0
