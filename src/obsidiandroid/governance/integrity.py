"""Integrity checks for run-scoped artifact governance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import app_config
from obsidiandroid.common.output_paths import project_runtime_logs_dir

from .exceptions import IntegrityStop


@dataclass(frozen=True)
class IntegrityReport:
    """Structured integrity report for one validation pass.

    Attributes:
        passed: Whether all checks passed.
        invalid_paths: Artifact paths outside allowed roots.
        reason: Human-readable summary reason.
    """

    passed: bool
    invalid_paths: tuple[str, ...]
    reason: str


def validate_run_scoped_artifact_paths(
    *,
    artifact_paths: list[str],
    run_root: Path,
    output_root: Path,
    allow_latest: bool = True,
    run_id: str | None = None,
) -> IntegrityReport:
    """Validate that all artifact paths are run-scoped.

    Args:
        artifact_paths: Paths to validate.
        run_root: Allowed run root.
        output_root: Output root for optional latest pointer allowlist.
        allow_latest: Whether to permit ``output/latest`` descendants and operator mirrors.

    Tee logs under :func:`obsidiandroid.common.output_paths.project_runtime_logs_dir` for the
    active run instance are allowed (repo ``logs/runtime/<run_id>/``, not under ``output/runs/``).

    Returns:
        Structured report with pass/fail details.
    """
    run_root_resolved = run_root.resolve()
    latest_root = (output_root / "latest").resolve()
    diagnostics_root = (output_root / "diagnostics").resolve()
    promoted_root = (output_root / "promoted").resolve()
    runtime_run_id = str(
        run_id
        or getattr(app_config, "RUNTIME_RUN_ID", "")
        or run_root_resolved.name
        or "unknown"
    ).strip() or "unknown"
    runtime_logs_resolved = project_runtime_logs_dir(runtime_run_id).resolve()
    invalid: list[str] = []

    for raw_path in artifact_paths:
        path_text = str(raw_path).strip()
        if not path_text:
            continue
        candidate = Path(path_text)
        candidate = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
        if _is_within(candidate, run_root_resolved):
            continue
        if _is_within(candidate, runtime_logs_resolved):
            continue
        if allow_latest and _is_within(candidate, latest_root):
            continue
        if allow_latest and _is_operator_mirror_path(candidate, diagnostics_root, promoted_root):
            continue
        invalid.append(path_text)

    if invalid:
        preview = ", ".join(invalid[:5])
        return IntegrityReport(
            passed=False,
            invalid_paths=tuple(invalid),
            reason=f"non-run-scoped artifacts detected: {preview}",
        )
    return IntegrityReport(passed=True, invalid_paths=tuple(), reason="")


def enforce_run_scoped_artifact_paths(
    *,
    artifact_paths: list[str],
    run_root: Path,
    output_root: Path,
    allow_latest: bool = True,
    run_id: str | None = None,
) -> None:
    """Enforce run-scoped path policy and raise on violations.

    Args:
        artifact_paths: Paths to validate.
        run_root: Allowed run root.
        output_root: Output root for optional latest pointer allowlist.
        allow_latest: Whether to permit `output/latest` descendants.

    Raises:
        IntegrityStop: If any path is outside allowed roots.
    """
    report = validate_run_scoped_artifact_paths(
        artifact_paths=artifact_paths,
        run_root=run_root,
        output_root=output_root,
        allow_latest=allow_latest,
        run_id=run_id,
    )
    if not report.passed:
        raise IntegrityStop(f"[INTEGRITY] {report.reason}")


def _is_within(child: Path, parent: Path) -> bool:
    """Return True when `child` is under `parent`."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_operator_mirror_path(
    candidate: Path,
    diagnostics_root: Path,
    promoted_root: Path,
) -> bool:
    """Allow small global pointer/mirror files under ``output/diagnostics`` or ``output/promoted``."""
    name_lower = candidate.name.lower()
    if _is_within(candidate, promoted_root):
        return True
    if not _is_within(candidate, diagnostics_root):
        return False
    if "latest" in name_lower or "pointer" in name_lower:
        return True
    if name_lower.startswith("pipeline_stage_timings.latest"):
        return True
    if name_lower.startswith("artifact_inventory."):
        return True
    if name_lower.startswith("cohort_filter_contract.latest"):
        return True
    if name_lower.startswith("run_health_summary.latest"):
        return True
    if name_lower.startswith("run_summary.latest"):
        return True
    if name_lower.startswith("split_freeze_headline.latest"):
        return True
    if name_lower.startswith("ablation_summary.latest"):
        return True
    return False
