# Filename: analysis/pipeline/score_av_engines.py
# Purpose  : Score AV engines based on binary detection matrix and engine metadata

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

from analysis.pipeline import engine_normalization
from analysis.risk_band import phase_score_engines
from config import app_config
from database import db_engine
from obsidiandroid.cli.ui import display as du
from obsidiandroid.reporting import export_manager as em
from obsidiandroid.observability.logging import get_logger, log_event

# Output paths
RESULTS_DIR = "output"
EXPORT_INPUT_PATH = os.path.join(RESULTS_DIR, "engine_score_input_matrix.xlsx")
EXPORT_OUTPUT_PATH = os.path.join(RESULTS_DIR, "engine_score_output.xlsx")
EXPORT_MISSING_FIELDS_PATH = os.path.join(RESULTS_DIR, "engine_score_missing_fields.xlsx")
EXPORT_DEBUG_LOG_PATH = os.path.join(RESULTS_DIR, "engine_score_debug_snapshot.xlsx")
SCORE_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.score_av_engines",
    "pipeline",
)


def _lifecycle_path() -> Path:
    """Resolve engine lifecycle export path for current runtime context."""
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_dir:
        return Path(runtime_dir) / "engine_lifecycle.latest.csv"
    return Path("output/diagnostics/engine_lifecycle.latest.csv")


def is_valid_matrix(df: pd.DataFrame) -> bool:
    """Validate detection matrix structure."""
    return not df.empty and "sample_id" in df.columns


