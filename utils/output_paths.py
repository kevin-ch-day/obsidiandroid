"""Canonical output directory layout helpers.

This module centralizes output path resolution so pipeline stages avoid
hard-coded root-relative paths and keep artifacts organized by domain.
"""

from __future__ import annotations

from pathlib import Path

from config import app_config


def output_root() -> Path:
    """Return the configured output root."""
    return Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))).resolve()


def runs_root() -> Path:
    """Return output root for run-scoped artifacts."""
    return output_root() / str(getattr(app_config, "OUTPUT_RUNS_SUBDIR", "runs"))


def resolve_runtime_run_directory(run_id: str) -> Path:
    """Return the directory that holds run-scoped artifacts (e.g. ``conf_matrices/``).

    Prefers :attr:`RUNTIME_RUN_ROOT` when its final segment matches ``run_id``
    (including evidence mode where ``DEFAULT_OUTPUT_DIR`` points at the run folder).
    Otherwise uses ``output_root() / runs / run_id`` (standard layout).
    """
    rid = str(run_id).strip()
    runtime_root_raw = getattr(app_config, "RUNTIME_RUN_ROOT", None)
    if runtime_root_raw:
        path = Path(str(runtime_root_raw)).expanduser().resolve()
        if path.name == rid:
            return path
    runs_sub = str(getattr(app_config, "OUTPUT_RUNS_SUBDIR", "runs"))
    return output_root() / runs_sub / rid


def bundles_root() -> Path:
    """Return output root for paper/report bundles."""
    return output_root() / str(getattr(app_config, "OUTPUT_BUNDLES_SUBDIR", "bundles"))


def reports_root() -> Path:
    """Return output root for high-level global reports."""
    return output_root() / str(getattr(app_config, "OUTPUT_REPORTS_SUBDIR", "reports"))


def diagnostics_root() -> Path:
    """Return output root for global diagnostics."""
    return output_root() / str(getattr(app_config, "OUTPUT_DIAGNOSTICS_SUBDIR", "diagnostics"))


def logs_root() -> Path:
    """Return output root for global logs."""
    return output_root() / str(getattr(app_config, "OUTPUT_LOGS_SUBDIR", "logs"))


def latest_root() -> Path:
    """Return output root for mutable latest pointers/copies."""
    return output_root() / str(getattr(app_config, "OUTPUT_LATEST_SUBDIR", "latest"))


def promoted_root() -> Path:
    """Return output root for promoted convenience mirrors/pointers."""
    return output_root() / str(getattr(app_config, "OUTPUT_PROMOTED_SUBDIR", "promoted"))


def ensure_output_layout() -> dict[str, Path]:
    """Create and return canonical top-level output directories."""
    roots = {
        "output_root": output_root(),
        "runs_root": runs_root(),
        "bundles_root": bundles_root(),
        "reports_root": reports_root(),
        "diagnostics_root": diagnostics_root(),
        "logs_root": logs_root(),
        "latest_root": latest_root(),
        "promoted_root": promoted_root(),
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    return roots
