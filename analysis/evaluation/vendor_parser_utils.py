# Filename: analysis/evaluation/vendor_parser_utils.py
# Purpose  : Production-grade utilities to support the vendor classification parser pipeline

from typing import Dict
from pathlib import Path
import pandas as pd

from obsidiandroid.cli.ui import display as du
from config import app_config
from obsidiandroid.vendors.parsing import generic_label_parser
from obsidiandroid.vendors.parsing import vendor_parser_map
from obsidiandroid.evaluation import vendor_parser_matching as parser_match
from analysis.evaluation import av_results_fetcher as results_fetcher

REQUIRED_COLUMNS = {"sample_id"}
MERGE_KEY = "sample_id"
MAX_ERRORS_TO_SHOW = 5
LABEL_CANDIDATE_COLUMNS = [
    "family_canonical",
    "family_name",
    "family_label_raw",
    "family_id",
]
NON_VENDOR_COLUMNS = {
    "sample_id",
    "family_name",
    "family_canonical",
    "family_label_raw",
    "family_id",
}
PARSER_COVERAGE_EXPORT = Path("output/diagnostics/vendor_parser_coverage.latest.csv")
PARSER_CANDIDATES_EXPORT = Path("output/diagnostics/vendor_parser_coverage_candidates.latest.csv")


def validate_input_columns(samples_df: pd.DataFrame) -> bool:
    """
    Ensures required columns are present in the input DataFrame.
    """
    missing = REQUIRED_COLUMNS - set(samples_df.columns)
    if missing:
        du.print_error(f"Missing required columns in sample input: {missing}")
        return False
    if not any(c in samples_df.columns for c in LABEL_CANDIDATE_COLUMNS):
        du.print_error(
            "Missing family label columns in sample input. "
            f"Tried: {LABEL_CANDIDATE_COLUMNS}"
        )
        return False
    return True


def check_sample_integrity(samples_df: pd.DataFrame, verbose: bool = False):
    """
    Reports missing or duplicated sample IDs and family names.
    """
    null_ids = samples_df["sample_id"].isnull().sum()
    label_col = _resolve_label_column(samples_df)
    null_families = samples_df[label_col].isnull().sum() if label_col else 0
    duplicates = samples_df["sample_id"].duplicated().sum()

    du.print_info(f"Sample DataFrame -> {len(samples_df)} rows | {samples_df.shape[1]} columns")

    if null_ids:
        du.print_warning(f"Missing 'sample_id' values: {null_ids}")
    if label_col and null_families:
        du.print_warning(f"Missing '{label_col}' values: {null_families}")
    if duplicates:
        du.print_warning(f"Duplicate 'sample_id' entries: {duplicates}")


