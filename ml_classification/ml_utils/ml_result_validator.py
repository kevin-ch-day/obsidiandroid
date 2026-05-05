# Filename: ml_result_validator.py
# Purpose : Validate and debug model output structure for ObsidianDroid ML pipeline

from obsidiandroid.cli.ui import display as du

# Required top-level keys in a valid result dictionary
REQUIRED_KEYS = [
    "model",
    "X_test",
    "y_test",
    "evaluation",
    "label_classes",
    "label_encoder",
    "predictions",
    "true_labels",
    "metadata",
    "confidences"
]

def validate_result_structure(result: dict, model_name: str = "unknown") -> bool:
    """
    Validates that the model result dictionary has all required keys and valid nested fields.

    Args:
        result (dict): Model output dictionary from training pipeline.
        model_name (str): Optional name of the model for logging.

    Returns:
        bool: True if valid, False if any critical keys or structures are missing.
    """
    trace_tag = f"[{model_name.upper()}_RESULT]"
    du.print_debug(f"{trace_tag} Validating result structure...")

    if not isinstance(result, dict):
        du.print_error(f"{trace_tag} Result is not a dictionary. Found type: {type(result).__name__}")
        return False

    if not result:
        du.print_error(f"{trace_tag} Result dictionary is empty.")
        return False

    missing = [key for key in REQUIRED_KEYS if key not in result]
    if missing:
        du.print_warning(f"{trace_tag} Missing required keys: {missing}")
        return False

    # Check evaluation block
    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict) or not evaluation:
        du.print_warning(f"{trace_tag} 'evaluation' block is missing or invalid.")
        return False

    # Check predictions
    preds = result.get("predictions")
    if preds is None:
        du.print_warning(f"{trace_tag} 'predictions' is missing.")
        return False
    elif isinstance(preds, dict):
        du.print_debug(f"{trace_tag} Predictions count: {len(preds)}")
    elif hasattr(preds, "__len__"):
        du.print_warning(
            f"{trace_tag} 'predictions' is list-like; expected dict keyed by sample ID."
        )
        du.print_debug(f"{trace_tag} Predictions length: {len(preds)}")
    else:
        du.print_warning(
            f"{trace_tag} 'predictions' has unsupported type: {type(preds).__name__}."
        )
        return False

    # Check confidences
    confidences = result.get("confidences")
    if confidences is None:
        du.print_warning(f"{trace_tag} 'confidences' is missing.")
        return False
    elif hasattr(confidences, '__len__'):
        du.print_debug(f"{trace_tag} Confidences length: {len(confidences)}")
    else:
        du.print_warning(f"{trace_tag} 'confidences' is not list-like.")
        return False

    du.print_debug(f"{trace_tag} Structure validation passed.")
    return True


def display_label_encoder_info(label_encoder, model_name: str = "") -> None:
    """
    Displays the label encoder's class list for diagnostics.

    Args:
        label_encoder: Fitted label encoder instance.
        model_name (str): Optional model tag for logging context.
    """
    tag = f"[{model_name.upper()}_ENCODER]" if model_name else "[ENCODER]"
    if label_encoder is None:
        du.print_warning(f"{tag} Label encoder is None.")
        return

    try:
        classes = list(label_encoder.classes_)
        du.print_info(f"{tag} Classes: {classes}")
    except Exception as e:
        du.print_warning(f"{tag} Failed to extract encoder classes: {e}")


def show_prediction_sample(predictions, label_encoder=None, limit=5, model_name: str = "") -> None:
    """Print a small preview of predicted class values."""
    import textwrap
    tag = f"[{model_name.upper()}_PREVIEW]" if model_name else "[PREVIEW]"
    if predictions is None or len(predictions) == 0:
        du.print_info(f"{tag} No predictions to display.")
        return

    if isinstance(predictions, dict):
        sample_items = list(predictions.items())[:limit]
        sample_values = [p[1] for p in sample_items]
    else:
        sample_items = list(enumerate(predictions))[:limit]
        sample_values = [p[1] for p in sample_items]

    decode_needed = label_encoder is not None and all(not isinstance(p, str) for p in sample_values)

    if decode_needed:
        try:
            sample_values = label_encoder.inverse_transform(sample_values)
        except Exception as e:
            du.print_warning(f"{tag} Error decoding prediction sample: {e}")

    bullet_lines = []
    if isinstance(predictions, dict):
        for idx, (key, _) in enumerate(sample_items, start=1):
            pred = sample_values[idx - 1]
            line = f"{idx:>2}. {key} -> {pred}"
            bullet_lines.append(textwrap.shorten(str(line), width=70, placeholder="..."))
    else:
        for idx, pred in enumerate(sample_values, start=1):
            line = f"{idx:>2}. {pred}"
            bullet_lines.append(textwrap.shorten(str(line), width=70, placeholder="..."))

    preview = "\n".join(bullet_lines)
    du.print_info(f"{tag} Sample Predictions:\n{preview}")
