# Filename: obsidiandroid/pipeline/vendor_metadata_pipeline.py
#
# Canonical vendor-metadata pipeline helpers.

"""Vendor metadata extraction pipeline orchestration."""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_float_config_value
from obsidiandroid.evaluation import vendor_feature_extractor
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.observability.logging import get_logger, log_event
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.common import output_hygiene as oh


PIPELINE_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.vendor_metadata",
    "pipeline",
)


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory under configured output root."""
    return resolve_diagnostics_dir()


def extract_vendor_metadata(
    pipeline_results: Dict[str, Any],
    samples_df: pd.DataFrame,
    verbose: bool = False,
) -> Tuple:
    """Extract vendor metadata and quality scorecard objects."""
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    if not ml_console.is_compact():
        du.print_subheader("Extract Vendor Metadata")
    log_event(
        PIPELINE_LOGGER,
        "vendor_metadata_start",
        event_id="VENDOR_META_001",
        run_id=run_id,
        samples=int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0,
    )

    if not _validate_inputs(pipeline_results, samples_df):
        du.print_error("[ABORT] Input validation failed. Exiting vendor metadata phase.")
        log_event(
            PIPELINE_LOGGER,
            "vendor_metadata_failed",
            event_id="VENDOR_META_400",
            level="ERROR",
            run_id=run_id,
            reason="input_validation",
        )
        return None, None, None, None

    if ml_console.is_compact():
        du.print_info("[VENDOR] Extracting vendor metadata and parser diagnostics...")
    else:
        du.print_info("[PHASE] Starting metadata extraction...")
    results = _perform_vendor_extraction(pipeline_results, samples_df, verbose)
    if results is None:
        du.print_error("[ABORT] Vendor extraction returned None. Cannot continue.")
        log_event(
            PIPELINE_LOGGER,
            "vendor_metadata_failed",
            event_id="VENDOR_META_500",
            level="ERROR",
            run_id=run_id,
            reason="extractor_none",
        )
        return None, None, None, None

    vendor_eval_df, records_by_vendor, parsed_data, scorecard_df = results

    if not ml_console.is_compact():
        du.print_info("[PHASE] Running diagnostics...")
    _print_diagnostics(vendor_eval_df, records_by_vendor, parsed_data, scorecard_df, verbose)
    _check_dataframe_structure(vendor_eval_df, label="vendor_eval_df", required_columns={"Vendor", "Enrichment Score"})
    _check_dataframe_structure(scorecard_df, label="scorecard_df", required_columns={"Final ML Score"})
    _inject_pipeline_state(pipeline_results, vendor_eval_df)

    if isinstance(scorecard_df, pd.DataFrame) and not scorecard_df.empty:
        if not ml_console.is_compact():
            du.print_success(f"[OK] Scorecard shape: {scorecard_df.shape}")
        _export_parser_quality(scorecard_df)
    else:
        du.print_error("[FAIL] Scorecard is missing or invalid; ML scoring will fail.")
        log_event(
            PIPELINE_LOGGER,
            "vendor_metadata_failed",
            event_id="VENDOR_META_422",
            level="ERROR",
            run_id=run_id,
            reason="invalid_scorecard",
        )
        return None, None, None, None

    if ml_console.is_compact():
        du.print_success(
            f"[DONE] Vendor metadata ready: vendors={len(records_by_vendor):,}, "
            f"scorecard_rows={int(scorecard_df.shape[0]) if isinstance(scorecard_df, pd.DataFrame) else 0:,}"
        )
    else:
        du.print_success("[DONE] Vendor metadata extraction complete.")
    log_event(
        PIPELINE_LOGGER,
        "vendor_metadata_complete",
        event_id="VENDOR_META_200",
        run_id=run_id,
        vendor_eval_rows=int(vendor_eval_df.shape[0]) if isinstance(vendor_eval_df, pd.DataFrame) else 0,
        scorecard_rows=int(scorecard_df.shape[0]) if isinstance(scorecard_df, pd.DataFrame) else 0,
    )
    return vendor_eval_df, records_by_vendor, parsed_data, scorecard_df


def _validate_inputs(pipeline_results: Dict[str, Any], samples_df: pd.DataFrame) -> bool:
    valid = True
    if not isinstance(pipeline_results, dict):
        du.print_error("[ERROR] pipeline_results is not a dictionary.")
        du.print_debug(f"Type: {type(pipeline_results)}")
        valid = False
    if not isinstance(samples_df, pd.DataFrame):
        du.print_error("[ERROR] samples_df is not a DataFrame.")
        du.print_debug(f"Type: {type(samples_df)}")
        valid = False
    if isinstance(samples_df, pd.DataFrame) and samples_df.empty:
        du.print_warning("[WARN] samples_df is empty.")
    return valid


def _perform_vendor_extraction(
    pipeline_results: Dict[str, Any],
    samples_df: pd.DataFrame,
    verbose: bool,
) -> Optional[Tuple[pd.DataFrame, dict, dict, pd.DataFrame]]:
    try:
        result = vendor_feature_extractor.extract_vendor_feature_metadata(
            av_pipeline_results=pipeline_results,
            samples_df=samples_df,
            verbose=verbose,
        )
    except Exception as exc:
        du.print_error(f"[EXCEPTION] Metadata extraction crashed: {exc}")
        return None

    if not isinstance(result, tuple) or len(result) != 4:
        du.print_error("[ERROR] Expected 4-tuple from extractor.")
        du.print_debug(f"Type: {type(result)} | Value: {result}")
        return None

    vendor_eval_df, records_by_vendor, parsed_data, scorecard_df = result
    types_ok = all(
        [
            isinstance(vendor_eval_df, pd.DataFrame),
            isinstance(records_by_vendor, dict),
            isinstance(parsed_data, dict),
            isinstance(scorecard_df, pd.DataFrame),
        ]
    )
    if not types_ok:
        du.print_error("[ERROR] One or more return values have incorrect types.")
        du.print_debug(
            "[DEBUG] Types -> "
            f"eval_df: {type(vendor_eval_df)}, records: {type(records_by_vendor)}, "
            f"parsed: {type(parsed_data)}, scorecard: {type(scorecard_df)}"
        )
        return None

    if vendor_eval_df.empty:
        du.print_warning("[WARN] vendor_eval_df is empty.")
    if scorecard_df.empty:
        du.print_warning("[WARN] scorecard_df is empty.")
    return vendor_eval_df, records_by_vendor, parsed_data, scorecard_df


def _print_diagnostics(
    vendor_eval_df: Any,
    records_by_vendor: Any,
    parsed_data: Any,
    scorecard_df: Any,
    verbose: bool,
) -> None:
    if not verbose:
        return
    du.print_debug("[DEBUG] Metadata output types:")
    du.print_debug(f"  vendor_eval_df     : {type(vendor_eval_df)}")
    du.print_debug(f"  records_by_vendor  : {type(records_by_vendor)}")
    du.print_debug(f"  parsed_data        : {type(parsed_data)}")
    du.print_debug(f"  scorecard_df       : {type(scorecard_df)}")
    if any(x is None for x in [vendor_eval_df, parsed_data, scorecard_df]):
        du.print_warning("[WARN] One or more components are None.")


def _check_dataframe_structure(df: Any, label: str, required_columns: set) -> None:
    if not isinstance(df, pd.DataFrame):
        du.print_error(f"[STRUCTURE] {label} is not a DataFrame.")
        return
    if df.empty:
        du.print_warning(f"[STRUCTURE] {label} is empty.")
        return
    missing = required_columns - set(df.columns)
    if missing:
        du.print_warning(f"[STRUCTURE] {label} missing columns: {sorted(missing)}")


def _inject_pipeline_state(pipeline_results: Dict[str, Any], vendor_eval_df: pd.DataFrame) -> None:
    if isinstance(vendor_eval_df, pd.DataFrame) and not vendor_eval_df.empty:
        pipeline_results["vendor_eval_df"] = vendor_eval_df
        if not ml_console.is_compact():
            du.print_info("[INFO] vendor_eval_df injected into pipeline_results.")
    else:
        du.print_error("[FAIL] vendor_eval_df missing or empty. Pipeline state not updated.")


def _export_parser_quality(scorecard_df: pd.DataFrame) -> None:
    """Export parser quality diagnostics artifact."""
    export_df = _build_parser_quality_export_df(scorecard_df)
    if export_df.empty:
        return

    diagnostics_dir = _diagnostics_dir()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rid = oh.normalize_artifact_run_id(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    path = diagnostics_dir / f"parser_quality_{rid}.csv"
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=path.name,
        csv_text=export_df.to_csv(index=False),
        global_latest_name="parser_quality.latest.csv",
    )
    du.print_debug(f"[DIAG] Parser quality report exported: {path.name}")
    if oh.should_emit_parser_stress_and_strengths_grid():
        _export_parser_stress_test(export_df)
        _export_parser_strengths_weaknesses(export_df)
    log_event(
        PIPELINE_LOGGER,
        "parser_quality_exported",
        event_id="VENDOR_META_230",
        run_id=str(getattr(app_config, "RUNTIME_RUN_ID", "unknown")),
        path=str(path),
        rows=int(export_df.shape[0]),
    )


def _build_parser_quality_export_df(scorecard_df: pd.DataFrame) -> pd.DataFrame:
    """Build parser-quality export frame with stable governance columns."""
    if not isinstance(scorecard_df, pd.DataFrame) or scorecard_df.empty:
        return pd.DataFrame()

    legacy_cols = [
        "Vendor",
        "Samples Evaluated",
        "Unknown Parsed (%)",
        "Generic Family Ratio",
        "Family Match Accuracy (%)",
        "mapped_ratio",
        "unknown_ratio",
        "generic_ratio",
        "entropy",
        "parser_gate_status",
        "downweight_factor",
        "effective_weight",
        "included_in_model",
    ]
    legacy_present = [col for col in legacy_cols if col in scorecard_df.columns]
    if not legacy_present:
        return pd.DataFrame()

    export_df = scorecard_df[legacy_present].copy()
    has_explicit_gate_status = "parser_gate_status" in scorecard_df.columns
    has_explicit_include_flag = "included_in_model" in scorecard_df.columns
    has_explicit_governance = has_explicit_gate_status or has_explicit_include_flag

    # Governance-stable contract columns (snake_case).
    if "Vendor" in export_df.columns:
        export_df["vendor_id"] = export_df["Vendor"].astype(str).str.strip().str.lower()
    else:
        export_df["vendor_id"] = "unknown"

    if "Samples Evaluated" in export_df.columns:
        export_df["total_rows"] = pd.to_numeric(
            export_df["Samples Evaluated"], errors="coerce"
        ).fillna(0).astype(int)
    else:
        export_df["total_rows"] = 0

    if "mapped_ratio" not in export_df.columns and "Family Match Accuracy (%)" in export_df.columns:
        export_df["mapped_ratio"] = (
            pd.to_numeric(export_df["Family Match Accuracy (%)"], errors="coerce").fillna(0.0)
            / 100.0
        )
    if "unknown_ratio" not in export_df.columns and "Unknown Parsed (%)" in export_df.columns:
        export_df["unknown_ratio"] = (
            pd.to_numeric(export_df["Unknown Parsed (%)"], errors="coerce").fillna(0.0)
            / 100.0
        )
    if "generic_ratio" not in export_df.columns and "Generic Family Ratio" in export_df.columns:
        export_df["generic_ratio"] = pd.to_numeric(
            export_df["Generic Family Ratio"], errors="coerce"
        ).fillna(0.0)

    # Build/repair gating columns so diagnostics remain meaningful even when
    # upstream summary frames do not yet include governance fields.
    if "parser_gate_status" not in export_df.columns:
        unknown_cut = safe_float_config_value(
            getattr(app_config, "PARSER_UNKNOWN_EXCLUDE_THRESHOLD", 0.70),
            default=0.70,
        )
        mapped_cut = safe_float_config_value(
            getattr(app_config, "PARSER_MAPPED_MIN_THRESHOLD", 0.30),
            default=0.30,
        )
        generic_cut = safe_float_config_value(
            getattr(app_config, "PARSER_GENERIC_DOWNWEIGHT_THRESHOLD", 0.60),
            default=0.60,
        )

        gate_status = pd.Series("included", index=export_df.index, dtype="object")
        gate_status.loc[pd.to_numeric(export_df.get("unknown_ratio"), errors="coerce").fillna(0.0) > unknown_cut] = (
            "excluded_high_unknown"
        )
        gate_status.loc[pd.to_numeric(export_df.get("mapped_ratio"), errors="coerce").fillna(0.0) < mapped_cut] = (
            "excluded_low_mapped"
        )
        mask_generic = (
            pd.to_numeric(export_df.get("generic_ratio"), errors="coerce").fillna(0.0) > generic_cut
        ) & (gate_status == "included")
        gate_status.loc[mask_generic] = "downweight_generic"
        export_df["parser_gate_status"] = gate_status

    if "downweight_factor" not in export_df.columns:
        default_downweight = safe_float_config_value(
            getattr(app_config, "PARSER_GENERIC_DOWNWEIGHT_FACTOR", 0.50),
            default=0.50,
        )
        export_df["downweight_factor"] = 1.0
        export_df.loc[
            export_df["parser_gate_status"].astype(str).str.contains("downweight", case=False, na=False),
            "downweight_factor",
        ] = default_downweight

    # Normalize trusted/active vendor governance flags across varying source names.
    trusted_sources = ("Trusted", "trusted", "trusted_vendor_flag", "is_trusted_vendor")
    active_sources = ("Active", "active", "active_vendor_flag", "is_engine_active")
    trusted_col = next((col for col in trusted_sources if col in scorecard_df.columns), None)
    active_col = next((col for col in active_sources if col in scorecard_df.columns), None)
    if trusted_col:
        export_df["trusted_vendor_flag"] = (
            pd.to_numeric(scorecard_df[trusted_col], errors="coerce").fillna(0).astype(int)
        )
    else:
        export_df["trusted_vendor_flag"] = 0
    if active_col:
        export_df["active_vendor_flag"] = (
            pd.to_numeric(scorecard_df[active_col], errors="coerce").fillna(0).astype(int)
        )
    else:
        export_df["active_vendor_flag"] = 0

    if "included_in_model" not in export_df.columns:
        gate_status_series = export_df["parser_gate_status"].astype(str).str.lower()
        export_df["included_in_model"] = gate_status_series.str.startswith("included").astype(int)

    include_series = pd.Series(0, index=export_df.index, dtype="int64")
    if "included_in_model" in export_df.columns:
        include_series = pd.to_numeric(
            export_df["included_in_model"], errors="coerce"
        ).fillna(0).astype(int)
    gate_status = pd.Series("included", index=export_df.index, dtype="object")
    if "parser_gate_status" in export_df.columns:
        gate_status = export_df["parser_gate_status"].fillna("included")
    gate_status = gate_status.astype(str).str.strip().str.lower()

    # Contract: inclusion_status must be one of include/downweight/exclude/unknown.
    export_df["inclusion_status"] = "include"
    export_df.loc[gate_status.str.contains("downweight"), "inclusion_status"] = "downweight"
    export_df.loc[
        gate_status.str.contains("excluded")
        | gate_status.str.contains("reject")
        | (include_series == 0),
        "inclusion_status",
    ] = "exclude"
    if not has_explicit_governance:
        all_included = (export_df["inclusion_status"] == "include").all()
        if all_included:
            export_df["inclusion_status"] = "unknown"
    # Clarify that parser quality reflects vendor-metadata stage diagnostics
    # before engine-weight relaxation/fallback rules are applied.
    export_df["diagnostic_stage"] = "vendor_metadata_pre_weights"

    preferred_cols = [
        "vendor_id",
        "total_rows",
        "mapped_ratio",
        "unknown_ratio",
        "generic_ratio",
        "entropy",
        "inclusion_status",
        "parser_gate_status",
        "downweight_factor",
        "effective_weight",
        "included_in_model",
        "trusted_vendor_flag",
        "active_vendor_flag",
        "diagnostic_stage",
        # legacy compatibility columns:
        "Vendor",
        "Samples Evaluated",
        "Unknown Parsed (%)",
        "Generic Family Ratio",
        "Family Match Accuracy (%)",
    ]
    present_cols = [col for col in preferred_cols if col in export_df.columns]
    return export_df[present_cols]


def _export_parser_stress_test(export_df: pd.DataFrame) -> None:
    """Export threshold-sweep stress test over parser gating controls."""
    if export_df.empty:
        return
    diagnostics_dir = _diagnostics_dir()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rid = oh.normalize_artifact_run_id(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    out_path = diagnostics_dir / f"vendor_parser_stress_test_{rid}.csv"

    base = export_df.copy()
    for col in ("mapped_ratio", "unknown_ratio", "generic_ratio"):
        base[col] = pd.to_numeric(base.get(col, 0.0), errors="coerce").fillna(0.0)
    base["trusted_vendor_flag"] = pd.to_numeric(
        base.get("trusted_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    base["active_vendor_flag"] = pd.to_numeric(
        base.get("active_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)

    unknown_grid = (0.60, 0.70, 0.80)
    mapped_grid = (0.20, 0.30, 0.40)
    generic_grid = (0.50, 0.60, 0.70)
    downweight_factor = safe_float_config_value(
        getattr(app_config, "PARSER_GENERIC_DOWNWEIGHT_FACTOR", 0.50),
        default=0.50,
    )
    rows: list[dict[str, object]] = []

    for unknown_cut in unknown_grid:
        for mapped_cut in mapped_grid:
            for generic_cut in generic_grid:
                status = pd.Series("included", index=base.index, dtype="object")
                status.loc[base["unknown_ratio"] > unknown_cut] = "excluded_high_unknown"
                status.loc[base["mapped_ratio"] < mapped_cut] = "excluded_low_mapped"
                generic_mask = (base["generic_ratio"] > generic_cut) & (status == "included")
                status.loc[generic_mask] = "downweight_generic"

                include_count = int((status == "included").sum())
                exclude_count = int(status.str.startswith("excluded").sum())
                downweight_count = int((status == "downweight_generic").sum())
                trusted_included = int(((status == "included") & (base["trusted_vendor_flag"] == 1)).sum())
                active_included = int(((status == "included") & (base["active_vendor_flag"] == 1)).sum())
                effective_share = (
                    include_count + downweight_count * downweight_factor
                ) / max(float(len(base)), 1.0)
                rows.append(
                    {
                        "unknown_cut": unknown_cut,
                        "mapped_cut": mapped_cut,
                        "generic_cut": generic_cut,
                        "include_count": include_count,
                        "exclude_count": exclude_count,
                        "downweight_count": downweight_count,
                        "trusted_included_count": trusted_included,
                        "active_included_count": active_included,
                        "effective_inclusion_share": round(float(effective_share), 4),
                    }
                )

    export_df_rows = pd.DataFrame(rows).sort_values(
        by=["effective_inclusion_share", "include_count", "trusted_included_count"],
        ascending=[False, False, False],
    )
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=out_path.name,
        csv_text=export_df_rows.to_csv(index=False),
        global_latest_name="vendor_parser_stress_test.latest.csv",
    )
    du.print_debug(f"[DIAG] Parser stress test exported: {out_path.name}")


def _export_parser_strengths_weaknesses(export_df: pd.DataFrame) -> None:
    """Export per-vendor parser strength/weakness diagnostics."""
    if export_df.empty:
        return
    diagnostics_dir = _diagnostics_dir()
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rid = oh.normalize_artifact_run_id(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    out_path = diagnostics_dir / f"vendor_parser_strengths_weaknesses_{rid}.csv"

    frame = export_df.copy()
    vendor_source = "vendor_id" if "vendor_id" in frame.columns else "vendor"
    frame["vendor"] = frame.get(vendor_source, pd.Series("unknown", index=frame.index)).astype(str)
    frame["mapped_ratio"] = pd.to_numeric(frame.get("mapped_ratio", 0.0), errors="coerce").fillna(0.0)
    frame["unknown_ratio"] = pd.to_numeric(frame.get("unknown_ratio", 0.0), errors="coerce").fillna(0.0)
    frame["generic_ratio"] = pd.to_numeric(frame.get("generic_ratio", 0.0), errors="coerce").fillna(0.0)
    frame["trusted_vendor_flag"] = pd.to_numeric(
        frame.get("trusted_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    frame["active_vendor_flag"] = pd.to_numeric(
        frame.get("active_vendor_flag", 0), errors="coerce"
    ).fillna(0).astype(int)

    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        strengths: list[str] = []
        weaknesses: list[str] = []
        if float(row["mapped_ratio"]) >= 0.60:
            strengths.append("high_mapping")
        if float(row["unknown_ratio"]) <= 0.25:
            strengths.append("low_unknown")
        if float(row["generic_ratio"]) <= 0.25:
            strengths.append("low_generic")
        if int(row["trusted_vendor_flag"]) == 1:
            strengths.append("trusted_vendor")
        if int(row["active_vendor_flag"]) == 1:
            strengths.append("active_vendor")

        if float(row["mapped_ratio"]) < 0.30:
            weaknesses.append("low_mapping")
        if float(row["unknown_ratio"]) > 0.50:
            weaknesses.append("high_unknown")
        if float(row["generic_ratio"]) > 0.60:
            weaknesses.append("high_generic")
        status = str(row.get("inclusion_status", "unknown")).strip().lower()
        if status == "exclude":
            weaknesses.append("excluded_by_gate")

        rows.append(
            {
                "vendor": str(row["vendor"]),
                "inclusion_status": status,
                "mapped_ratio": round(float(row["mapped_ratio"]), 4),
                "unknown_ratio": round(float(row["unknown_ratio"]), 4),
                "generic_ratio": round(float(row["generic_ratio"]), 4),
                "trusted_vendor_flag": int(row["trusted_vendor_flag"]),
                "active_vendor_flag": int(row["active_vendor_flag"]),
                "strength_tags": ";".join(strengths),
                "weakness_tags": ";".join(weaknesses),
            }
        )

    export_df_rows = pd.DataFrame(rows).sort_values(
        by=["inclusion_status", "vendor"], ascending=[True, True]
    )
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=out_path.name,
        csv_text=export_df_rows.to_csv(index=False),
        global_latest_name="vendor_parser_strengths_weaknesses.latest.csv",
    )
    du.print_debug(f"[DIAG] Parser strengths/weaknesses exported: {out_path.name}")