def fetch_av_results(samples_df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """
    Fetch AV result columns aligned to input sample set.
    """
    return results_fetcher.fetch_av_results(samples_df, verbose)


def check_av_sample_alignment(samples_df: pd.DataFrame, av_df: pd.DataFrame):
    """
    Confirms that all sample IDs are represented in the AV detection result set.
    """
    source_ids = set(samples_df["sample_id"])
    result_ids = set(av_df["sample_id"])
    missing_ids = source_ids - result_ids

    if missing_ids:
        du.print_warning(f"{len(missing_ids)} sample_id values are missing in AV result set.")


def match_parsers(av_summary_df: pd.DataFrame, verbose: bool = False) -> dict:
    """
    Matches vendor parsers to available AV result columns.
    """
    vendor_map = vendor_parser_map.get_vendor_parser_map()
    av_columns = list(av_summary_df.columns)
    matched = parser_match.resolve_valid_vendor_columns(vendor_map, av_columns, verbose=verbose)

    dynamic_generic = _build_dynamic_generic_parser_map(
        av_df=av_summary_df,
        existing_map=matched,
        verbose=verbose,
    )
    if dynamic_generic:
        matched.update(dynamic_generic)

    if not matched:
        du.print_error("No valid vendor parsers found for AV columns.")
    _export_parser_coverage_snapshot(av_summary_df, matched, verbose=verbose)

    return matched


def _export_parser_coverage_snapshot(
    av_df: pd.DataFrame,
    matched_map: dict,
    verbose: bool = False,
) -> None:
    """Export parser coverage snapshot for diagnostics."""
    try:
        if not isinstance(av_df, pd.DataFrame) or av_df.empty:
            return
        total_rows = max(len(av_df), 1)
        mapped_columns = {
            meta.get("column_name", key)
            for key, meta in (matched_map or {}).items()
            if isinstance(meta, dict)
        }

        rows = []
        for col in av_df.columns:
            if col in NON_VENDOR_COLUMNS:
                continue
            series = av_df[col]
            non_empty = _build_non_empty_value_mask(series)
            rows.append(
                {
                    "vendor_column": col,
                    "coverage_pct": round((float(non_empty.sum()) / float(total_rows)) * 100.0, 2),
                    "parser_mapped": int(col in mapped_columns),
                    "is_dynamic_generic": int(
                        any(
                            isinstance(meta, dict)
                            and meta.get("column_name") == col
                            and bool(meta.get("dynamic_generic"))
                            for meta in (matched_map or {}).values()
                        )
                    ),
                }
            )

        if not rows:
            return
        out_df = pd.DataFrame(rows).sort_values(
            by=["parser_mapped", "coverage_pct", "vendor_column"],
            ascending=[False, False, True],
        )
        PARSER_COVERAGE_EXPORT.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(PARSER_COVERAGE_EXPORT, index=False)
        _export_unmapped_coverage_candidates(out_df, verbose=verbose)
        if verbose:
            mapped = int(out_df["parser_mapped"].sum())
            du.print_info(
                f"[PARSER] Coverage snapshot exported: {PARSER_COVERAGE_EXPORT} "
                f"({mapped}/{len(out_df)} mapped)"
            )
    except Exception as exc:
        if verbose:
            du.print_warning(f"[PARSER] Failed exporting parser coverage snapshot: {exc}")


def _export_unmapped_coverage_candidates(
    coverage_df: pd.DataFrame,
    verbose: bool = False,
) -> None:
    """Export unmapped high-coverage vendors prioritized for parser onboarding."""
    if coverage_df.empty:
        return

    min_cov = float(getattr(app_config, "PARSER_ONBOARDING_CANDIDATE_MIN_COVERAGE_PCT", 80.0))
    max_rows = int(getattr(app_config, "PARSER_ONBOARDING_CANDIDATE_MAX_ROWS", 16))

    candidates = coverage_df[
        (coverage_df["parser_mapped"] == 0) & (coverage_df["coverage_pct"] >= min_cov)
    ].copy()

    if candidates.empty:
        empty_cols = [
            "priority_rank",
            "vendor_column",
            "coverage_pct",
            "parser_mapped",
            "is_dynamic_generic",
            "onboarding_priority",
        ]
        pd.DataFrame(columns=empty_cols).to_csv(PARSER_CANDIDATES_EXPORT, index=False)
        return

    candidates = candidates.sort_values(
        by=["coverage_pct", "vendor_column"],
        ascending=[False, True],
    ).head(max_rows)
    candidates.insert(0, "priority_rank", range(1, len(candidates) + 1))
    candidates["onboarding_priority"] = "high_coverage_unmapped"
    candidates.to_csv(PARSER_CANDIDATES_EXPORT, index=False)

    if verbose:
        du.print_info(
            "[PARSER] Coverage onboarding candidates exported: "
            f"{PARSER_CANDIDATES_EXPORT} ({len(candidates)} rows, min_cov={min_cov:.1f}%)"
        )


def _build_dynamic_generic_parser_map(
    av_df: pd.DataFrame,
    existing_map: dict,
    verbose: bool = False,
) -> dict:
    """Build dynamic generic-parser entries for uncovered vendor columns.

    Args:
        av_df: Raw AV verdict matrix.
        existing_map: Already resolved parser mapping.
        verbose: Enable diagnostic logging.

    Returns:
        Dictionary keyed by synthetic parser name with parser metadata.
    """
    if not bool(getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True)):
        return {}

    if not isinstance(av_df, pd.DataFrame) or av_df.empty:
        return {}

    min_cov = float(getattr(app_config, "DYNAMIC_GENERIC_MIN_COVERAGE_PCT", 5.0))
    max_cols = int(getattr(app_config, "DYNAMIC_GENERIC_MAX_COLUMNS", 40))

    mapped_columns = {
        meta.get("column_name", key)
        for key, meta in (existing_map or {}).items()
        if isinstance(meta, dict)
    }
    all_cols = [c for c in av_df.columns if c not in NON_VENDOR_COLUMNS]
    uncovered = [c for c in all_cols if c not in mapped_columns]
    if not uncovered:
        return {}

    total_rows = max(len(av_df), 1)
    candidates = []
    for col in uncovered:
        series = av_df[col]
        non_empty = _build_non_empty_value_mask(series)
        coverage_pct = (float(non_empty.sum()) / float(total_rows)) * 100.0
        if coverage_pct >= min_cov:
            candidates.append((col, coverage_pct))

    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = candidates[:max_cols]

    dynamic_map = {}
    for col, coverage_pct in selected:
        dynamic_map[f"{col}__generic"] = {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification,
            "column_name": col,
            "display_name": col,
            "dynamic_generic": True,
            "observed_coverage_pct": round(coverage_pct, 2),
        }

    if verbose:
        du.print_info(
            f"[PARSER] Dynamic generic onboarding: {len(dynamic_map)} column(s) "
            f"(min_cov={min_cov:.1f}%, max={max_cols})."
        )
        if dynamic_map:
            preview = list(dynamic_map.values())[:10]
            names = [str(v.get("column_name")) for v in preview]
            du.print_debug(f"[PARSER] Dynamic columns preview: {names}")

    return dynamic_map


