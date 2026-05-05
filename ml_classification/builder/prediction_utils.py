# Filename: prediction_utils.py
# Purpose : Utility functions for handling prediction output and model metadata

from typing import Dict, Tuple, Any
from obsidiandroid.cli.ui import display as du
from config import app_config
from ml_classification.common.malware_family_constants import normalize_family_name


def _normalize_sample_key(value: Any) -> str:
    """Normalize sample-id-like keys so int/float/string ids compare consistently."""
    try:
        f = float(value)
        i = int(f)
        if f == i:
            return str(i)
    except Exception:
        pass
    return str(value)


def _looks_like_sample_metadata_map(metadata: dict, predictions: dict) -> bool:
    """Heuristic: metadata is sample-scoped when it shares keys with predictions."""
    if not isinstance(metadata, dict) or not metadata or not isinstance(predictions, dict):
        return False
    pred_keys = {_normalize_sample_key(k) for k in predictions.keys()}
    meta_keys = {_normalize_sample_key(k) for k in metadata.keys()}
    # Require at least one overlap and avoid false positives on tiny config dicts.
    return len(pred_keys.intersection(meta_keys)) > 0


def extract_prediction_components(
    results: dict,
    verbose: bool = False,
    include_label_name_map: bool = False,
) -> Tuple[dict, dict, dict, dict] | Tuple[dict, dict, dict, dict, dict]:
    """
    Extract and validate the key components from model prediction results.
    Returns a tuple of
    ``(predictions, label_decoder, true_labels, metadata)`` by default.
    When ``include_label_name_map`` is True, returns
    ``(predictions, label_decoder, true_labels, metadata, label_name_map)``.

    ``metadata`` will contain per-sample details from ``prediction_metadata`` if
    present in ``results``. When only ``metadata`` exists, it is returned as-is,
    but nested ``prediction_metadata`` dictionaries are also supported.
    """
    predictions = results.get("predictions", {})
    label_decoder = results.get("label_decoder", {})
    
    if not isinstance(label_decoder, dict) or not label_decoder:
        label_encoder = results.get("label_encoder")
        if label_encoder is not None and hasattr(label_encoder, "classes_"):
            try:
                label_decoder = {
                    idx: label for idx, label in enumerate(label_encoder.classes_)
                }
            except Exception:
                label_decoder = {}

    true_labels = results.get("true_labels", {})
    label_name_map = results.get("label_name_map", {})

    # Robust metadata fallback: support nested "prediction_metadata" inside "metadata"
    metadata = results.get("prediction_metadata")
    if metadata is None:
        base_meta = results.get("metadata", {})
        if isinstance(base_meta, dict) and "prediction_metadata" in base_meta:
            nested = base_meta.get("prediction_metadata")
            metadata = nested if isinstance(nested, dict) else base_meta
        else:
            metadata = base_meta

    # Validation and fallback defaults
    if not isinstance(predictions, dict):
        du.print_warning("'predictions' is missing or not a dict.")
        predictions = {}
    if not isinstance(label_decoder, dict):
        du.print_warning("'label_decoder' is missing or not a dict.")
        label_decoder = {}
    if not isinstance(true_labels, dict):
        du.print_warning("'true_labels' is missing or not a dict.")
        true_labels = {}
    if not isinstance(metadata, dict):
        du.print_warning("'metadata' is missing or not a dict.")
        metadata = {}
    if not isinstance(label_name_map, dict):
        label_name_map = {}

    # Fallback: some model outputs store global run metadata plus a confidences vector.
    # Build sample-level metadata map so Step 7 can emit meaningful confidence values.
    if not _looks_like_sample_metadata_map(metadata, predictions):
        confidences = results.get("confidences")
        if hasattr(confidences, "tolist"):
            confidences = confidences.tolist()
        if isinstance(confidences, (list, tuple)) and len(confidences) == len(predictions):
            metadata = {
                sample_id: {"confidence": float(conf)}
                for sample_id, conf in zip(predictions.keys(), confidences)
            }

    if verbose and getattr(app_config, "DEBUG_MODE", False):
        du.print_debug(f"Predictions loaded: {len(predictions)} samples")
        du.print_debug(f"Label decoder size: {len(label_decoder)}")
        du.print_debug(f"True label map: {len(true_labels)} entries")
        du.print_debug(f"Metadata map: {len(metadata)} entries")

    if include_label_name_map:
        return predictions, label_decoder, true_labels, metadata, label_name_map
    return predictions, label_decoder, true_labels, metadata


def decode_prediction(pred_index: int, decoder: Dict[int, str]) -> str:
    """
    Translate model prediction index into a family name using the decoder.
    """
    return decoder.get(pred_index, "unknown")


def get_sample_confidence(metadata: dict, sample_id: str, include: bool) -> float:
    """
    Extract the confidence score for a given sample ID if available.
    """
    if not include:
        return None
    if isinstance(metadata, dict):
        if "prediction_metadata" in metadata:
            metadata = metadata.get("prediction_metadata") or metadata.get("metadata", {})
        elif "metadata" in metadata:
            metadata = metadata.get("metadata", {})
    if not isinstance(metadata, dict):
        return 0.0
    if "prediction_metadata" in metadata and isinstance(metadata["prediction_metadata"], dict):
        metadata = metadata["prediction_metadata"]
    entry = metadata.get(sample_id)
    if entry is None:
        # Handle mixed key types across pipeline stages (e.g., int vs str sample IDs).
        sample_key = _normalize_sample_key(sample_id)
        for key, value in metadata.items():
            if _normalize_sample_key(key) == sample_key:
                entry = value
                break
    if isinstance(entry, dict):
        return entry.get("confidence", 0.0)
    if isinstance(entry, (float, int)):
        return float(entry)
    return 0.0


def get_category_vector_string(record: Any) -> str:
    """Return the semicolon joined category vector for a record."""
    vector = getattr(record, "category_vector", [])
    normalized = []
    if isinstance(vector, list):
        for token in vector:
            value = str(token)
            if value.startswith("family:"):
                family_value = value.split(":", 1)[1]
                value = f"family:{normalize_family_name(family_value)}"
            normalized.append(value)
        return ";".join(normalized)
    if vector is None:
        return ""
    return str(vector)


def check_label_completeness(record: Any, sample_id: str, verbose: bool = False) -> str:
    """Determine whether a vendor record has all required classification fields."""
    predicted_family = getattr(record, "_predicted_family_fallback", "")
    try:
        if hasattr(record, "validate_record_completeness"):
            result = record.validate_record_completeness()
        elif hasattr(record, "validate_completeness"):
            result = record.validate_completeness()
        else:
            result = "incomplete"
    except Exception as e:
        if verbose:
            du.print_warning(f"[ERROR] completeness check failed for {sample_id}: {e}")
        result = "incomplete"

    if isinstance(result, str) and result.strip().lower() == "complete":
        return "complete"

    # Recovery path: if vendor record is sparse but the effective fields used by
    # final labeling are populated, treat the row as complete.
    family = (predicted_family or getattr(record, "family", "") or "").strip().lower()
    malware_type = (getattr(record, "malware_type", "") or "").strip().lower()
    threat_class = (getattr(record, "threat_class", "") or "").strip().lower()
    if family and family != "unknown" and malware_type and malware_type != "unknown" and threat_class and threat_class != "unknown":
        return "complete"

    return result if isinstance(result, str) else "incomplete"
