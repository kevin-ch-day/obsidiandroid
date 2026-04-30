"""Path-safety helpers for run-scoped output enforcement."""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a path escapes the permitted run root."""


def safe_join(run_root: Path, relative_path: str | Path) -> Path:
    """Resolve a path under `run_root` and reject escapes."""
    root = run_root.resolve()
    normalized_relative = str(relative_path).replace("\\", "/")
    candidate = (root / Path(normalized_relative)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes run root: {relative_path}") from exc
    return candidate
