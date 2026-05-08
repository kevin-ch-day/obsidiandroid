# Filename: vendor_classification_parser.py
# Purpose : Production-grade parser entry for vendor AV classification and scoring.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, Tuple

import pandas as pd

from obsidiandroid.vendors.execution import av_parser_executor as parser_exec

from obsidiandroid.evaluation import vendor_parser_utils as vp_utils
from obsidiandroid.evaluation import vendor_score_calculator as score_calc
from obsidiandroid.vendors import ParsedLabelMetadata, VendorClassificationRecord


@dataclass(frozen=True)
class VendorClassificationParseResult:
    """Stable result bundle for vendor classification parsing.

    Backward-compat: this is iterable so callers can still unpack as:
    ``parsed_data, summary_df, vendor_records, flat_df = parse_vendor_classifications(...)``.
    """

    parsed_data: Dict[str, Any]
    summary_df: pd.DataFrame
    vendor_records: Dict[str, Any]
    flat_df: pd.DataFrame

    def __iter__(self) -> Iterator[Any]:
        yield self.parsed_data
        yield self.summary_df
        yield self.vendor_records
        yield self.flat_df


# === Validate Parser Output Format ===
def _validate_parsed_output(output, vendor: str) -> bool:
    if isinstance(output, (ParsedLabelMetadata, VendorClassificationRecord)):
        return True
    if isinstance(output, dict):
        try:
            ParsedLabelMetadata.from_dict(output)
            return True
        except Exception:
            return False
    return False


# === Main Entry Point ===
def parse_vendor_classifications(
    samples_df: pd.DataFrame,
    engine_metadata: dict = None,
    verbose: bool = False,
) -> VendorClassificationParseResult:
    if not vp_utils.validate_input_columns(samples_df):
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    if verbose:
        vp_utils.check_sample_integrity(samples_df, verbose)

    av_summary_df = vp_utils.fetch_av_results(samples_df, verbose)
    if av_summary_df.empty:
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    if verbose:
        vp_utils.check_av_sample_alignment(samples_df, av_summary_df)

    matched_vendors = vp_utils.match_parsers(av_summary_df, verbose)
    if not matched_vendors:
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    merged_df = vp_utils.merge_sample_metadata(av_summary_df, samples_df, verbose)
    if merged_df is None:
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    try:
        parsed_data, summary_rows, vendor_records, flat_df, errors = parser_exec.parse_all_vendors(
            merged_df=merged_df,
            vendor_map=matched_vendors,
            metadata_lookup=engine_metadata,
            verbose=verbose,
        )
    except Exception:
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    # Basic structure check (only first record per vendor)
    for vendor, records in vendor_records.items():
        if records and not _validate_parsed_output(records[0], vendor):
            continue  # Silently ignore malformed vendor output

    if verbose:
        vp_utils.print_parser_diagnostics(summary_rows, flat_df, vendor_records, errors, verbose)

    if not summary_rows:
        return VendorClassificationParseResult({}, pd.DataFrame(), {}, pd.DataFrame())

    try:
        summary_df = score_calc.compute_vendor_scores(summary_rows)
    except Exception:
        return VendorClassificationParseResult(parsed_data, pd.DataFrame(), vendor_records, flat_df)

    return VendorClassificationParseResult(parsed_data, summary_df, vendor_records, flat_df)
