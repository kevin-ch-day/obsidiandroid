"""Prune noisy output artifacts while preserving current/latest results."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

from obsidiandroid.common.output_cleanup_clutter import (
    DIAGNOSTICS_TIMESTAMP_GLOBS,
    LEGACY_OUTPUT_ROOT_FILES,
    LEGACY_RUN_SUBDIR_NAMES,
    LEGACY_SHORT_NAME_LOG_FILES,
    PAPER_BUNDLE_ARCHIVE_GLOBS,
    PAPER_BUNDLE_SMOKE_GLOBS,
    RUN_BOUND_LATEST_MIRROR_FILES,
    RUN_DIAGNOSTICS_LOCAL_LATEST_GLOB,
    RUN_DIAGNOSTICS_SPLIT_FREEZE_GLOB,
    WORKBOOK_CORRUPT_GLOB,
)
from obsidiandroid.common.output_paths import project_logs_root


RUN_ID_PATTERN = re.compile(r"(\d{8}T\d{6}Z__[a-z0-9]{6})")
CANONICAL_RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z__[a-z0-9]{6}$")


def _extract_run_id(path: Path) -> str | None:
    """Extract run_id token from path name when present."""
    match = RUN_ID_PATTERN.search(path.name)
    return match.group(1) if match else None


def _is_canonical_run_id(run_id: object) -> bool:
    """Return whether an ID is eligible for retention as a real pipeline run."""
    return bool(CANONICAL_RUN_ID_PATTERN.fullmatch(str(run_id or "").strip()))


def _parse_iso_utc(value: object) -> datetime | None:
    """Parse ISO-ish UTC timestamp strings used in manifests/pointers."""
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_run_id_timestamp(run_id: str) -> datetime | None:
    """Parse UTC timestamp embedded in canonical run IDs."""
    token = str(run_id or "").strip()
    match = RUN_ID_PATTERN.search(token)
    if not match:
        return None
    stamp = match.group(1).split("__", maxsplit=1)[0]
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def _resolve_existing_run_root(output_dir: Path, *, run_id: str, run_root_raw: str = "") -> Path | None:
    """Resolve an existing run root from a pointer or run ID."""
    output_root = output_dir.resolve()
    candidate_roots: list[Path] = []
    if run_root_raw:
        run_root = Path(run_root_raw)
        if run_root.is_absolute():
            candidate_roots.append(run_root)
        else:
            # Pointer files commonly store paths such as ``output/runs/<id>``.
            # Resolve those relative to the supplied output root's parent, not
            # the process CWD; otherwise a temporary/audited output root can
            # accidentally adopt a live repository run with the same pointer.
            candidate_roots.extend((output_root.parent / run_root, output_root / run_root))
    if run_id:
        candidate_roots.append(output_root / "runs" / run_id)

    seen: set[Path] = set()
    for candidate in candidate_roots:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            resolved.relative_to(output_root)
        except ValueError:
            continue
        if (resolved / "run_manifest.json").is_file():
            return resolved

    runs_dir = output_root / "runs"
    if not runs_dir.exists():
        return None
    target = str(run_id).strip()
    for manifest_path in runs_dir.rglob("run_manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        manifest_run_id = str(payload.get("run_id", "")).strip()
        if target and manifest_run_id == target:
            return manifest_path.parent.resolve()
    return None


def _iter_run_manifest_records(output_dir: Path) -> list[tuple[tuple[int, datetime, str], dict[str, object], Path]]:
    """Return sortable manifest records discovered under output/runs."""
    runs_dir = output_dir / "runs"
    records: list[tuple[tuple[int, datetime, str], dict[str, object], Path]] = []
    if not runs_dir.exists():
        return records
    for manifest_path in runs_dir.rglob("run_manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        run_root = manifest_path.parent.resolve()
        run_id = str(payload.get("run_id", "")).strip() or _extract_run_id(run_root) or run_root.name
        if not _is_canonical_run_id(run_id):
            continue
        timestamp = (
            _parse_iso_utc(payload.get("timestamp_utc"))
            or _parse_iso_utc(payload.get("run_started_at_utc"))
            or _parse_iso_utc(payload.get("created_at_utc"))
            or _parse_run_id_timestamp(run_id)
        )
        if timestamp is None:
            try:
                timestamp = datetime.fromtimestamp(run_root.stat().st_mtime, tz=UTC)
            except OSError:
                continue
        records.append(((1, timestamp, run_id), payload, run_root))
    return records


def _build_pointer_payload_from_manifest(manifest_payload: dict[str, object], run_root: Path) -> dict[str, str]:
    """Build canonical latest-run pointer payload from a full manifest."""
    run_id = str(manifest_payload.get("run_id", "")).strip() or run_root.name
    profile_params = manifest_payload.get("profile_params")
    profile_params = profile_params if isinstance(profile_params, dict) else {}
    profile_id = (
        str(manifest_payload.get("profile_id", "")).strip()
        or str(profile_params.get("profile_id", "")).strip()
    )
    created_at = (
        str(manifest_payload.get("timestamp_utc", "")).strip()
        or str(manifest_payload.get("created_at_utc", "")).strip()
    )
    return {
        "run_id": run_id,
        "run_instance_id": str(manifest_payload.get("run_instance_id", "")).strip() or run_id,
        "run_slot": str(manifest_payload.get("run_slot", "")).strip(),
        "run_started_at_utc": str(manifest_payload.get("run_started_at_utc", "")).strip() or created_at,
        "profile_id": profile_id,
        "run_mode": str(manifest_payload.get("run_mode", "")).strip(),
        "claim_surface": str(manifest_payload.get("claim_surface", "")).strip(),
        "created_at_utc": created_at,
        "run_root": str(run_root).replace("\\", "/"),
    }


def _resolve_latest_pointer_payload(output_dir: Path) -> dict[str, str] | None:
    """Resolve a valid latest-run pointer payload from manifests or discovered runs."""
    pointer_candidates = [
        output_dir / "diagnostics" / "latest_run_pointer.json",
        output_dir / "promoted" / "latest_run_manifest.json",
    ]
    for pointer_path in pointer_candidates:
        if not pointer_path.is_file():
            continue
        try:
            pointer_payload = json.loads(pointer_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(pointer_payload, dict):
            continue
        run_id = str(pointer_payload.get("run_id", "")).strip()
        if not _is_canonical_run_id(run_id):
            continue
        run_root = _resolve_existing_run_root(
            output_dir,
            run_id=run_id,
            run_root_raw=str(pointer_payload.get("run_root", "")).strip(),
        )
        if run_root is None:
            continue
        manifest_path = run_root / "run_manifest.json"
        if manifest_path.is_file():
            try:
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest_payload = {}
            if isinstance(manifest_payload, dict):
                return _build_pointer_payload_from_manifest(manifest_payload, run_root)
        sanitized = dict(pointer_payload)
        sanitized["run_root"] = str(run_root).replace("\\", "/")
        if run_id:
            sanitized["run_id"] = run_id
        return {str(key): str(value) for key, value in sanitized.items() if key}

    manifest_latest_path = output_dir / "diagnostics" / "run_manifest.latest.json"
    if manifest_latest_path.is_file():
        try:
            manifest_payload = json.loads(manifest_latest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest_payload = {}
        if isinstance(manifest_payload, dict):
            run_id = str(manifest_payload.get("run_id", "")).strip()
            if not _is_canonical_run_id(run_id):
                run_id = ""
            if not run_id:
                manifest_payload = {}
        if isinstance(manifest_payload, dict) and manifest_payload:
            run_root = _resolve_existing_run_root(
                output_dir,
                run_id=run_id,
                run_root_raw=str(manifest_payload.get("run_root", "")).strip(),
            )
            if run_root is not None:
                return _build_pointer_payload_from_manifest(manifest_payload, run_root)

    records = _iter_run_manifest_records(output_dir)
    if not records:
        return None
    _sort_key, manifest_payload, run_root = max(records, key=lambda item: item[0])
    return _build_pointer_payload_from_manifest(manifest_payload, run_root)


def _discover_pointed_latest_run_id(output_dir: Path) -> str | None:
    """Prefer canonical latest-run pointer files over mtime heuristics."""
    payload = _resolve_latest_pointer_payload(output_dir)
    if not payload:
        return None
    run_id = str(payload.get("run_id", "")).strip()
    return run_id or None


def _discover_recent_run_ids(output_dir: Path, keep_latest_runs: int) -> set[str]:
    """Return newest manifest-backed run IDs under output/runs."""
    if keep_latest_runs <= 0:
        return set()
    run_ids_in_order: list[str] = []
    pointed_run_id = _discover_pointed_latest_run_id(output_dir)
    if pointed_run_id:
        run_ids_in_order.append(pointed_run_id)
    for _sort_key, manifest_payload, run_root in sorted(
        _iter_run_manifest_records(output_dir),
        key=lambda item: item[0],
        reverse=True,
    ):
        run_id = str(manifest_payload.get("run_id", "")).strip() or _extract_run_id(run_root) or run_root.name
        if run_id and run_id not in run_ids_in_order:
            run_ids_in_order.append(run_id)
        if len(run_ids_in_order) >= keep_latest_runs:
            break
    return set(run_ids_in_order[:keep_latest_runs])


def _sync_promoted_latest_run_pointers(output_dir: Path) -> bool:
    """Rewrite latest-run pointers from a valid manifest-backed source."""
    payload = _resolve_latest_pointer_payload(output_dir)
    if not payload:
        return False

    run_id = str(payload.get("run_id", "")).strip()
    run_root = str(payload.get("run_root", "")).strip()
    created_at_utc = str(payload.get("created_at_utc", "")).strip()
    if not run_id:
        return False

    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "latest_run_pointer.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

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


def _is_stale_run_bound_latest_mirror(path: Path, latest_run_id: str) -> bool:
    """Return True when a run-bound latest mirror does not match the current latest run."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    if latest_run_id and latest_run_id in text:
        return False
    run_bound_tokens = ('"run_id"', "Run ID:", "output/runs/")
    return any(token in text for token in run_bound_tokens)


