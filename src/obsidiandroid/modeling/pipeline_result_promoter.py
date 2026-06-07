# Filename: pipeline_result_promoter.py
# Purpose  : Promote selected fields from the best/default ML model to top-level results for downstream access

from obsidiandroid.cli.ui import display as du
from obsidiandroid.evaluation.ml_terminal_presentation import should_defer_headline_training_terminal

# Default model key used to select which model's results to promote
DEFAULT_MODEL_KEY = "xgboost"

# Keys that will be promoted from the model result to the top-level results dictionary
PROMOTED_KEYS = [
    "predictions",
    "true_labels",
    "metadata",
    "prediction_metadata",
    "confidences",
    "label_encoder",
    "label_classes",
    "evaluation",
    "label_name_map",
]

# Promote selected model outputs to top-level
def promote_model_outputs_to_top_level(results: dict, model_key: str = DEFAULT_MODEL_KEY) -> dict:
    # Validate results container
    if not _is_valid_results_dict(results):
        return results

    # Extract result block for the selected model
    model_result = results.get(model_key)
    if not isinstance(model_result, dict):
        du.print_warning(f"[PROMOTER] Model result block is missing or malformed for key: '{model_key}'")
        return results

    if not should_defer_headline_training_terminal():
        du.print_info(f"[PROMOTER] Promoting fields from model: {model_key}")

    # Extract promotable fields from the model result
    promoted_fields = _extract_promotable_fields(model_result)
    if not promoted_fields:
        du.print_warning(f"[PROMOTER] No valid fields found for promotion from model: '{model_key}'")
        return results

    # Update top-level dictionary with promoted fields
    results.update(promoted_fields)
    if not should_defer_headline_training_terminal():
        du.print_success(f"[PROMOTER] Promoted {len(promoted_fields)} field(s) to top-level from '{model_key}'")
    return results

# Extract and return promotable fields that are non-null
def _extract_promotable_fields(model_result: dict) -> dict:
    promoted = {}
    for key in PROMOTED_KEYS:
        value = model_result.get(key)
        if value is not None:
            promoted[key] = value
            du.print_debug(f"[PROMOTER] + Promoted field: '{key}' ({type(value).__name__})")
        else:
            du.print_debug(f"[PROMOTER] - Missing or null field: '{key}'")
    return promoted

# Check that the results dictionary is valid
def _is_valid_results_dict(results: dict) -> bool:
    if not isinstance(results, dict) or not results:
        du.print_error("[PROMOTER] Invalid results structure: expected non-empty dictionary.")
        return False
    return True

# Print all keys available in a given model's output block
def summarize_model_fields(model_key: str, model_result: dict):
    if not isinstance(model_result, dict):
        du.print_error(f"[SUMMARY] Cannot summarize fields for '{model_key}': not a dictionary.")
        return

    du.print_subheader(f"[SUMMARY] Model Output Fields for: {model_key}")
    for key in sorted(model_result.keys()):
        tag = "*" if key in PROMOTED_KEYS else "-"
        du.print_info(f"{tag} {key}")

# Check if all expected fields are present before promotion
def check_promotion_completeness(model_key: str, model_result: dict):
    missing = [key for key in PROMOTED_KEYS if key not in model_result or model_result[key] is None]
    if missing:
        du.print_warning(f"[CHECK] Model '{model_key}' is missing promotable fields: {missing}")
    else:
        du.print_success(f"[CHECK] All promotable fields are present for model: '{model_key}'")
