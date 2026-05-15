"""Parser diagnostics state and artifact-location helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json

import pandas as pd

from config import app_config
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir

from . import run_locator


def output_root() -> Path:
    """Return the configured output root."""
    return canonical_output_root()


def global_diagnostics() -> Path:
    """Return the global diagnostics directory under the output root."""
    return output_root() / "diagnostics"


def run_diagnostics(run_id: str) -> Path:
    """Return the run-scoped diagnostics directory for one run id."""
    return output_root() / "runs" / run_id.strip() / "diagnostics"


def first_existing(paths: list[Path]) -> Path | None:
    """Return the first existing regular file from a candidate list."""
    for path in paths:
        if path.is_file():
            return path
    return None


def resolve_vendor_parser_coverage_csv() -> Path | None:
    """Prefer run-scoped vendor_parser_coverage, then global ``.latest``."""
    rid = run_locator.read_latest_run_id()
    candidates: list[Path] = []
    if rid:
        rd = run_diagnostics(rid)
        candidates.extend(
            [
                rd / f"vendor_parser_coverage_{rid}.csv",
                rd / "vendor_parser_coverage.latest.csv",
            ]
        )
    candidates.append(global_diagnostics() / "vendor_parser_coverage.latest.csv")
    return first_existing(candidates)


def resolve_vendor_parser_coverage_candidates_csv() -> Path | None:
    """Resolve parser onboarding candidate CSV for the latest run."""
    rid = run_locator.read_latest_run_id()
    candidates: list[Path] = []
    if rid:
        rd = run_diagnostics(rid)
        candidates.extend(
            [
                rd / f"vendor_parser_coverage_candidates_{rid}.csv",
                rd / "vendor_parser_coverage_candidates.latest.csv",
            ]
        )
    candidates.append(global_diagnostics() / "vendor_parser_coverage_candidates.latest.csv")
    return first_existing(candidates)


def resolve_vendor_gate_pre_gate_csv() -> Path | None:
    """Resolve pre-gate vendor score CSV for the latest run."""
    rid = run_locator.read_latest_run_id()
    candidates: list[Path] = []
    if rid:
        rd = run_diagnostics(rid)
        candidates.extend(
            [
                rd / f"vendor_gate_top10_pre_gate_{rid}.csv",
                rd / "vendor_gate_top10_pre_gate.latest.csv",
            ]
        )
    candidates.append(global_diagnostics() / "vendor_gate_top10_pre_gate.latest.csv")
    return first_existing(candidates)


def resolve_vendor_stress_test_csv() -> Path | None:
    """Resolve vendor parser stress-test CSV for the latest run."""
    rid = run_locator.read_latest_run_id()
    candidates: list[Path] = []
    if rid:
        rd = run_diagnostics(rid)
        candidates.extend(
            [
                rd / f"vendor_parser_stress_test_{rid}.csv",
                rd / "vendor_parser_stress_test.latest.csv",
            ]
        )
    candidates.append(global_diagnostics() / "vendor_parser_stress_test.latest.csv")
    return first_existing(candidates)


def resolve_vendor_strengths_weaknesses_csv() -> Path | None:
    """Resolve vendor parser strengths/weaknesses CSV for the latest run."""
    rid = run_locator.read_latest_run_id()
    candidates: list[Path] = []
    if rid:
        rd = run_diagnostics(rid)
        candidates.extend(
            [
                rd / f"vendor_parser_strengths_weaknesses_{rid}.csv",
                rd / "vendor_parser_strengths_weaknesses.latest.csv",
            ]
        )
    candidates.append(global_diagnostics() / "vendor_parser_strengths_weaknesses.latest.csv")
    return first_existing(candidates)


def diagnostics_dir() -> Path:
    """Resolve the active diagnostics directory under the output root."""
    return resolve_diagnostics_dir()


def read_csv(path: Path) -> pd.DataFrame:
    """Read CSV if it exists, otherwise return an empty dataframe."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_latest_manifest() -> dict[str, Any]:
    """Load the latest run manifest payload when present."""
    path = diagnostics_dir() / "run_manifest.latest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_parser_diagnostics_state(
    *,
    workbook_loader: Callable[..., object],
) -> dict[str, object]:
    """Return current parser-diagnostics capability state."""
    coverage_csv = resolve_vendor_parser_coverage_csv()
    candidates_csv = resolve_vendor_parser_coverage_candidates_csv()
    scores_csv = resolve_vendor_gate_pre_gate_csv()
    try:
        workbook_df = workbook_loader(emit_warnings=False)
    except TypeError:
        workbook_df = workbook_loader()
    workbook_ready = isinstance(workbook_df, pd.DataFrame)
    csv_ready = coverage_csv is not None
    observed_engines = 0
    parser_mapped_vendors = 0
    unmapped_vendors = 0
    if coverage_csv is not None:
        coverage_df = read_csv(coverage_csv)
        if not coverage_df.empty:
            observed_engines = int(len(coverage_df))
            parser_mapped_vendors = int(
                pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum()
            )
            unmapped_vendors = max(0, observed_engines - parser_mapped_vendors)
    manifest = read_latest_manifest()
    selected_vendors = manifest.get("selected_vendor_count")
    try:
        selected_vendors = int(selected_vendors) if selected_vendors is not None else None
    except (TypeError, ValueError):
        selected_vendors = None
    engine_scoring_universe = None
    rid = run_locator.read_latest_run_id()
    engine_csv = Path()
    if rid:
        rd = run_diagnostics(rid)
        for candidate in (rd / "engine_scoring_summary.csv", rd / "engine_scoring_summary.latest.csv"):
            if candidate.is_file():
                engine_csv = candidate
                break
    if engine_csv.is_file():
        engine_df = read_csv(engine_csv)
        if not engine_df.empty:
            engine_scoring_universe = int(len(engine_df))
    return {
        "workbook_ready": workbook_ready,
        "csv_ready": csv_ready,
        "coverage_csv_path": coverage_csv or Path(),
        "candidates_csv_path": candidates_csv or Path(),
        "scores_csv_path": scores_csv or Path(),
        "observed_engines": observed_engines,
        "parser_mapped_vendors": parser_mapped_vendors,
        "unmapped_vendors": unmapped_vendors,
        "selected_vendors": selected_vendors,
        "engine_scoring_universe": engine_scoring_universe,
    }


__all__ = [
    "build_parser_diagnostics_state",
    "diagnostics_dir",
    "first_existing",
    "global_diagnostics",
    "output_root",
    "read_csv",
    "read_latest_manifest",
    "resolve_vendor_gate_pre_gate_csv",
    "resolve_vendor_parser_coverage_candidates_csv",
    "resolve_vendor_parser_coverage_csv",
    "resolve_vendor_strengths_weaknesses_csv",
    "resolve_vendor_stress_test_csv",
    "run_diagnostics",
]