def _collect_targets(
    output_dir: Path,
    keep_run_ids: set[str],
    keep_runtime_logs: int,
    prune_preserved_legacy: bool = False,
) -> list[Path]:
    """Build list of cleanup targets while preserving selected recent runs."""
    targets: list[Path] = []
    pipeline_runtime_candidates: list[Path] = []
    runtime_category_targets: list[Path] = []
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
            manifest_path = run_dir / "run_manifest.json"
            if not manifest_path.is_file() and run_dir.name.startswith("_"):
                continue
            run_id = ""
            if manifest_path.is_file():
                try:
                    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest_payload = {}
                run_id = str(manifest_payload.get("run_id", "")).strip()
            run_id = run_id or _extract_run_id(run_dir) or run_dir.name
            if not _is_canonical_run_id(run_id):
                # Test fixtures and interrupted manual experiments must not
                # occupy a retention slot or remain as misleading run history.
                targets.append(run_dir)
                continue
            preserve_run = run_id in keep_run_ids
            if preserve_run and not prune_preserved_legacy:
                continue
            for dirname in LEGACY_RUN_SUBDIR_NAMES:
                legacy_dir = run_dir / dirname
                if legacy_dir.exists():
                    targets.append(legacy_dir)
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

    # Repo-root legacy short-name logs now superseded by clearer canonical names.
    logs_root = project_logs_root()
    if logs_root.exists():
        for legacy_name in LEGACY_SHORT_NAME_LOG_FILES:
            legacy_path = logs_root / legacy_name
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

        latest_payload = _resolve_latest_pointer_payload(output_dir) or {}
        latest_run_id = str(latest_payload.get("run_id", "")).strip()
        if latest_run_id:
            for name in RUN_BOUND_LATEST_MIRROR_FILES:
                path = diagnostics_dir / name
                if path.is_file() and _is_stale_run_bound_latest_mirror(path, latest_run_id):
                    targets.append(path)

        # Legacy rolling category logs (pre–repo-root ``logs/`` layout).
        logs_legacy_dir = diagnostics_dir / "logs"
        if logs_legacy_dir.exists():
            targets.extend(p for p in logs_legacy_dir.glob("*.log") if p.is_file())

        # Legacy runtime logs under output/diagnostics/runtime_logs/**/
        runtime_dir = diagnostics_dir / "runtime_logs"
        if runtime_dir.exists():
            for path in runtime_dir.rglob("pipeline_runtime*.log"):
                if path.is_file():
                    pipeline_runtime_candidates.append(path)

    # Canonical repo logs: logs/runtime/<run_id>/pipeline_runtime_console_*.log
    log_runtime_root = project_logs_root() / "runtime"
    if log_runtime_root.exists():
        for run_dir in log_runtime_root.iterdir():
            if not run_dir.is_dir():
                continue
            run_id = _extract_run_id(run_dir) or run_dir.name
            preserve_run = run_id in keep_run_ids
            for path in run_dir.glob("*.log"):
                if not path.is_file():
                    continue
                if path.name.startswith("pipeline_runtime"):
                    pipeline_runtime_candidates.append(path)
                    continue
                if path.name in LEGACY_SHORT_NAME_LOG_FILES and (not preserve_run or prune_preserved_legacy):
                    runtime_category_targets.append(path)

    if pipeline_runtime_candidates:
        pipeline_runtime_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        targets.extend(pipeline_runtime_candidates[max(0, keep_runtime_logs) :])
    targets.extend(runtime_category_targets)

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


