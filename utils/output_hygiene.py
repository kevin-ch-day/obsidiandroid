"""Output hygiene helpers: run-scoped naming vs global operator mirrors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.common import output_paths


def resolve_stable_output_root_for_mirrors() -> Path:
    """Resolve the repo ``output/`` root even when ``DEFAULT_OUTPUT_DIR`` points at a run folder."""
    explicit = str(getattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", "") or "").strip()
    if explicit:
        return Path(explicit).resolve()
    run_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if run_root:
        p = Path(run_root).resolve()
        if p.name != "output" and "runs" in p.parts:
            try:
                idx = p.parts.index("runs")
                return Path(*p.parts[:idx]).resolve()
            except ValueError:
                pass
    return output_paths.output_root()


def global_diagnostics_root() -> Path:
    """Global ``output/diagnostics`` for ``.latest`` mirrors and pointer files."""
    return resolve_stable_output_root_for_mirrors() / str(
        getattr(app_config, "OUTPUT_DIAGNOSTICS_SUBDIR", "diagnostics")
    )


def path_is_under_output_runs(path: Path) -> bool:
    """True when the path resolves under ``.../runs/<run_id>/``."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return "runs" in resolved.parts


def run_diagnostics_should_omit_latest_duplicate() -> bool:
    """When True, writers should not emit ``*.latest.*`` inside ``runs/<id>/diagnostics``."""
    return bool(getattr(app_config, "SUPPRESS_LATEST_DUPLICATES_IN_RUN_DIRS", True))


def write_global_latest_text(*, filename: str, text: str) -> Path:
    """Write a UTF-8 text mirror under global ``output/diagnostics``."""
    out = global_diagnostics_root()
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(text, encoding="utf-8")
    return path


def write_global_latest_pointer(*, filename: str, payload: dict[str, Any]) -> Path:
    """Write a small JSON pointer under global diagnostics."""
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return write_global_latest_text(filename=filename, text=body)


def should_emit_parser_stress_and_strengths_grid() -> bool:
    """Skip heavy parser grids on dev-fast unless deep audit or forced."""
    mode = str(getattr(app_config, "OUTPUT_HYGIENE_MODE", "standard") or "standard").lower()
    if mode in {"debug_audit", "deep_audit"}:
        return True
    if bool(getattr(app_config, "OUTPUT_FORCE_PARSER_DEEP_DIAGNOSTICS", False)):
        return True
    return mode not in {"dev_fast", "dev_fast_like"}


def resolve_dataset_time_contract_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Prefer ``dataset_time_contract_<run_id>.json``; fall back to legacy ``*.latest.json``."""
    rid = str(run_id).strip()
    preferred = diagnostics_dir / f"dataset_time_contract_{rid}.json"
    legacy = diagnostics_dir / "dataset_time_contract.latest.json"
    if preferred.is_file():
        return preferred
    if legacy.is_file():
        return legacy
    return preferred


def resolve_aligned_features_cache_path(diagnostics_dir: Path, run_id: str = "") -> Path:
    """Pick existing aligned-feature export under diagnostics (run-scoped name preferred)."""
    diag = Path(diagnostics_dir)
    rid = str(run_id).strip()
    if rid:
        for candidate in (
            diag / f"aligned_features_{rid}.csv.gz",
            diag / "aligned_features.latest.csv.gz",
        ):
            if candidate.is_file():
                return candidate
    matches = sorted(diag.glob("aligned_features_*.csv.gz"))
    if matches:
        return matches[-1]
    return diag / "aligned_features.latest.csv.gz"


def resolve_analysis_snapshot_csv_path(diagnostics_dir: Path, run_id: str) -> Path | None:
    """Return an existing analysis snapshot CSV under run diagnostics, or ``None``."""
    rid = str(run_id).strip()
    if not rid:
        return None
    for candidate in (
        diagnostics_dir / f"analysis_snapshot_{rid}.csv",
        diagnostics_dir / "analysis_snapshot.latest.csv",
    ):
        if candidate.is_file():
            return candidate
    return None


def mirror_csv_text_run_then_global(
    *,
    diagnostics_dir: Path,
    run_filename: str,
    csv_text: str,
    global_latest_name: str,
) -> list[Path]:
    """Write run-scoped CSV then either global ``output/diagnostics`` latest or legacy local latest.

    Returns all paths written (1–2).
    """
    out_dir = Path(diagnostics_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    primary = out_dir / run_filename
    primary.write_text(csv_text, encoding="utf-8")
    written: list[Path] = [primary]
    if run_diagnostics_should_omit_latest_duplicate() and path_is_under_output_runs(out_dir):
        written.append(write_global_latest_text(filename=global_latest_name, text=csv_text))
    else:
        legacy = out_dir / global_latest_name
        legacy.write_text(csv_text, encoding="utf-8")
        written.append(legacy)
    return written


__all__ = [
    "global_diagnostics_root",
    "mirror_csv_text_run_then_global",
    "path_is_under_output_runs",
    "resolve_aligned_features_cache_path",
    "resolve_analysis_snapshot_csv_path",
    "resolve_dataset_time_contract_path",
    "resolve_stable_output_root_for_mirrors",
    "run_diagnostics_should_omit_latest_duplicate",
    "should_emit_parser_stress_and_strengths_grid",
    "write_global_latest_pointer",
    "write_global_latest_text",
]