def _normalize_engine_key(name: str) -> str:
    """Normalize engine names for robust metadata matching."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _align_engine_metadata_to_matrix(
    matrix_df: pd.DataFrame,
    metadata_map: dict,
    verbose: bool = False,
) -> dict:
    """Keep metadata entries corresponding to engines present in the matrix."""
    if not isinstance(metadata_map, dict) or not metadata_map:
        return {}

    engine_cols = [c for c in matrix_df.columns if c != "sample_id"]
    normalized_lookup = {_normalize_engine_key(k): v for k, v in metadata_map.items()}

    aligned = {}
    unmatched = []
    for engine in engine_cols:
        if engine in metadata_map:
            aligned[engine] = metadata_map[engine]
            continue
        norm = _normalize_engine_key(engine)
        if norm in normalized_lookup:
            aligned[engine] = normalized_lookup[norm]
        else:
            unmatched.append(engine)

    if verbose:
        du.print_debug(
            f"[SCORE] Metadata alignment -> DB: {len(metadata_map)}, "
            f"Matrix: {len(engine_cols)}, Matched: {len(aligned)}"
        )
        if unmatched:
            du.print_warning(
                f"[SCORE] {len(unmatched)} matrix engine(s) missing DB metadata; defaults will be used."
            )

    return aligned


def fetch_engine_metadata(verbose: bool = False, run_id: str = "unknown") -> dict:
    """Fetch trusted/active metadata for each AV engine."""
    try:
        query = """
            SELECT vendor_key AS engine_name, is_trusted_vendor, is_engine_active
            FROM virustotal_vendor_engines
        """
        cols, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
        if not rows or len(cols) != 3:
            raise ValueError("Incomplete metadata query result.")
        metadata_df = pd.DataFrame(rows, columns=cols)
        if verbose:
            du.print_debug(f"[SCORE] Engine metadata retrieved: {len(metadata_df)} rows")
        log_event(
            SCORE_LOGGER,
            "metadata_fetch_complete",
            event_id="SCORE_META_200",
            run_id=run_id,
            rows=int(len(metadata_df)),
        )
        return metadata_df.set_index("engine_name").to_dict(orient="index")
    except Exception as exc:
        if verbose:
            du.print_warning(f"[SCORE] Metadata fetch failed: {exc}")
        log_event(
            SCORE_LOGGER,
            "metadata_fetch_failed",
            event_id="SCORE_META_500",
            run_id=run_id,
            error=str(exc),
        )
        return {}


def export_matrix(df: pd.DataFrame, path: str, label: str, verbose: bool = False):
    """Export DataFrame to Excel file (silent if not verbose)."""
    if not bool(getattr(app_config, "ENABLE_AV_PIPELINE_EXCEL_EXPORT", False)):
        if verbose:
            du.print_info(f"[SCORE] Skipping Excel export for {label} (disabled by config).")
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        exported_path = em.export_dataframe_to_excel(
            df=df,
            filename=os.path.basename(path),
            sheet_name=str(label).replace(" ", "_"),
            preview_rows=0,
        )
        if verbose:
            if exported_path:
                du.print_info(f"[SCORE] Exported {label} to {exported_path}")
            else:
                du.print_warning(f"[SCORE] Export skipped or failed for {label}.")
    except Exception as exc:
        if verbose:
            du.print_warning(f"[SCORE] Failed to export {label}: {exc}")


def validate_scoring_output(df: pd.DataFrame, verbose: bool = False):
    """Verify output format and expected columns."""
    expected_fields = {"Engine Name", "Coverage %", "Detection %", "Detection Tier"}
    missing = expected_fields - set(df.columns)
    if missing and verbose:
        du.print_warning(f"[SCORE] Missing expected fields: {missing}")
        export_matrix(df, EXPORT_MISSING_FIELDS_PATH, "fallback output", verbose=verbose)


def apply_scoring_defaults(config: dict) -> dict:
    """Apply default scoring parameters."""
    config.setdefault("min_engine_detections", int(getattr(app_config, "ENGINE_MIN_SAMPLES_SCANNED", 10)))
    config.setdefault("min_coverage_pct", float(getattr(app_config, "ENGINE_MIN_COVERAGE_PCT", 20.0)))
    config.setdefault("min_positive_flags", int(getattr(app_config, "ENGINE_MIN_POSITIVE_FLAGS", 5)))
    config.setdefault("min_detection_pct", float(getattr(app_config, "ENGINE_MIN_DETECTION_PCT", 1.0)))
    config.setdefault("exclude_zero_detection", bool(getattr(app_config, "ENGINE_EXCLUDE_ZERO_DETECTION", True)))
    config.setdefault("trusted_only", False)
    config.setdefault("active_only", True)
    return config


def _map_exclusion_reason(reason: str) -> str:
    reason = str(reason or "").strip().lower()
    mapping = {
        "": "NONE",
        "included": "NONE",
        "low_coverage": "LOW_COVERAGE",
        "low_coverage_pct": "LOW_COVERAGE",
        "metadata_filter": "MANUAL_EXCLUSION",
        "zero_detections": "BELOW_THRESHOLD",
        "low_positive_flags": "BELOW_THRESHOLD",
        "low_detection_pct": "BELOW_THRESHOLD",
    }
    return mapping.get(reason, "DATA_INCONSISTENCY")


def _build_lifecycle_table(
    matrix_df: pd.DataFrame,
    canonical_keep_map: dict,
    duplicate_losers: set,
    invalid_raw: set,
    score_df: pd.DataFrame,
    profile_context: str,
    run_id: str,
) -> pd.DataFrame:
    """Build per-engine lifecycle table."""
    rows = []
    score_lookup = {}
    if isinstance(score_df, pd.DataFrame) and not score_df.empty:
        for _, row in score_df.iterrows():
            score_lookup[str(row.get("Engine Name"))] = row.to_dict()

    for raw_name, canonical in canonical_keep_map.items():
        selected = raw_name not in duplicate_losers
        score_row = score_lookup.get(canonical, {})
        included = bool(score_row.get("Included", False)) if selected else False
        base_reason = (
            "DUPLICATE_CANONICAL"
            if raw_name in duplicate_losers
            else _map_exclusion_reason(score_row.get("Exclusion Reason", "included"))
        )
        exclusion_stage = (
            "excluded_prescore"
            if raw_name in duplicate_losers
            else ("excluded_postscore" if not included else "none")
        )
        rows.append(
            {
                "engine_name_raw": raw_name,
                "engine_name_canonical": canonical,
                "observed_flag": True,
                "canonicalized_flag": bool(canonical),
                "scored_flag": bool(selected),
                "included_in_model_flag": bool(included),
                "tier_label": score_row.get("Detection Tier", "Excluded") if selected else "Excluded",
                "ml_readiness_score": float(score_row.get("ML Weight Score", 0.0)) if selected else 0.0,
                "exclusion_reason": base_reason if not included else "NONE",
                "exclusion_stage": exclusion_stage,
                "profile_context": profile_context,
                "run_id": run_id,
                "engine_hash": engine_normalization.compute_engine_hash(canonical) if canonical else "",
            }
        )

    for raw_name in sorted(invalid_raw):
        rows.append(
            {
                "engine_name_raw": raw_name,
                "engine_name_canonical": "",
                "observed_flag": True,
                "canonicalized_flag": False,
                "scored_flag": False,
                "included_in_model_flag": False,
                "tier_label": "Excluded",
                "ml_readiness_score": 0.0,
                "exclusion_reason": "DATA_INCONSISTENCY",
                "exclusion_stage": "excluded_precanonical",
                "profile_context": profile_context,
                "run_id": run_id,
                "engine_hash": "",
            }
        )
    return pd.DataFrame(rows)


def _validate_lifecycle_reconciliation(lifecycle_df: pd.DataFrame) -> None:
    """Validate governance lifecycle equations."""
    observed = int(lifecycle_df["observed_flag"].sum())
    canonicalized = int(lifecycle_df["canonicalized_flag"].sum())
    excluded_precanonical = int((lifecycle_df["exclusion_stage"] == "excluded_precanonical").sum())
    scored = int(lifecycle_df["scored_flag"].sum())
    excluded_prescore = int((lifecycle_df["exclusion_stage"] == "excluded_prescore").sum())
    included = int(lifecycle_df["included_in_model_flag"].sum())
    excluded_postscore = int((lifecycle_df["exclusion_stage"] == "excluded_postscore").sum())

    if observed != canonicalized + excluded_precanonical:
        raise ValueError("Lifecycle reconciliation failed: observed != canonicalized + excluded_precanonical")
    if canonicalized != scored + excluded_prescore:
        raise ValueError("Lifecycle reconciliation failed: canonicalized != scored + excluded_prescore")
    if scored != included + excluded_postscore:
        raise ValueError("Lifecycle reconciliation failed: scored != included + excluded_postscore")


def _canonicalize_matrix(
    matrix_df: pd.DataFrame,
    verbose: bool = False,
) -> tuple[pd.DataFrame, dict, set, set, bool]:
    """Canonicalize matrix engine columns and resolve duplicates deterministically."""
    aliases = engine_normalization.load_engine_aliases()
    raw_cols = [c for c in matrix_df.columns if c != "sample_id"]
    scan_counts = matrix_df.attrs.get("engine_scan_counts", {})

    canonical_groups: dict[str, list[str]] = {}
    keep_map: dict[str, str] = {}
    invalid_raw = set()
    duplicate_detected = False

    for raw in raw_cols:
        canonical = engine_normalization.canonicalize_engine_name(raw, aliases=aliases)
        if not canonical:
            invalid_raw.add(raw)
            continue
        keep_map[raw] = canonical
        canonical_groups.setdefault(canonical, []).append(raw)

    duplicate_losers: set[str] = set()
    selected_raw_by_canonical: dict[str, str] = {}
    for canonical, raws in canonical_groups.items():
        if len(raws) == 1:
            selected_raw_by_canonical[canonical] = raws[0]
            continue
        duplicate_detected = True
        scored = []
        for raw in raws:
            coverage = int(scan_counts.get(raw, matrix_df[raw].notna().sum()))
            detections = int(pd.to_numeric(matrix_df[raw], errors="coerce").fillna(0).sum())
            malicious_pct = (detections / coverage) if coverage else 0.0
            scored.append((raw, coverage, malicious_pct))
        scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
        winner = scored[0][0]
        selected_raw_by_canonical[canonical] = winner
        for raw, _, _ in scored[1:]:
            duplicate_losers.add(raw)

    selected_cols = ["sample_id"]
    rename_map = {}
    new_scan_counts = {}
    for canonical, raw in selected_raw_by_canonical.items():
        selected_cols.append(raw)
        rename_map[raw] = canonical
        new_scan_counts[canonical] = int(scan_counts.get(raw, matrix_df[raw].notna().sum()))

    canonical_df = matrix_df[selected_cols].rename(columns=rename_map).copy()
    canonical_df.attrs["engine_scan_counts"] = new_scan_counts
    if verbose:
        du.print_info(
            f"[SCORE] Engine canonicalization: observed={len(raw_cols)}, "
            f"canonical={len(selected_raw_by_canonical)}, duplicates={len(duplicate_losers)}"
        )
    return canonical_df, keep_map, duplicate_losers, invalid_raw, duplicate_detected


def run_av_engine_scoring(
    matrix_df: pd.DataFrame,
    config: dict = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Score antivirus engines based on binary detection matrix and metadata."""
    cfg = config or {}
    run_id = str(cfg.get("run_id", getattr(app_config, "RUNTIME_RUN_ID", "unknown")))

    if verbose:
        du.print_section("AV ENGINE SCORING")
    log_event(
        SCORE_LOGGER,
        "engine_scoring_start",
        event_id="SCORE_001",
        run_id=run_id,
        matrix_rows=int(len(matrix_df)) if isinstance(matrix_df, pd.DataFrame) else 0,
        matrix_cols=int(matrix_df.shape[1]) if isinstance(matrix_df, pd.DataFrame) else 0,
    )

    if not is_valid_matrix(matrix_df):
        if verbose:
            du.print_error("[SCORE] Invalid detection matrix - aborting scoring.")
        log_event(
            SCORE_LOGGER,
            "engine_scoring_failed",
            event_id="SCORE_400",
            run_id=run_id,
            reason="invalid_matrix",
        )
        return pd.DataFrame()

    export_matrix(matrix_df, EXPORT_INPUT_PATH, "input matrix", verbose=verbose)
    config = cfg
    profile_context = str(config.get("profile_context", "unknown"))

    canonical_df, raw_to_canonical, duplicate_losers, invalid_raw, duplicate_detected = _canonicalize_matrix(
        matrix_df,
        verbose=verbose,
    )

    if "engine_metadata" not in config:
        config["engine_metadata"] = fetch_engine_metadata(verbose, run_id=run_id)
    config["engine_metadata"] = _align_engine_metadata_to_matrix(
        canonical_df,
        config.get("engine_metadata", {}),
        verbose=verbose,
    )

    if not isinstance(config.get("engine_metadata"), dict) or not config["engine_metadata"]:
        if verbose:
            du.print_warning("[SCORE] Engine metadata is missing or invalid - skipping scoring.")
        export_matrix(matrix_df, EXPORT_DEBUG_LOG_PATH, "scoring skipped - metadata issue", verbose=verbose)
        log_event(
            SCORE_LOGGER,
            "engine_scoring_failed",
            event_id="SCORE_401",
            run_id=run_id,
            reason="missing_metadata",
        )
        return pd.DataFrame()

    config = apply_scoring_defaults(config)

    try:
        if verbose:
            du.print_debug("[SCORE] Running engine scoring...")
            du.print_debug(f"Matrix shape: {canonical_df.shape}")

        result = phase_score_engines.score_av_engines_from_matrix(
            binary_df=canonical_df,
            config=config,
            verbose=verbose,
        )

        if not isinstance(result, pd.DataFrame) or result.empty:
            if verbose:
                du.print_error("[SCORE] Scoring returned empty result.")
            export_matrix(canonical_df, EXPORT_DEBUG_LOG_PATH, "scoring failed - empty result", verbose=verbose)
            log_event(
                SCORE_LOGGER,
                "engine_scoring_failed",
                event_id="SCORE_402",
                run_id=run_id,
                reason="empty_result",
            )
            return pd.DataFrame()

        lifecycle_df = _build_lifecycle_table(
            matrix_df=matrix_df,
            canonical_keep_map=raw_to_canonical,
            duplicate_losers=duplicate_losers,
            invalid_raw=invalid_raw,
            score_df=result,
            profile_context=profile_context,
            run_id=run_id,
        )
        if not lifecycle_df.empty:
            _validate_lifecycle_reconciliation(lifecycle_df)
            lifecycle_path = _lifecycle_path()
            lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
            lifecycle_df.to_csv(lifecycle_path, index=False)
            result.attrs["engine_lifecycle"] = lifecycle_df
            result.attrs["engine_observed_count"] = int(len([c for c in matrix_df.columns if c != "sample_id"]))
            result.attrs["engine_canonical_count"] = int(lifecycle_df["engine_name_canonical"].nunique())
            result.attrs["engine_included_count"] = int(lifecycle_df["included_in_model_flag"].sum())
            result.attrs["engine_excluded_count"] = int((~lifecycle_df["included_in_model_flag"]).sum())
            if int(result.attrs["engine_included_count"]) == 0:
                raise ValueError("included_engines == 0")

        export_matrix(result, EXPORT_OUTPUT_PATH, "scoring results", verbose=verbose)
        validate_scoring_output(result, verbose=verbose)
        if duplicate_detected:
            raise ValueError("Duplicate canonical engine slugs detected.")

        log_event(
            SCORE_LOGGER,
            "engine_scoring_complete",
            event_id="SCORE_200",
            run_id=run_id,
            output_rows=int(result.shape[0]),
            output_cols=int(result.shape[1]),
            included_count=int(result.attrs.get("engine_included_count", 0)),
            excluded_count=int(result.attrs.get("engine_excluded_count", 0)),
        )
        return result

    except Exception as exc:
        if verbose:
            du.print_error(f"[SCORE] Engine scoring failed: {exc}")
        export_matrix(canonical_df, EXPORT_DEBUG_LOG_PATH, "scoring crash matrix", verbose=verbose)
        log_event(
            SCORE_LOGGER,
            "engine_scoring_failed",
            event_id="SCORE_500",
            run_id=run_id,
            error=str(exc),
        )
        return pd.DataFrame()
