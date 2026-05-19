"""Output hygiene helpers: run-scoped naming vs global operator mirrors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.common import output_paths


def normalize_artifact_run_id(run_id: object, *, default: str = "unknown") -> str:
    """Return a safe run-id token for artifact filenames and mirrors."""
    rid = str(run_id or "").strip()
    if not rid or rid.lower() == "none":
        return default
    return rid


def validate_diagnostics_output_dir(diagnostics_dir: Path) -> Path:
    """Reject placeholder diagnostics roots such as the literal top-level ``None/`` directory."""
    out_dir = Path(diagnostics_dir)
    if str(out_dir).strip().lower() == "none":
        raise ValueError(
            "diagnostics_dir resolved to the literal 'None' path; "
            "set a real diagnostics directory before writing artifacts"
        )
    return out_dir


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


def resolve_run_or_global_artifact_path(
    diagnostics_dir: Path,
    *,
    run_filename: str,
    global_latest_name: str,
    local_latest_name: str | None = None,
) -> Path:
    """Resolve a canonical run-scoped artifact first, then local/global latest mirrors.

    Returns the first existing path, or the canonical run-scoped candidate when none exist.
    """
    diag = Path(diagnostics_dir)
    candidates = [diag / str(run_filename)]
    latest_name = str(local_latest_name or global_latest_name)
    if latest_name:
        candidates.append(diag / latest_name)
    candidates.append(global_diagnostics_root() / str(global_latest_name))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def resolve_taxonomy_consistency_summary_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve taxonomy consistency summary across run-scoped and global-latest locations."""
    rid = normalize_artifact_run_id(run_id)
    return resolve_run_or_global_artifact_path(
        diagnostics_dir,
        run_filename=f"taxonomy_consistency_summary_{rid}.json",
        global_latest_name="taxonomy_consistency_summary.latest.json",
    )


def resolve_feature_column_survival_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve feature-column survival CSV across run-scoped and global-latest locations."""
    rid = normalize_artifact_run_id(run_id)
    return resolve_run_or_global_artifact_path(
        diagnostics_dir,
        run_filename=f"feature_column_survival_{rid}.csv",
        global_latest_name="feature_column_survival.latest.csv",
    )


def mirror_utf8_text_run_then_global(
    *,
    diagnostics_dir: Path,
    run_filename: str,
    text: str,
    global_latest_name: str,
) -> list[Path]:
    """Write run-scoped UTF-8 text then either global ``output/diagnostics`` latest or legacy local latest.

    Used by :func:`mirror_csv_text_run_then_global`, :func:`mirror_json_text_run_then_global`, and
    plain-text methodology mirrors (leakage assessment, etc.).
    """
    out_dir = validate_diagnostics_output_dir(diagnostics_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    primary = out_dir / run_filename
    primary.write_text(text, encoding="utf-8")
    written: list[Path] = [primary]
    if run_diagnostics_should_omit_latest_duplicate() and path_is_under_output_runs(out_dir):
        written.append(write_global_latest_text(filename=global_latest_name, text=text))
    else:
        legacy = out_dir / global_latest_name
        legacy.write_text(text, encoding="utf-8")
        written.append(legacy)
    return written


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
    return mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=run_filename,
        text=csv_text,
        global_latest_name=global_latest_name,
    )


def mirror_json_text_run_then_global(
    *,
    diagnostics_dir: Path,
    run_filename: str,
    payload: dict[str, Any],
    global_latest_name: str,
    indent: int = 2,
) -> list[Path]:
    """Write run-scoped JSON then either global ``.latest`` mirror or legacy local duplicate.

    Mirrors :func:`mirror_csv_text_run_then_global` for structured JSON artifacts.
    """
    text = json.dumps(payload, indent=indent, sort_keys=True) + "\n"
    return mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=run_filename,
        text=text,
        global_latest_name=global_latest_name,
    )


__all__ = [
    "global_diagnostics_root",
    "normalize_artifact_run_id",
    "mirror_csv_text_run_then_global",
    "mirror_json_text_run_then_global",
    "mirror_utf8_text_run_then_global",
    "path_is_under_output_runs",
    "resolve_feature_column_survival_path",
    "resolve_aligned_features_cache_path",
    "resolve_analysis_snapshot_csv_path",
    "resolve_dataset_time_contract_path",
    "resolve_run_or_global_artifact_path",
    "resolve_stable_output_root_for_mirrors",
    "resolve_taxonomy_consistency_summary_path",
    "run_diagnostics_should_omit_latest_duplicate",
    "should_emit_parser_stress_and_strengths_grid",
    "validate_diagnostics_output_dir",
    "write_global_latest_pointer",
    "write_global_latest_text",
]
