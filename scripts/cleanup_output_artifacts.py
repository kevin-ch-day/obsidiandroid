"""Prune noisy output artifacts while preserving current/latest results."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


RUN_ID_PATTERN = re.compile(r"(\d{8}T\d{6}Z__[a-z0-9]{6})")


def _extract_run_id(path: Path) -> str | None:
    """Extract run_id token from path name when present."""
    match = RUN_ID_PATTERN.search(path.name)
    return match.group(1) if match else None


def _discover_recent_run_ids(output_dir: Path, keep_latest_runs: int) -> set[str]:
    """Return the newest run IDs discovered under output/runs."""
    if keep_latest_runs <= 0:
        return set()
    runs_dir = output_dir / "runs"
    run_ids: set[str] = set()
    if runs_dir.exists():
        run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
        run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        for run_dir in run_dirs:
            run_id = _extract_run_id(run_dir) or run_dir.name
            if run_id:
                run_ids.add(run_id)
            if len(run_ids) >= keep_latest_runs:
                break
    sorted_ids = sorted(run_ids, reverse=True)
    return set(sorted_ids[:keep_latest_runs])


def _collect_targets(
    output_dir: Path,
    keep_run_ids: set[str],
    keep_runtime_logs: int,
) -> list[Path]:
    """Build list of cleanup targets while preserving selected recent runs."""
    targets: list[Path] = []

    # Run-scoped bundles/archives (keep latest selected run IDs).
    for path in output_dir.glob("paper_bundle_20*"):
        run_id = _extract_run_id(path)
        if run_id and run_id in keep_run_ids:
            continue
        targets.append(path)
    for path in output_dir.glob("paper_bundle_20*.zip"):
        run_id = _extract_run_id(path)
        if run_id and run_id in keep_run_ids:
            continue
        targets.append(path)
    # Legacy global mirrors and exports now superseded by run-scoped outputs.
    for legacy_name in (
        "paper_bundle_latest",
        "permission_trends",
        "permission_trends.zip",
        "engine_scoring_summary_log.txt",
        "family_distribution_report.txt",
    ):
        legacy_path = output_dir / legacy_name
        if legacy_path.exists():
            targets.append(legacy_path)

    # Smoke/debug bundle clutter (always remove).
    targets.extend(output_dir.glob("paper_bundle_smoke*"))
    targets.extend(output_dir.glob("paper_bundle_zip_smoke*"))
    targets.extend(output_dir.glob("paper_bundle_unit_smoke*"))
    targets.extend(output_dir.glob("paper_bundle_*smoke*.zip"))

    # Legacy workbook copies/corrupt backups.
    targets.extend(output_dir.glob("obsidiandroid_outputs_copy.xlsx"))
    targets.extend(output_dir.glob("obsidiandroid_outputs_snapshot.xlsx"))
    targets.extend(output_dir.glob("obsidiandroid_outputs__unknown.xlsx"))
    targets.extend(output_dir.glob("obsidiandroid_outputs.corrupt_*.xlsx"))

    # Timestamped diagnostics duplicates (keep `.latest.*`).
    diagnostics_dir = output_dir / "diagnostics"
    if diagnostics_dir.exists():
        diagnostics_patterns = [
            "ablation_per_family_20*.csv",
            "ablation_summary_20*.csv",
            "feature_contract_20*.json",
            "leakage_assessment_20*.txt",
            "classifier_summary_eval_20*.txt",
        ]
        for pattern in diagnostics_patterns:
            targets.extend(diagnostics_dir.glob(pattern))

        # Runtime logs: keep newest N.
        runtime_dir = diagnostics_dir / "runtime_logs"
        if runtime_dir.exists():
            runtime_logs = sorted(runtime_dir.glob("pipeline_runtime_*.log"), reverse=True)
            targets.extend(runtime_logs[max(0, keep_runtime_logs):])

    # Vendor raw run folders: keep latest selected run IDs.
    vendor_raw_dir = output_dir / "vendor_raw"
    if vendor_raw_dir.exists():
        for child in vendor_raw_dir.iterdir():
            if not child.is_dir():
                continue
            run_id = _extract_run_id(child)
            if run_id and run_id in keep_run_ids:
                continue
            targets.append(child)

    # Never delete canonical current outputs.
    protected_names = {
        "obsidiandroid_outputs.xlsx",
        "obsidiandroid_outputs.xlsx.lock",
    }
    unique_targets = []
    for path in sorted(set(path for path in targets if path.exists())):
        if path.name in protected_names:
            continue
        unique_targets.append(path)
    return unique_targets


def _remove_path(path: Path) -> None:
    if path.is_dir():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
    else:
        path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean noisy output artifacts.")
    parser.add_argument("--output-dir", default="output", help="Output directory path.")
    parser.add_argument(
        "--keep-latest-runs",
        type=int,
        default=1,
        help="Number of latest run IDs to preserve for run-scoped artifacts.",
    )
    parser.add_argument(
        "--keep-runtime-logs",
        type=int,
        default=5,
        help="Number of newest runtime log files to preserve.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply deletions (default is dry-run).")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        return

    keep_run_ids = _discover_recent_run_ids(output_dir, keep_latest_runs=max(0, args.keep_latest_runs))
    targets = _collect_targets(
        output_dir,
        keep_run_ids=keep_run_ids,
        keep_runtime_logs=max(0, args.keep_runtime_logs),
    )
    if not targets:
        print("No cleanup targets found.")
        return

    if keep_run_ids:
        print(f"Preserving latest run IDs: {', '.join(sorted(keep_run_ids))}")
    print(f"Found {len(targets)} cleanup targets:")
    for target in targets:
        print(f" - {target}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete.")
        return

    for target in targets:
        _remove_path(target)
    print(f"Deleted {len(targets)} targets.")


if __name__ == "__main__":
    main()
