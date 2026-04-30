"""Integrity checks for run-scoped artifact governance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
) -> IntegrityReport:
    """Validate that all artifact paths are run-scoped.

    Args:
        artifact_paths: Paths to validate.
        run_root: Allowed run root.
        output_root: Output root for optional latest pointer allowlist.
        allow_latest: Whether to permit `output/latest` descendants.

    Returns:
        Structured report with pass/fail details.
    """
    run_root_resolved = run_root.resolve()
    latest_root = (output_root / "latest").resolve()
    invalid: list[str] = []

    for raw_path in artifact_paths:
        path_text = str(raw_path).strip()
        if not path_text:
            continue
        candidate = Path(path_text)
        candidate = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
        if _is_within(candidate, run_root_resolved):
            continue
        if allow_latest and _is_within(candidate, latest_root):
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

