"""Run-slot planning and cleanup helpers for operator-facing output paths."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from obsidiandroid.common.json_io import read_json_dict

KEEP_MARKER = ".keep"
PROTECTED_MARKER = ".protected"

_SLOT_BY_PROFILE = {
    "android_malware_major_families": "majorfam_benchmark",
    "android_malware_all_current": "allcurrent_diagnostic",
    "android_malware_type_taxonomy": "typelevel_benchmark",
    "android_malware_expanded_families": "expandedfam_exploratory",
    "dev_smoke": "dev_smoke",
    "dev_fast": "dev_smoke",
    "dev_ablation_fast": "dev_smoke",
}

CANONICAL_PROFILES = (
    "android_malware_major_families",
    "android_malware_type_taxonomy",
    "android_malware_expanded_families",
    "android_malware_all_current",
)

_CANONICAL_PROFILE_SET = frozenset(CANONICAL_PROFILES)


def is_canonical_profile(profile_id: str) -> bool:
    """Return True for the four canonical benchmark/diagnostic profiles."""
    return str(profile_id or "").strip() in _CANONICAL_PROFILE_SET


@dataclass(frozen=True)
class RunSlotPlan:
    """Resolved storage contract for one pipeline run."""

    run_slot: str
    run_mode: str
    claim_surface: str
    archive_run: bool


def _slugify(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return token or "unnamed_run"


def resolve_run_slot_plan(
    *,
    profile_id: str,
    paper_locked: bool,
    evidence_mode: bool,
    keep_run_output: bool,
) -> RunSlotPlan:
    """Resolve slot, run mode, and claim surface for a run."""

    token = str(profile_id or "").strip()
    run_slot = _SLOT_BY_PROFILE.get(token, _slugify(token))

    if paper_locked:
        return RunSlotPlan(
            run_slot=run_slot,
            run_mode="locked_publication",
            claim_surface="locked_publication_cohort",
            archive_run=True,
        )
    if evidence_mode:
        return RunSlotPlan(
            run_slot=run_slot,
            run_mode="evidence_publication",
            claim_surface="evidence_publication_cohort",
            archive_run=True,
        )
    if keep_run_output:
        return RunSlotPlan(
            run_slot=run_slot,
            run_mode="milestone_keep",
            claim_surface=_claim_surface_for_profile(token),
            archive_run=True,
        )

    return RunSlotPlan(
        run_slot=run_slot,
        run_mode=_run_mode_for_profile(token),
        claim_surface=_claim_surface_for_profile(token),
        archive_run=False,
    )


def _run_mode_for_profile(profile_id: str) -> str:
    if profile_id == "android_malware_major_families":
        return "benchmark"
    if profile_id == "android_malware_type_taxonomy":
        return "benchmark"
    if profile_id == "android_malware_all_current":
        return "diagnostic"
    if profile_id == "android_malware_expanded_families":
        return "exploratory"
    if profile_id in {"dev_smoke", "dev_fast", "dev_ablation_fast"}:
        return "smoke"
    return "standard"


def _claim_surface_for_profile(profile_id: str) -> str:
    if profile_id == "android_malware_major_families":
        return "governed_major_family_benchmark"
    if profile_id == "android_malware_type_taxonomy":
        return "authoritative_type_benchmark"
    if profile_id == "android_malware_all_current":
        return "current_corpus_diagnostic"
    if profile_id == "android_malware_expanded_families":
        return "expanded_family_exploratory"
    if profile_id in {"dev_smoke", "dev_fast", "dev_ablation_fast"}:
        return "development_smoke"
    return _slugify(profile_id)


def _replace_slot_root(
    *,
    slot_root: Path,
    kept_root: Path,
    failed_root: Path,
    completed_root: Path,
    keep_last_failed_runs: int,
    keep_last_completed_runs: int,
) -> tuple[str, Path | None]:
    if not slot_root.exists():
        return "fresh_slot", None
    manifest = read_json_dict(slot_root / "run_manifest.json")
    run_instance_id = str(manifest.get("run_instance_id") or manifest.get("run_id") or slot_root.name).strip()

    if _should_keep_existing_slot(slot_root=slot_root, manifest=manifest):
        destination = _archive_slot(slot_root=slot_root, archive_parent=kept_root, run_instance_id=run_instance_id)
        return "archived_kept_slot", destination

    if keep_last_failed_runs > 0 and _slot_manifest_failed(manifest):
        destination = _archive_slot(slot_root=slot_root, archive_parent=failed_root, run_instance_id=run_instance_id)
        _prune_failed_archives(failed_root=failed_root, keep_last_failed_runs=keep_last_failed_runs)
        return "archived_failed_slot", destination

    if keep_last_completed_runs > 0 and _slot_manifest_completed(manifest):
        destination = _archive_slot(
            slot_root=slot_root, archive_parent=completed_root, run_instance_id=run_instance_id
        )
        _prune_completed_archives(
            completed_root=completed_root,
            keep_last_completed_runs=keep_last_completed_runs,
        )
        return "archived_completed_slot", destination

    # Prefer archiving when a .COMPLETE marker exists even if manifest status is stale.
    if keep_last_completed_runs > 0 and (slot_root / ".COMPLETE").exists():
        destination = _archive_slot(
            slot_root=slot_root, archive_parent=completed_root, run_instance_id=run_instance_id
        )
        _prune_completed_archives(
            completed_root=completed_root,
            keep_last_completed_runs=keep_last_completed_runs,
        )
        return "archived_completed_slot_via_marker", destination

    shutil.rmtree(slot_root, ignore_errors=True)
    return "cleared_slot", None


def prepare_run_root(
    *,
    runs_root: Path,
    run_slot: str,
    run_instance_id: str,
    archive_run: bool,
    keep_last_failed_runs: int = 0,
    keep_last_completed_runs: int = 3,
) -> dict[str, Path | str | None]:
    """Prepare and return runtime output roots for the requested run contract."""

    runs_root.mkdir(parents=True, exist_ok=True)
    archives_root = runs_root / "_archived"
    kept_root = archives_root / "kept"
    failed_root = archives_root / "failed"
    slot_root = runs_root / run_slot
    completed_root = archives_root / "completed" / run_slot

    if archive_run:
        run_root = kept_root / run_instance_id
        run_root.mkdir(parents=True, exist_ok=True)
        diagnostics_dir = run_root / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        return {
            "slot_root": slot_root,
            "run_root": run_root,
            "diagnostics_dir": diagnostics_dir,
            "cleanup_action": "archived_run_new_root",
            "previous_slot_archive": None,
        }

    cleanup_action, previous_archive = _replace_slot_root(
        slot_root=slot_root,
        kept_root=kept_root,
        failed_root=failed_root,
        completed_root=completed_root,
        keep_last_failed_runs=keep_last_failed_runs,
        keep_last_completed_runs=keep_last_completed_runs,
    )
    slot_root.mkdir(parents=True, exist_ok=True)
    diagnostics_dir = slot_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return {
        "slot_root": slot_root,
        "run_root": slot_root,
        "diagnostics_dir": diagnostics_dir,
        "cleanup_action": cleanup_action,
        "previous_slot_archive": previous_archive,
    }


def _should_keep_existing_slot(*, slot_root: Path, manifest: dict[str, Any]) -> bool:
    if (slot_root / KEEP_MARKER).exists() or (slot_root / PROTECTED_MARKER).exists():
        return True
    profile = manifest.get("profile_params")
    profile = profile if isinstance(profile, dict) else {}
    if bool(profile.get("paper_locked", False)):
        return True
    publication_mode = manifest.get("publication_ready_mode")
    if isinstance(publication_mode, dict) and bool(publication_mode.get("resolved_value")):
        return True
    if isinstance(manifest.get("paper_mode"), dict) and bool(manifest["paper_mode"].get("resolved_value")):
        return True
    return bool(manifest.get("keep_run_output", False))


def _slot_manifest_failed(manifest: dict[str, Any]) -> bool:
    status = str(manifest.get("run_status", "") or "").strip().lower()
    return status in {"failed", "interrupted"}


def _slot_manifest_completed(manifest: dict[str, Any]) -> bool:
    """Return whether a reusable slot contains a completed run worth retaining."""
    return str(manifest.get("run_status", "") or "").strip().lower() == "complete"


def _archive_slot(*, slot_root: Path, archive_parent: Path, run_instance_id: str) -> Path:
    archive_parent.mkdir(parents=True, exist_ok=True)
    destination = archive_parent / run_instance_id
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    shutil.move(str(slot_root), str(destination))
    return destination


def _prune_failed_archives(*, failed_root: Path, keep_last_failed_runs: int) -> None:
    if keep_last_failed_runs <= 0 or not failed_root.exists():
        return
    candidates: list[tuple[datetime, Path]] = []
    for child in failed_root.iterdir():
        if not child.is_dir():
            continue
        manifest = read_json_dict(child / "run_manifest.json")
        raw = str(
            manifest.get("run_started_at_utc")
            or manifest.get("timestamp_utc")
            or manifest.get("created_at_utc")
            or ""
        ).strip()
        stamp = _parse_utc(raw) or datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)
        candidates.append((stamp, child))
    for _, stale_dir in sorted(candidates, key=lambda item: item[0], reverse=True)[keep_last_failed_runs:]:
        shutil.rmtree(stale_dir, ignore_errors=True)


def _prune_completed_archives(*, completed_root: Path, keep_last_completed_runs: int) -> None:
    """Retain only the newest bounded set of automatically archived slot runs."""
    if keep_last_completed_runs <= 0 or not completed_root.exists():
        return
    candidates: list[tuple[datetime, Path]] = []
    for child in completed_root.iterdir():
        if not child.is_dir():
            continue
        manifest = read_json_dict(child / "run_manifest.json")
        raw = str(
            manifest.get("run_started_at_utc")
            or manifest.get("timestamp_utc")
            or manifest.get("created_at_utc")
            or ""
        ).strip()
        stamp = _parse_utc(raw) or datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)
        candidates.append((stamp, child))
    for _, stale_dir in sorted(candidates, key=lambda item: item[0], reverse=True)[keep_last_completed_runs:]:
        shutil.rmtree(stale_dir, ignore_errors=True)


def _parse_utc(value: str) -> datetime | None:
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
