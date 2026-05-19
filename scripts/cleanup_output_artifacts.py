"""Prune noisy output artifacts while preserving current/latest results."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.common.output_cleanup_clutter import (
    DIAGNOSTICS_TIMESTAMP_GLOBS,
    LEGACY_OUTPUT_ROOT_FILES,
    LEGACY_RUN_SUBDIR_NAMES,
    PAPER_BUNDLE_ARCHIVE_GLOBS,
    PAPER_BUNDLE_SMOKE_GLOBS,
    RUN_DIAGNOSTICS_LOCAL_LATEST_GLOB,
    RUN_DIAGNOSTICS_SPLIT_FREEZE_GLOB,
    WORKBOOK_CORRUPT_GLOB,
)
from obsidiandroid.common.output_paths import project_logs_root


RUN_ID_PATTERN = re.compile(r"(\d{8}T\d{6}Z__[a-z0-9]{6})")


def _extract_run_id(path: Path) -> str | None:
    """Extract run_id token from path name when present."""
    match = RUN_ID_PATTERN.search(path.name)
    return match.group(1) if match else None


def _discover_pointed_latest_run_id(output_dir: Path) -> str | None:
    """Prefer canonical latest-run pointer files over mtime heuristics."""
    diagnostics_pointer = output_dir / "diagnostics" / "latest_run_pointer.json"
    if diagnostics_pointer.is_file():
        try:
            payload = json.loads(diagnostics_pointer.read_text(encoding="utf-8"))
            run_id = str(payload.get("run_id", "")).strip()
            if run_id:
                return run_id
        except Exception:
            pass

    promoted_manifest = output_dir / "promoted" / "latest_run_manifest.json"
    if promoted_manifest.is_file():
        try:
            payload = json.loads(promoted_manifest.read_text(encoding="utf-8"))
            run_id = str(payload.get("run_id", "")).strip()
            if run_id:
                return run_id
        except Exception:
            pass

    promoted_txt = output_dir / "promoted" / "latest_run.txt"
    if promoted_txt.is_file():
        run_id = promoted_txt.read_text(encoding="utf-8").strip()
        if run_id:
            return run_id
    return None


def _discover_recent_run_ids(output_dir: Path, keep_latest_runs: int) -> set[str]:
    """Return the newest run IDs discovered under output/runs."""
    if keep_latest_runs <= 0:
        return set()
    runs_dir = output_dir / "runs"
    run_ids_in_order: list[str] = []
    pointed_run_id = _discover_pointed_latest_run_id(output_dir)
    if pointed_run_id:
        run_ids_in_order.append(pointed_run_id)
    if runs_dir.exists():
        run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
        run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        for run_dir in run_dirs:
            run_id = _extract_run_id(run_dir) or run_dir.name
            if run_id and run_id not in run_ids_in_order:
                run_ids_in_order.append(run_id)
            if len(run_ids_in_order) >= keep_latest_runs:
                break
    return set(run_ids_in_order[:keep_latest_runs])


def _sync_promoted_latest_run_pointers(output_dir: Path) -> bool:
    """Rewrite legacy promoted latest-run pointers from the canonical diagnostics pointer."""
    diagnostics_pointer = output_dir / "diagnostics" / "latest_run_pointer.json"
    if not diagnostics_pointer.is_file():
        return False
    try:
        payload = json.loads(diagnostics_pointer.read_text(encoding="utf-8"))
    except Exception:
        return False

    run_id = str(payload.get("run_id", "")).strip()
    run_root = str(payload.get("run_root", "")).strip()
    created_at_utc = str(payload.get("created_at_utc", "")).strip()
    if not run_id:
        return False

    promoted_dir = output_dir / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    (promoted_dir / "latest_run.txt").write_text(f"{run_id}\n", encoding="utf-8")
    (promoted_dir / "latest_run_manifest.json").write_text(
        json.dumps(
            {
                "created_at_utc": created_at_utc,
                "run_id": run_id,
                "run_root": run_root,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def _collect_targets(
    output_dir: Path,
    keep_run_ids: set[str],
    keep_runtime_logs: int,
    prune_preserved_legacy: bool = False,
) -> list[Path]:
    """Build list of cleanup targets while preserving selected recent runs."""
    targets: list[Path] = []
    pipeline_runtime_candidates: list[Path] = []
    runs_dir = output_dir / "runs"

    # Run-scoped bundles/archives (keep latest selected run IDs).
    for pattern in PAPER_BUNDLE_ARCHIVE_GLOBS:
        for path in output_dir.glob(pattern):
            run_id = _extract_run_id(path)
            if run_id and run_id in keep_run_ids:
                continue
            targets.append(path)

    # Historical run-local layout clutter. Canonical artifacts already live at run_root.
    if runs_dir.exists():
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            run_id = _extract_run_id(run_dir) or run_dir.name
            preserve_run = run_id in keep_run_ids
            if preserve_run and not prune_preserved_legacy:
                continue
            for dirname in LEGACY_RUN_SUBDIR_NAMES:
                legacy_dir = run_dir / dirname
                if legacy_dir.exists():
                    targets.append(legacy_dir)
            legacy_pack_dir = run_dir / "paper2_pack"
            if legacy_pack_dir.exists() and (run_dir / "evidence_bundle").exists():
                targets.append(legacy_pack_dir)
            if preserve_run:
                continue
            diagnostics_dir = run_dir / "diagnostics"
            if diagnostics_dir.exists():
                targets.extend(p for p in diagnostics_dir.glob(RUN_DIAGNOSTICS_LOCAL_LATEST_GLOB) if p.is_file())
                targets.extend(p for p in diagnostics_dir.glob(RUN_DIAGNOSTICS_SPLIT_FREEZE_GLOB) if p.is_file())

    # Legacy global mirrors and exports now superseded by run-scoped outputs.
    for legacy_name in LEGACY_OUTPUT_ROOT_FILES:
        legacy_path = output_dir / legacy_name
        if legacy_path.exists():
            targets.append(legacy_path)

    # Smoke/debug bundle clutter (always remove).
    for pattern in PAPER_BUNDLE_SMOKE_GLOBS:
        targets.extend(output_dir.glob(pattern))

    targets.extend(output_dir.glob(WORKBOOK_CORRUPT_GLOB))

    # Timestamped diagnostics duplicates (keep `.latest.*`).
    diagnostics_dir = output_dir / "diagnostics"
    if diagnostics_dir.exists():
        for pattern in DIAGNOSTICS_TIMESTAMP_GLOBS:
            targets.extend(diagnostics_dir.glob(pattern))

        # Legacy rolling category logs (pre–repo-root ``logs/`` layout).
        logs_legacy_dir = diagnostics_dir / "logs"
        if logs_legacy_dir.exists():
            targets.extend(p for p in logs_legacy_dir.glob("*.log") if p.is_file())

        # Legacy runtime logs under output/diagnostics/runtime_logs/**/
        runtime_dir = diagnostics_dir / "runtime_logs"
        if runtime_dir.exists():
            for path in runtime_dir.rglob("pipeline_runtime_*.log"):
                if path.is_file():
                    pipeline_runtime_candidates.append(path)

    # Canonical repo logs: logs/runtime/<run_id>/pipeline_runtime_*.log
    log_runtime_root = project_logs_root() / "runtime"
    if log_runtime_root.exists():
        for path in log_runtime_root.glob("*/pipeline_runtime_*.log"):
            if path.is_file():
                pipeline_runtime_candidates.append(path)

    if pipeline_runtime_candidates:
        pipeline_runtime_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        targets.extend(pipeline_runtime_candidates[max(0, keep_runtime_logs) :])

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
    parser.add_argument(
        "--prune-preserved-legacy",
        action="store_true",
        help="Also prune redundant legacy layout dirs from the preserved latest run(s).",
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
        prune_preserved_legacy=bool(args.prune_preserved_legacy),
    )
    pointers_synced = False
    if not targets:
        if args.apply:
            pointers_synced = _sync_promoted_latest_run_pointers(output_dir)
        if pointers_synced:
            print("No cleanup targets found. Synced promoted latest-run pointers.")
        else:
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
    pointers_synced = _sync_promoted_latest_run_pointers(output_dir)
    print(f"Deleted {len(targets)} targets.")
    if pointers_synced:
        print("Synced promoted latest-run pointers from canonical diagnostics pointer.")


if __name__ == "__main__":
    main()
