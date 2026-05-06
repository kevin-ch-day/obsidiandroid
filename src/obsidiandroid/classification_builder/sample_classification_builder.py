# Filename: sample_classification_builder.py
# Purpose : Build structured malware classification records using modular utilities

from typing import List, Tuple, Dict, Any
import traceback
import numpy as np
import pandas as pd

from obsidiandroid.cli.ui import display as du
from .prediction_utils import extract_prediction_components
from .classification_row_builder import build_classification_row
from ml_classification.inference.label_consensus_engine import resolve_consensus_label
from config import app_config

def build_sample_classification_records(
    records_by_vendor: Dict[str, Any],
    results: Dict[str, Any],
    label_format: str = "structured",
    include_confidence: bool = True,
    verbose: bool = True,
    use_consensus: bool = False,
    consensus_function=None
) -> pd.DataFrame:
    if use_consensus and consensus_function is None:
        consensus_function = resolve_consensus_label

    # Extract predictions and metadata
    predictions, label_decoder, true_labels, metadata, label_name_map = extract_prediction_components(
        results,
        verbose=verbose,
        include_label_name_map=True,
    )

    if not _validate_prediction_inputs(predictions, label_decoder, records_by_vendor):
        return pd.DataFrame()

    # Build sample-level index once to avoid repeated full vendor scans.
    records_by_sample_id = _build_records_by_sample_id(records_by_vendor)

    # Build structured rows
    output_rows, failed_samples = _build_all_classification_rows(
        predictions=predictions,
        label_decoder=label_decoder,
        true_labels=true_labels,
        metadata=metadata,
        label_name_map=label_name_map,
        records_by_vendor=records_by_vendor,
        records_by_sample_id=records_by_sample_id,
        label_format=label_format,
        include_confidence=include_confidence,
        use_consensus=use_consensus,
        consensus_function=consensus_function
    )

    df = pd.DataFrame(output_rows)
    if not df.empty and "sample_id" in df.columns:
        df.sort_values("sample_id", inplace=True)
        df.reset_index(drop=True, inplace=True)

    _report_classification_summary(df, failed_samples, label_format, include_confidence, verbose)
    return df

# --------------------------------------------------------------------
# Internal Utilities
# --------------------------------------------------------------------

def _validate_prediction_inputs(predictions, label_decoder, records_by_vendor) -> bool:
    if not isinstance(predictions, dict) or not predictions:
        du.print_error("[BUILDER] Missing or malformed 'predictions'")
        return False
    if not isinstance(label_decoder, dict):
        du.print_error("[BUILDER] 'label_decoder' must be a dictionary")
        return False
    if not isinstance(records_by_vendor, dict):
        du.print_error("[BUILDER] 'records_by_vendor' must be a dictionary")
        return False

    if not label_decoder:
        du.print_warning("[BUILDER] Label decoder is empty; fallback labels will be 'unknown'.")

    unmatched = [idx for idx in set(predictions.values()) if idx not in label_decoder]
    if unmatched:
        du.print_warning(f"[BUILDER] Unmapped prediction indices: {unmatched[:5]} (total: {len(unmatched)})")

    return True

def _build_all_classification_rows(
    predictions: Dict[str, Any],
    label_decoder: Dict[int, str],
    true_labels: Dict[str, str],
    metadata: Dict[str, Any],
    label_name_map: Dict[str, str],
    records_by_vendor: Dict[str, List[Any]],
    records_by_sample_id: Dict[str, List[Any]],
    label_format: str,
    include_confidence: bool,
    use_consensus: bool,
    consensus_function
) -> Tuple[List[dict], List[str]]:
    output_rows = []
    failed_samples = []

    for sample_id, pred_index in predictions.items():
        if sample_id is None or pred_index is None:
            du.print_warning("[BUILDER] Missing sample ID or prediction.")
            failed_samples.append(str(sample_id))
            continue

        if not isinstance(pred_index, (int, np.integer)):
            du.print_warning(f"[BUILDER] Invalid prediction type for sample {sample_id}")
            failed_samples.append(str(sample_id))
            continue

        try:
            consensus_data = {}
            if use_consensus and consensus_function:
                try:
                    vendor_records = _gather_records_for_sample(
                        sample_id,
                        records_by_vendor,
                        records_by_sample_id=records_by_sample_id,
                    )
                    consensus_data = consensus_function(vendor_records)
                except Exception as ce:
                    du.print_warning(f"[BUILDER] Consensus function error for {sample_id}: {ce}")

            try:
                row = build_classification_row(
                    sample_id=sample_id,
                    pred_index=int(pred_index),
                    label_decoder=label_decoder,
                    true_labels=true_labels,
                    metadata=metadata,
                    label_name_map=label_name_map,
                    records_by_vendor=records_by_vendor,
                    records_by_sample_id=records_by_sample_id,
                    label_format=label_format,
                    include_confidence=include_confidence,
                    debug=False,
                    consensus_data=consensus_data
                )
            except TypeError as type_error:
                # Backward-compat: allow patched/legacy builders that do not
                # accept newer keyword arguments.
                fallback_tokens = ("label_name_map", "records_by_sample_id")
                if not any(token in str(type_error) for token in fallback_tokens):
                    raise
                row = build_classification_row(
                    sample_id=sample_id,
                    pred_index=int(pred_index),
                    label_decoder=label_decoder,
                    true_labels=true_labels,
                    metadata=metadata,
                    records_by_vendor=records_by_vendor,
                    label_format=label_format,
                    include_confidence=include_confidence,
                    debug=False,
                    consensus_data=consensus_data
                )
            output_rows.append(row)
        except Exception as e:
            du.print_warning(f"[BUILDER] Failed to build row for {sample_id}: {e}")
            du.print_debug(traceback.format_exc())
            failed_samples.append(str(sample_id))

    return output_rows, failed_samples

def _build_records_by_sample_id(records_by_vendor: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    """Index vendor records by normalized sample ID for fast lookup."""
    indexed: Dict[str, List[Any]] = {}

    for rec_list in records_by_vendor.values():
        for rec in rec_list:
            sid = _norm_sample_id(getattr(rec, "sample_id", ""))
            indexed.setdefault(sid, []).append(rec)
    return indexed


def _norm_sample_id(value: Any) -> str:
    """Normalize sample ID tokens for stable dictionary keys."""
    try:
        f = float(value)
        i = int(f)
        if f == i:
            return str(i)
    except (ValueError, TypeError):
        pass
    return str(value)


def _gather_records_for_sample(
    sample_id: str,
    records_by_vendor: Dict[str, List[Any]],
    records_by_sample_id: Dict[str, List[Any]] | None = None,
) -> List[Any]:
    if isinstance(records_by_sample_id, dict):
        return list(records_by_sample_id.get(_norm_sample_id(sample_id), []))

    def _norm(val):
        try:
            f = float(val)
            i = int(f)
            if f == i:
                return str(i)
        except (ValueError, TypeError):
            pass
        return str(val)

    normalized = _norm(sample_id)
    records = []
    for _vendor, rec_list in records_by_vendor.items():
        for rec in rec_list:
            try:
                if _norm(getattr(rec, "sample_id", "")) == normalized:
                    records.append(rec)
            except Exception:
                continue
    return records

def _report_classification_summary(
    df: pd.DataFrame,
    failed_samples: List[str],
    label_format: str,
    include_confidence: bool,
    verbose: bool
):
    if not verbose:
        return

    compact = bool(getattr(app_config, "CLASSIFICATION_TERMINAL_COMPACT", True))
    du.print_section("Structured Classification Summary")
    du.print_success(f"Structured classification generated for {len(df)} samples.")
    du.print_stat("Label Format", label_format)
    du.print_stat("Include Confidence", "Yes" if include_confidence else "No")

    if not df.empty:
        if "predicted_family" in df.columns:
            top_preds = df["predicted_family"].value_counts().head(5)
            if compact:
                top_line = ", ".join(f"{fam}={int(count)}" for fam, count in top_preds.items())
                du.print_info(f"Top Predicted Families: {top_line}")
            else:
                du.print_info("Top Predicted Families:")
                for fam, count in top_preds.items():
                    du.print_info(f" - {fam:<12}: {count}")

        if include_confidence and "confidence" in df.columns:
            du.print_stat("Confidence Range", f"{df['confidence'].min():.2f} -> {df['confidence'].max():.2f}")
            du.print_stat("Average Confidence", f"{df['confidence'].mean():.4f}")

        if "known_family" in df.columns:
            known_count = df["known_family"].sum()
            du.print_stat("Known Families", f"{known_count} / {len(df)}")

        if "label_validity" in df.columns:
            valid_count = (df["label_validity"] == "complete").sum()
            du.print_stat("Valid Labels", f"{valid_count} / {len(df)}")

    if failed_samples:
        du.print_warning(f"{len(failed_samples)} samples failed to classify.")
        du.print_info(f"First 5 failures: {failed_samples[:5]}")

    du.print_success(f"Classification finalized for {len(df)} samples.")