def _build_non_empty_value_mask(series: pd.Series) -> pd.Series:
    """Return a boolean mask for values that count as usable vendor labels.

    Args:
        series: Raw vendor label series.

    Returns:
        Boolean mask where ``True`` indicates a non-empty, non-null label value.
    """
    cleaned = series.fillna("").astype(str).str.strip()
    return (cleaned != "") & (~cleaned.str.lower().isin({"none", "null", "n/a"}))


def merge_sample_metadata(av_summary_df: pd.DataFrame, samples_df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """
    Merges AV results with ground truth family labels from sample metadata.
    """
    if MERGE_KEY not in samples_df.columns:
        du.print_error(f"Required merge column missing: {MERGE_KEY}")
        return None
    label_col = _resolve_label_column(samples_df)
    if not label_col:
        du.print_error(
            "No supported family label column found for merge. "
            f"Tried: {LABEL_CANDIDATE_COLUMNS}"
        )
        return None

    try:
        merged = av_summary_df.merge(
            samples_df[[MERGE_KEY, label_col]],
            on=MERGE_KEY,
            how="left",
            validate="many_to_one"
        )
        merged["family_name"] = merged[label_col].astype(str).str.strip().str.lower()
        return merged
    except Exception as e:
        du.print_error(f"Failed to merge sample metadata: {e}")
        return None


def _resolve_label_column(samples_df: pd.DataFrame) -> str | None:
    for col in LABEL_CANDIDATE_COLUMNS:
        if col in samples_df.columns:
            return col
    return None


def print_parser_diagnostics(summary_rows, flat_df, records_by_vendor, errors, verbose: bool):
    """
    Displays high-level statistics about parser output and basic error feedback.
    """
    du.print_section("Vendor Parsing Outcome")
    du.print_info(f"Vendors Parsed       : {len(records_by_vendor)}")
    du.print_info(f"Flat Parsed Records  : {len(flat_df)}")
    du.print_info(f"Summary Rows Created : {len(summary_rows)}")

    if errors:
        du.print_warning(f"{len(errors)} parsing errors encountered.")
        for err in errors[:MAX_ERRORS_TO_SHOW]:
            if isinstance(err, dict):
                du.print_info(
                    f"  - Vendor: {err.get('vendor')} | Sample: {err.get('sample_id')} | Error: {err.get('error')}"
                )
            else:
                du.print_info(f"  - Error: {err}")
