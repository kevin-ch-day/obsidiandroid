# Filename: ml_classification/ml_utils/ml_result_analyzer.py
# Purpose : Shared ML result display helpers and evaluation wrapper.

import textwrap

from obsidiandroid.cli.ui import display as du


def display_label_encoder_info(label_encoder, model_name: str = "") -> None:
    """Print decoded label classes from a fitted LabelEncoder."""
    tag = f"[ML_ANALYZER:{model_name.upper()}_ENCODER]" if model_name else "[ML_ANALYZER:ENCODER]"
    du.print_debug(f"{tag} Inspecting label encoder...")

    if label_encoder is None:
        du.print_warning(f"{tag} Label encoder is None - cannot display classes.")
        return

    try:
        du.print_info(f"{tag} Classes: {list(label_encoder.classes_)}")
    except Exception as exc:
        du.print_warning(f"{tag} Failed to retrieve encoder info: {exc}")


def show_prediction_sample(predictions, label_encoder=None, limit: int = 5, model_name: str = "") -> None:
    """Print a compact sample of model predictions for diagnostics."""
    tag = f"[ML_ANALYZER:{model_name.upper()}_PREVIEW]" if model_name else "[ML_ANALYZER:PREVIEW]"
    du.print_debug(f"{tag} Showing prediction preview...")

    if predictions is None or len(predictions) == 0:
        du.print_info(f"{tag} No predictions to show.")
        return

    if isinstance(predictions, dict):
        sample_items = list(predictions.items())[:limit]
        sample_values = [value for _, value in sample_items]
    else:
        sample_items = list(enumerate(predictions))[:limit]
        sample_values = [value for _, value in sample_items]

    decode_needed = label_encoder is not None and all(not isinstance(value, str) for value in sample_values)
    if decode_needed:
        try:
            sample_values = label_encoder.inverse_transform(sample_values)
        except Exception as exc:
            du.print_warning(f"{tag} Decoding failed: {exc}")

    lines = []
    if isinstance(predictions, dict):
        for idx, (key, _) in enumerate(sample_items, start=1):
            lines.append(textwrap.shorten(f"{idx}. {key} -> {sample_values[idx - 1]}", width=70, placeholder="..."))
    else:
        for idx, value in enumerate(sample_values, start=1):
            lines.append(textwrap.shorten(f"{idx}. {value}", width=70, placeholder="..."))

    du.print_info(f"{tag} Sample Predictions:\n" + "\n".join(lines))
