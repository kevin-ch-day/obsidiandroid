"""Shared run and workbook resolution helpers for operator-facing menus."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import app_config
from obsidiandroid.common import output_paths
from obsidiandroid.common.json_io import read_json_dict

_RUN_ID_TIMESTAMP_PATTERN = re.compile(r"^(?P<ts>\d{8}T\d{6}Z)__.+$")


def read_json_object(path: Path) -> dict:
    """Read a JSON object from disk or return an empty mapping.

    Args:
        path: File path to load.

    Returns:
        Parsed object when the file exists and contains a JSON object.
    """
    return read_json_dict(path)


def parse_run_timestamp_from_manifest(manifest_payload: dict[str, object]) -> datetime | None:
    """Parse canonical UTC timestamp fields from a run manifest."""
    for key in ("timestamp_utc", "created_at_utc"):
        raw = str(manifest_payload.get(key, "") or "").strip()
        if not raw:
            continue
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def parse_run_timestamp_from_id(run_id: str) -> datetime | None:
    """Parse UTC timestamp embedded in canonical run IDs."""
    match = _RUN_ID_TIMESTAMP_PATTERN.match(str(run_id).strip())
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group("ts"), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def candidate_sort_key(
    *,
    run_id: str,
    manifest_payload: dict[str, object] | None = None,
) -> tuple[int, datetime, str] | None:
    """Build a sortable key for run candidates."""
    token = str(run_id).strip()
    if not token:
        return None

    timestamp = parse_run_timestamp_from_manifest(manifest_payload or {})
    if timestamp is None:
        timestamp = parse_run_timestamp_from_id(token)
    if timestamp is None:
        return None
    return (1, timestamp, token)


def discover_latest_run_id_from_runs(
    *,
    required_markers: Iterable[str] | None = None,
) -> str | None:
    """Return newest run ID discovered under the run-scoped output tree."""
    runs_dir = output_paths.runs_root()
    if not runs_dir.exists():
        return None

    markers = tuple(required_markers or ("run_manifest.json",))
    candidates: list[tuple[tuple[int, datetime, str] | None, str]] = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        if markers and not any((child / marker).exists() for marker in markers):
            continue
        run_id = child.name.strip()
        if not run_id:
            continue
        manifest_payload = read_json_object(child / "run_manifest.json")
        candidates.append((candidate_sort_key(run_id=run_id, manifest_payload=manifest_payload), run_id))

    if not candidates:
        return None
    valid = [item for item in candidates if item[0] is not None]
    if valid:
        return max(valid, key=lambda item: item[0])[1]
    return max(candidates, key=lambda item: item[1])[1]


def read_latest_run_id() -> str | None:
    """Return the best current latest run ID across canonical and legacy pointers."""
    candidates: list[tuple[tuple[int, datetime, str] | None, str]] = []

    discovered_run_id = discover_latest_run_id_from_runs()
    if discovered_run_id:
        candidates.append((candidate_sort_key(run_id=discovered_run_id), discovered_run_id))

    promoted_pointer = output_paths.promoted_root() / "latest_run.txt"
    if promoted_pointer.exists():
        try:
            run_id = promoted_pointer.read_text(encoding="utf-8").strip()
        except Exception:
            run_id = ""
        if run_id:
            candidates.append((candidate_sort_key(run_id=run_id), run_id))

    manifest_path = output_paths.diagnostics_root() / "run_manifest.latest.json"
    manifest_payload = read_json_object(manifest_path)
    manifest_run_id = str(manifest_payload.get("run_id", "")).strip()
    if manifest_run_id:
        candidates.append(
            (
                candidate_sort_key(run_id=manifest_run_id, manifest_payload=manifest_payload),
                manifest_run_id,
            )
        )

    if not candidates:
        return None
    valid = [item for item in candidates if item[0] is not None]
    if valid:
        return max(valid, key=lambda item: item[0])[1]
    return max(candidates, key=lambda item: item[1])[1]


def resolve_manifest_for_run_id(run_id: str) -> tuple[dict, Path]:
    """Resolve canonical run-scoped manifest for a specific run ID."""
    canonical_path = output_paths.runs_root() / str(run_id).strip() / "run_manifest.json"
    return read_json_object(canonical_path), canonical_path


def resolve_latest_manifest_payload() -> tuple[dict, str | None, Path]:
    """Resolve latest manifest payload, following pointer manifests when needed."""
    latest_path = output_paths.diagnostics_root() / "run_manifest.latest.json"
    latest_payload = read_json_object(latest_path)
    if not latest_payload:
        return {}, None, latest_path

    run_id = str(latest_payload.get("run_id", "")).strip() or None
    is_pointer_only = "profile_params" not in latest_payload and "artifact_list" not in latest_payload
    if not is_pointer_only:
        return latest_payload, run_id, latest_path

    run_root_raw = str(latest_payload.get("run_root", "")).strip()
    if run_root_raw:
        run_root = Path(run_root_raw)
    elif run_id:
        run_root = output_paths.runs_root() / run_id
    else:
        run_root = output_paths.runs_root()

    canonical_path = run_root / "run_manifest.json"
    canonical_payload = read_json_object(canonical_path)
    if canonical_payload:
        canonical_run_id = str(canonical_payload.get("run_id", "")).strip()
        return canonical_payload, (canonical_run_id or run_id), canonical_path
    return latest_payload, run_id, latest_path


def resolve_run_root_for_manifest(
    manifest: dict,
    *,
    run_id: str | None,
    manifest_path: Path,
) -> Path:
    """Resolve run root for a manifest payload."""
    run_root_raw = str(manifest.get("run_root", "") or "").strip()
    if run_root_raw:
        return Path(run_root_raw)
    if manifest_path.name == "run_manifest.json":
        return manifest_path.parent
    if run_id:
        return output_paths.runs_root() / run_id
    return output_paths.runs_root()


def read_locked_paper_run_id() -> str | None:
    """Return locked publication/evidence run pointer when available."""
    diagnostics_root = output_paths.diagnostics_root()
    candidates = [
        diagnostics_root / "evidence_locked_run.txt",
        diagnostics_root / "paper2_locked_run.txt",
    ]
    pointer = next((path for path in candidates if path.exists()), candidates[0])
    if not pointer.exists():
        return None
    try:
        run_id = pointer.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return run_id or None


def candidate_workbook_paths() -> list[Path]:
    """Return likely consolidated workbook paths in priority order."""
    filename = str(getattr(app_config, "CONSOLIDATED_EXCEL_FILENAME", "obsidiandroid_outputs.xlsx"))
    candidates: list[Path] = []

    runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if runtime_root:
        candidates.append(Path(runtime_root) / filename)

    newest_run_id = discover_latest_run_id_from_runs(
        required_markers=("run_manifest.json", filename)
    )
    if newest_run_id:
        candidates.append(output_paths.runs_root() / newest_run_id / filename)

    promoted_pointer = output_paths.promoted_root() / "latest_run.txt"
    if promoted_pointer.exists():
        try:
            latest_run_id = promoted_pointer.read_text(encoding="utf-8").strip()
        except Exception:
            latest_run_id = ""
        if latest_run_id:
            candidates.append(output_paths.runs_root() / latest_run_id / filename)

    candidates.extend(
        [
            output_paths.reports_root() / filename,
            output_paths.output_root() / filename,
            output_paths.latest_root() / filename,
        ]
    )

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates
