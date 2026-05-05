# Filename: ml_classification/labeling/label_builder_wrapper.py
# Purpose  : Construct structured classification label records using vendor metadata and ML model output

import pandas as pd
from typing import Optional, Dict, Any
from obsidiandroid.cli.ui import display as du
from ml_classification.builder import sample_classification_builder
from ml_classification.common.malware_family_constants import normalize_family_name
from config import app_config

def should_use_db_family(sample_metadata: dict, predicted_family: str) -> bool:
    """
    Determine if the database family name should override the model prediction.
    """
    family_name = normalize_family_name((sample_metadata or {}).get("family_name", ""))
    predicted = normalize_family_name(predicted_family)
    return bool(family_name and family_name != "unknown" and family_name != predicted)

def apply_db_family_override(model_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Override model predictions using trusted family names from the database, if appropriate.
    """
    predictions = model_output.get("predictions", {})
    metadata = model_output.get("metadata", {})
    updated_predictions = {}
    override_count = 0

    for sample_id, predicted_family in predictions.items():
        sample_meta = metadata.get(sample_id, {}) or {}
        if should_use_db_family(sample_meta, predicted_family):
            db_family = sample_meta.get("family_name", "").strip()
            updated_predictions[sample_id] = db_family
            sample_meta["override_tag"] = "db_family_override"
            override_count += 1
        else:
            updated_predictions[sample_id] = predicted_family

        metadata[sample_id] = sample_meta

    if override_count > 0:
        du.print_info(f"[BUILDER_WRAPPER] Applied {override_count} DB family overrides.")

    model_output["predictions"] = updated_predictions
    model_output["metadata"] = metadata
    return model_output

def _log_model_output_debug(model_output: Dict[str, Any]):
    """
    Print debug statistics about model output structure.
    """
    if not getattr(app_config, "DEBUG_MODE", False):
        return

    predictions = model_output.get("predictions")
    true_labels = model_output.get("true_labels")
    metadata = model_output.get("metadata")
    label_encoder = model_output.get("label_encoder")

    if not isinstance(predictions, dict):
        du.print_warning("'predictions' is missing or not a dict.")
    else:
        du.print_debug(f"Predictions loaded: {len(predictions)} samples")

    if not isinstance(true_labels, dict):
        du.print_warning("'true_labels' is missing or not a dict.")
    else:
        du.print_debug(f"True labels loaded: {len(true_labels)} entries")

    if not isinstance(metadata, dict):
        du.print_warning("'metadata' is missing or not a dict.")
    else:
        du.print_debug(f"Metadata map: {len(metadata)} entries")

    if label_encoder is None:
        du.print_warning("'label_encoder' is missing.")
    else:
        try:
            classes = getattr(label_encoder, "classes_", [])
            du.print_debug(f"Label decoder size: {len(classes)}")
        except Exception:
            du.print_warning("Could not access 'label_encoder.classes_'")

def build_structured_label_output(
    vendor_records: Dict[str, Any],
    model_output: Dict[str, Any],
    use_consensus: bool = False,
    consensus_function=None,
    allow_db_family_override: bool = True
) -> Optional[pd.DataFrame]:
    """
    Build structured classification labels using vendor metadata and model results.
    """
    try:
        du.print_info("[BUILDER_WRAPPER] Building structured output from model predictions...")
        _log_model_output_debug(model_output)

        # Optional DB family override
        if allow_db_family_override:
            model_output = apply_db_family_override(model_output)

        # Generate structured classification records
        df_structured = sample_classification_builder.build_sample_classification_records(
            records_by_vendor=vendor_records,
            results=model_output,
            use_consensus=use_consensus,
            consensus_function=consensus_function,
            label_format="structured",
            include_confidence=True,
            verbose=True
        )

        if df_structured is None or df_structured.empty:
            du.print_warning("[BUILDER_WRAPPER] Structured output DataFrame is empty.")
            du.print_info("[BUILDER_WRAPPER] Check prediction content or enrichment logic.")
            return None

        du.print_success(f"[BUILDER_WRAPPER] Structured labels created for {len(df_structured)} samples.")
        return df_structured

    except Exception as e:
        du.print_error(f"[BUILDER_WRAPPER] Failed to build structured labels: {type(e).__name__} — {e}")
        return None