def _prune_empty_runtime_log_dirs(logs_root: Path) -> int:
    """Remove empty ``logs/runtime/<run_id>/`` directories after file pruning."""
    runtime_root = logs_root / "runtime"
    if not runtime_root.exists():
        return 0
    removed = 0
    for path in sorted(runtime_root.rglob("*"), reverse=True):
        if not path.is_dir():
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
            removed += 1
    return removed


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
        empty_runtime_dirs_removed = 0
        if args.apply:
            empty_runtime_dirs_removed = _prune_empty_runtime_log_dirs(project_logs_root())
            pointers_synced = _sync_promoted_latest_run_pointers(output_dir)
        if pointers_synced and empty_runtime_dirs_removed:
            print(
                "No cleanup targets found. "
                f"Removed {empty_runtime_dirs_removed} empty runtime log director"
                f"{'y' if empty_runtime_dirs_removed == 1 else 'ies'} and synced promoted latest-run pointers."
            )
        elif pointers_synced:
            print("No cleanup targets found. Synced promoted latest-run pointers.")
        elif empty_runtime_dirs_removed:
            print(
                "No cleanup targets found. "
                f"Removed {empty_runtime_dirs_removed} empty runtime log director"
                f"{'y' if empty_runtime_dirs_removed == 1 else 'ies'}."
            )
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
    empty_runtime_dirs_removed = _prune_empty_runtime_log_dirs(project_logs_root())
    pointers_synced = _sync_promoted_latest_run_pointers(output_dir)
    print(f"Deleted {len(targets)} targets.")
    if empty_runtime_dirs_removed:
        print(f"Removed {empty_runtime_dirs_removed} empty runtime log director{'y' if empty_runtime_dirs_removed == 1 else 'ies'}.")
    if pointers_synced:
        print("Synced promoted latest-run pointers from canonical diagnostics pointer.")


if __name__ == "__main__":
    main()
