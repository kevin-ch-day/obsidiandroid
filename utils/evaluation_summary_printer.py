# Filename: utils/evaluation_summary_printer.py
# Purpose  : Display ML model evaluation results with diagnostics and confusion matrix reporting

import pandas as pd
from utils import display_utils as du
from ml_classification.reporting import ml_report_builder


def evaluate_model_output(results, *, verbose: bool = True):
    du.print_section("Evaluation: Model Performance Summary")

    if not results or not isinstance(results, (dict, list)):
        du.print_error("Invalid input: No results to evaluate.")
        return

    # Detect promoted single-model output (not wrapped by model name)
    if isinstance(results, dict) and "predictions" in results and "true_labels" in results:
        du.print_info("Detected promoted top-level result dictionary. Wrapping as 'ACTIVE'.")
        results = {"ACTIVE": results}

    model_entries = results.items() if isinstance(results, dict) else enumerate(results)
    any_success = False

    for model_key, model_data in model_entries:
        name = str(model_key).upper()
        if verbose:
            du.print_info(f"Evaluating model: {name}")

        if not isinstance(model_data, dict):
            du.print_warning(f"{name}: Skipped — data is not a dictionary.")
            continue

        evaluation = model_data.get("evaluation")
        if not isinstance(evaluation, dict):
            du.print_warning(f"{name}: Missing or malformed 'evaluation' block.")
            continue

        summary_df = evaluation.get("summary_table")
        if not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
            du.print_warning(f"{name}: Missing or empty summary table.")
            continue

        valid_fields = _validate_model_fields(name, model_data, verbose=verbose)
        cm_path = evaluation.get("confusion_matrix_path", "N/A")

        _print_model_summary_block(
            name,
            evaluation,
            summary_df,
            cm_path,
            verbose=verbose,
        )

        if valid_fields:
            du.print_success(f"{name}: Evaluation completed successfully.")
            any_success = True
        else:
            du.print_warning(f"{name}: Evaluation complete with missing metadata fields.")

    if not any_success:
        du.print_error("No valid model evaluations completed.")
    elif verbose:
        du.print_info("All model evaluations processed.")


def _validate_model_fields(model_key: str, model_data: dict, *, verbose: bool = True) -> bool:
    if verbose:
        du.print_debug(f"{model_key}: Validating required metadata fields...")
    required = ["predictions", "true_labels", "metadata", "confidences", "label_encoder", "label_classes"]
    all_valid = True

    for key in required:
        value = model_data.get(key)
        if _is_empty(value):
            if verbose:
                du.print_warning(f"{model_key}: '{key}' is missing or empty.")
            all_valid = False
        else:
            if verbose:
                du.print_debug(
                    f"{model_key}: '{key}' OK — type: {type(value).__name__}, size: {_safe_len(value)}"
                )

    return all_valid


def _is_empty(value) -> bool:
    if value is None:
        return True
    if hasattr(value, "empty") and value.empty:
        return True
    if hasattr(value, "__len__") and len(value) == 0:
        return True
    return False


def _safe_len(obj) -> str:
    try:
        return str(len(obj))
    except Exception:
        return "n/a"


def _print_model_summary_block(
    model_key: str,
    evaluation: dict,
    summary_df: pd.DataFrame,
    cm_path: str,
    *,
    verbose: bool = True,
):
    du.print_subheader(f"Summary for: {model_key}")
    ml_report_builder.print_evaluation_summary(
        df=summary_df,
        acc=evaluation.get("accuracy", 0.0),
        prec=evaluation.get("precision", 0.0),
        recall=evaluation.get("recall", 0.0),
        f1=evaluation.get("f1_score", 0.0),
        cm_path=cm_path,
    )

    if cm_path and isinstance(cm_path, str) and cm_path.strip().upper() != "N/A":
        if verbose:
            du.print_info(f"Confusion matrix saved: {cm_path}")
    else:
        if verbose:
            du.print_warning("Confusion matrix path not provided.")


__all__ = ["evaluate_model_output"]
