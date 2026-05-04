"""Runtime path resolution helpers for diagnostics and output safety."""

from __future__ import annotations

from pathlib import Path

from config import app_config


def resolve_diagnostics_dir(*, ensure_exists: bool = False) -> Path:
    """Resolve diagnostics directory with runtime-path safety guards.

    A runtime diagnostics directory is honored only when it is nested under the
    current ``DEFAULT_OUTPUT_DIR``. Otherwise, the function falls back to
    ``<DEFAULT_OUTPUT_DIR>/diagnostics``.

    Args:
        ensure_exists: When True, creates the directory tree.

    Returns:
        Normalized diagnostics directory path.
    """
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))).resolve()
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()

    diagnostics_dir = output_root / "diagnostics"
    if runtime_dir:
        runtime_path = Path(runtime_dir).resolve()
        try:
            runtime_path.relative_to(output_root)
            diagnostics_dir = runtime_path
        except ValueError:
            diagnostics_dir = output_root / "diagnostics"

    if ensure_exists:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir
