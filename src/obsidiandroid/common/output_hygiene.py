"""Output hygiene helpers: run-scoped naming vs global operator mirrors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import app_config
from obsidiandroid.common import output_paths

RUN_SCOPED_ONLY = "run_scoped_only"
RUN_SCOPED_PLUS_POINTER = "run_scoped_plus_pointer"
RUN_SCOPED_PLUS_GLOBAL_LATEST_MIRROR = "run_scoped_plus_global_latest_mirror"
RUN_SCOPED_PLUS_LOCAL_LATEST_DUPLICATE = "run_scoped_plus_local_latest_duplicate"
DEBUG_ONLY = "debug_only"
LEGACY_COMPATIBILITY_ONLY = "legacy_compatibility_only"


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


def classify_artifact_origin(path: Path | None, diagnostics_dir: Path) -> str:
    """Classify one diagnostics artifact path for operator provenance reporting.

    Returns one of:
    - ``missing`` when no path is available
    - ``run_scoped`` for canonical/stamped artifacts under the run diagnostics dir
    - ``run_local_latest_duplicate`` for ``*.latest.*`` files under the run diagnostics dir
    - ``global_latest_mirror`` for ``output/diagnostics/*.latest.*`` mirrors
    - ``other`` when the path exists but falls outside the expected run/global roots
    """
    if path is None:
        return "missing"
    try:
        resolved = Path(path).resolve()
        run_diag = Path(diagnostics_dir).resolve()
        global_diag = global_diagnostics_root().resolve()
    except OSError:
        return "other"
    if resolved.parent == run_diag:
        return "run_local_latest_duplicate" if ".latest." in resolved.name else "run_scoped"
    if resolved.parent == global_diag:
        return "global_latest_mirror"
    return "other"


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


def diagnostics_mirror_write_policy(diagnostics_dir: Path) -> str:
    """Return the effective latest-mirror policy for a diagnostics directory."""
    if path_is_under_output_runs(Path(diagnostics_dir)) and run_diagnostics_should_omit_latest_duplicate():
        return RUN_SCOPED_PLUS_GLOBAL_LATEST_MIRROR
    return RUN_SCOPED_PLUS_LOCAL_LATEST_DUPLICATE


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


def _resolve_stamped_run_or_global_artifact_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    run_filename_template: str,
    global_latest_name: str,
    local_latest_name: str | None = None,
) -> Path:
    """Resolve one stamped run artifact first, then local/global latest mirrors."""
    rid = normalize_artifact_run_id(run_id)
    return resolve_run_or_global_artifact_path(
        diagnostics_dir,
        run_filename=run_filename_template.format(run_id=rid),
        global_latest_name=global_latest_name,
        local_latest_name=local_latest_name,
    )


def _resolve_stamped_then_compat_then_global_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    run_filename_template: str,
    compatibility_filenames: tuple[str, ...] = (),
    global_latest_name: str,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a stamped artifact, with legacy fallbacks only by explicit opt-in.

    Scientific reports must bind to one run.  A global ``*.latest`` mirror can
    belong to a different run, so it is an operator convenience only and must
    never silently satisfy a run-specific evidence request.
    """
    rid = normalize_artifact_run_id(run_id)
    diag = Path(diagnostics_dir)
    candidates = [diag / run_filename_template.format(run_id=rid)]
    if allow_legacy_compat:
        candidates.extend(diag / name for name in compatibility_filenames)
    if allow_global_latest:
        candidates.append(global_diagnostics_root() / global_latest_name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def resolve_taxonomy_consistency_summary_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve taxonomy consistency summary across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="taxonomy_consistency_summary_{run_id}.json",
        global_latest_name="taxonomy_consistency_summary.latest.json",
    )


def resolve_taxonomy_consistency_mismatches_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve taxonomy mismatch CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="taxonomy_consistency_mismatches_{run_id}.csv",
        global_latest_name="taxonomy_consistency_mismatches.latest.csv",
    )


def resolve_prediction_errors_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve prediction-errors CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="prediction_errors_{run_id}.csv",
        global_latest_name="prediction_errors.latest.csv",
    )


def resolve_headline_vs_ablation_contract_comparison_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    suffix: str = "md",
) -> Path:
    """Resolve headline-vs-ablation contract comparison across run-scoped and global-latest locations."""
    ext = str(suffix).strip().lstrip(".") or "md"
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template=f"headline_vs_ablation_contract_comparison_{{run_id}}.{ext}",
        global_latest_name=f"headline_vs_ablation_contract_comparison.latest.{ext}",
    )


def resolve_taxonomy_type_authority_review_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    suffix: str = "md",
) -> Path:
    """Resolve taxonomy-type authority review across run-scoped and global-latest locations."""
    ext = str(suffix).strip().lstrip(".") or "md"
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template=f"taxonomy_type_authority_review_{{run_id}}.{ext}",
        global_latest_name=f"taxonomy_type_authority_review.latest.{ext}",
    )


def resolve_feature_build_coverage_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve feature-build coverage JSON across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_build_coverage_{run_id}.json",
        global_latest_name="feature_build_coverage.latest.json",
    )


def resolve_cohort_missing_from_feature_matrix_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve missing-cohort CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="cohort_missing_from_feature_matrix_{run_id}.csv",
        global_latest_name="cohort_missing_from_feature_matrix.latest.csv",
    )


def resolve_analysis_snapshot_filter_summary_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve cohort filter-summary CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="analysis_snapshot_filter_summary_{run_id}.csv",
        global_latest_name="analysis_snapshot_filter_summary.latest.csv",
    )


def resolve_cohort_filter_contract_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve cohort filter-contract JSON across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="cohort_filter_contract_{run_id}.json",
        global_latest_name="cohort_filter_contract.latest.json",
    )


def resolve_cohort_gate_counts_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve cohort gate-counts CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="cohort_gate_counts_{run_id}.csv",
        global_latest_name="cohort_gate_counts.latest.csv",
    )


def resolve_feature_matrix_lineage_gate_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve lineage-gate JSON across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_matrix_lineage_gate_{run_id}.json",
        global_latest_name="feature_matrix_lineage_gate.latest.json",
    )


def resolve_feature_modality_coverage_audit_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve modality-audit CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_modality_coverage_audit_{run_id}.csv",
        global_latest_name="feature_modality_coverage_audit.latest.csv",
    )


def resolve_feature_modality_coverage_summary_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve modality-summary JSON across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_modality_coverage_summary_{run_id}.json",
        global_latest_name="feature_modality_coverage_summary.latest.json",
    )


def resolve_feature_contract_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound feature contract; legacy locations require opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_contract_{run_id}.json",
        compatibility_filenames=("feature_contract.json",),
        global_latest_name="feature_contract.latest.json",
        allow_legacy_compat=allow_legacy_compat,
        allow_global_latest=allow_global_latest,
    )


def resolve_ablation_summary_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_partial: bool = False,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound ablation summary; global mirrors require opt-in."""
    rid = normalize_artifact_run_id(run_id)
    diag = Path(diagnostics_dir)
    candidates = [diag / f"ablation_summary_{rid}.csv"]
    if allow_partial:
        candidates.append(diag / f"ablation_summary_partial_{rid}.csv")
    if allow_legacy_compat:
        candidates.append(diag / "ablation_summary.latest.csv")
    if allow_global_latest:
        candidates.append(global_diagnostics_root() / "ablation_summary.latest.csv")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def resolve_model_comparison_summary_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound model comparison; legacy locations require opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="model_comparison_summary_{run_id}.csv",
        compatibility_filenames=("model_comparison_summary.latest.csv",),
        global_latest_name="model_comparison_summary.latest.csv",
        allow_legacy_compat=allow_legacy_compat,
        allow_global_latest=allow_global_latest,
    )


def resolve_modality_method_contract_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound modality contract; legacy locations require opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="modality_method_contract_{run_id}.json",
        compatibility_filenames=("modality_method_contract.json",),
        global_latest_name="modality_method_contract.latest.json",
        allow_legacy_compat=allow_legacy_compat,
        allow_global_latest=allow_global_latest,
    )


def resolve_leakage_assessment_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound leakage assessment; legacy locations require opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="leakage_assessment_{run_id}.txt",
        compatibility_filenames=("leakage_assessment.txt",),
        global_latest_name="leakage_assessment.latest.txt",
        allow_legacy_compat=allow_legacy_compat,
        allow_global_latest=allow_global_latest,
    )


def resolve_label_name_map_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve label-name map JSON across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="label_name_map_{run_id}.json",
        global_latest_name="label_name_map.latest.json",
    )


def resolve_sample_stage_lineage_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve sample-stage lineage CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="sample_stage_lineage_{run_id}.csv",
        global_latest_name="sample_stage_lineage.latest.csv",
    )


def resolve_parser_quality_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve parser-quality CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="parser_quality_{run_id}.csv",
        global_latest_name="parser_quality.latest.csv",
    )


def resolve_parser_quality_final_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve final parser-quality CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="parser_quality_final_{run_id}.csv",
        global_latest_name="parser_quality_final.latest.csv",
    )


def resolve_engine_lifecycle_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve engine-lifecycle CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="engine_lifecycle_{run_id}.csv",
        global_latest_name="engine_lifecycle.latest.csv",
    )


def resolve_analysis_snapshot_label_conflicts_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve snapshot label-conflicts CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="analysis_snapshot_label_conflicts_{run_id}.csv",
        global_latest_name="analysis_snapshot_label_conflicts.latest.csv",
    )


def resolve_vendor_gate_debug_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve vendor-gate debug CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_gate_debug_{run_id}.csv",
        global_latest_name="vendor_gate_debug.latest.csv",
    )


def resolve_vendor_gate_top10_pre_gate_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve pre-gate top-vendor CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_gate_top10_pre_gate_{run_id}.csv",
        global_latest_name="vendor_gate_top10_pre_gate.latest.csv",
    )


def resolve_vendor_parser_coverage_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve parser coverage CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_parser_coverage_{run_id}.csv",
        global_latest_name="vendor_parser_coverage.latest.csv",
    )


def resolve_vendor_parser_coverage_candidates_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve parser onboarding-candidates CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_parser_coverage_candidates_{run_id}.csv",
        global_latest_name="vendor_parser_coverage_candidates.latest.csv",
    )


def resolve_vendor_parser_stress_test_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve parser stress-test CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_parser_stress_test_{run_id}.csv",
        global_latest_name="vendor_parser_stress_test.latest.csv",
    )


def resolve_vendor_parser_strengths_weaknesses_path(diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve parser strengths/weaknesses CSV across run-scoped and global-latest locations."""
    return _resolve_stamped_run_or_global_artifact_path(
        diagnostics_dir,
        run_id,
        run_filename_template="vendor_parser_strengths_weaknesses_{run_id}.csv",
        global_latest_name="vendor_parser_strengths_weaknesses.latest.csv",
    )


def resolve_feature_column_survival_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve run-bound feature survival; the global mirror requires opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_column_survival_{run_id}.csv",
        global_latest_name="feature_column_survival.latest.csv",
        allow_global_latest=allow_global_latest,
    )


def resolve_feature_set_ablation_summary_path(
    diagnostics_dir: Path,
    run_id: str,
    *,
    allow_legacy_compat: bool = False,
    allow_global_latest: bool = False,
) -> Path:
    """Resolve a run-bound feature-set ablation summary; fallbacks require opt-in."""
    return _resolve_stamped_then_compat_then_global_path(
        diagnostics_dir,
        run_id,
        run_filename_template="feature_set_ablation_summary_{run_id}.csv",
        compatibility_filenames=("feature_set_ablation_summary.csv",),
        global_latest_name="feature_set_ablation_summary.latest.csv",
        allow_legacy_compat=allow_legacy_compat,
        allow_global_latest=allow_global_latest,
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
    if diagnostics_mirror_write_policy(out_dir) == RUN_SCOPED_PLUS_GLOBAL_LATEST_MIRROR:
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
    "DEBUG_ONLY",
    "LEGACY_COMPATIBILITY_ONLY",
    "RUN_SCOPED_ONLY",
    "RUN_SCOPED_PLUS_GLOBAL_LATEST_MIRROR",
    "RUN_SCOPED_PLUS_LOCAL_LATEST_DUPLICATE",
    "RUN_SCOPED_PLUS_POINTER",
    "diagnostics_mirror_write_policy",
    "global_diagnostics_root",
    "normalize_artifact_run_id",
    "mirror_csv_text_run_then_global",
    "mirror_json_text_run_then_global",
    "mirror_utf8_text_run_then_global",
    "path_is_under_output_runs",
    "resolve_analysis_snapshot_filter_summary_path",
    "resolve_cohort_missing_from_feature_matrix_path",
    "resolve_cohort_filter_contract_path",
    "resolve_cohort_gate_counts_path",
    "resolve_engine_lifecycle_path",
    "resolve_feature_column_survival_path",
    "resolve_feature_build_coverage_path",
    "resolve_feature_contract_path",
    "resolve_feature_matrix_lineage_gate_path",
    "resolve_feature_modality_coverage_audit_path",
    "resolve_feature_modality_coverage_summary_path",
    "resolve_label_name_map_path",
    "resolve_leakage_assessment_path",
    "resolve_modality_method_contract_path",
    "resolve_parser_quality_path",
    "resolve_parser_quality_final_path",
    "resolve_aligned_features_cache_path",
    "resolve_analysis_snapshot_label_conflicts_path",
    "resolve_analysis_snapshot_csv_path",
    "resolve_dataset_time_contract_path",
    "resolve_run_or_global_artifact_path",
    "resolve_sample_stage_lineage_path",
    "resolve_stable_output_root_for_mirrors",
    "resolve_taxonomy_consistency_summary_path",
    "resolve_vendor_gate_debug_path",
    "resolve_vendor_gate_top10_pre_gate_path",
    "resolve_vendor_parser_coverage_candidates_path",
    "resolve_vendor_parser_coverage_path",
    "resolve_vendor_parser_strengths_weaknesses_path",
    "resolve_vendor_parser_stress_test_path",
    "run_diagnostics_should_omit_latest_duplicate",
    "should_emit_parser_stress_and_strengths_grid",
    "validate_diagnostics_output_dir",
    "write_global_latest_pointer",
    "write_global_latest_text",
]
