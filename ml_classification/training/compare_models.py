# Filename: compare_models.py
# Purpose  : Train and compare multiple ML models (Random Forest, SVM, XGBoost) for Android malware family classification

import pandas as pd
from utils import display_utils as du
from . import model_runner_helpers as helpers
from . import data_alignment

# List of supported model types to compare
MODEL_LIST = ["random_forest", "svm", "xgboost"]

# Main model comparison function
def compare_multiple_models(features_df: pd.DataFrame, samples_df: pd.DataFrame, save_models: bool = False) -> dict:
    # Print title banner
    du.print_banner("Model Comparison: Random Forest vs. SVM vs. XGBoost")

    results = {}

    # Align input feature and label datasets
    try:
        aligned_features, labels = data_alignment.extract_aligned_labels(features_df, samples_df)
    except data_alignment.DataAlignmentError as exc:
        du.print_error(f"[COMPARE] Failed to align features and labels: {exc}")
        return results

    # Train and evaluate each model
    for model_type in MODEL_LIST:
        du.print_section(f"[MODEL] Training and Evaluating — {model_type.upper()}")
        try:
            result = helpers.run_model_pipeline(
                model_type=model_type,
                features_df=aligned_features,
                labels=labels,
                save_model=save_models
            )

            evaluation = result.get("evaluation", {})

            results[model_type] = {
                "accuracy": evaluation.get("accuracy", 0),
                "precision": evaluation.get("precision", 0),
                "recall": evaluation.get("recall", 0),
                "f1_score": evaluation.get("f1_score", 0),
                "num_classes": evaluation.get("num_classes", 0),
                "samples_tested": evaluation.get("samples_tested", 0),
                "confusion_matrix_path": evaluation.get("confusion_matrix_path", None)
            }

            du.print_info(f"Accuracy: {evaluation.get('accuracy', 0):.4f} | F1 Score: {evaluation.get('f1_score', 0):.4f}")

        except Exception as e:
            du.print_error(f"[COMPARE ERROR] {model_type} failed: {e}")

    _display_comparison_summary(results)
    return results

# Display model metric comparison in table form
def _display_comparison_summary(results: dict):
    if not results:
        du.print_warning("[SUMMARY] No model results to summarize.")
        return

    du.print_banner("Model Comparison Summary")

    summary_data = []
    for model, metrics in results.items():
        summary_data.append({
            "Model": model.upper(),
            "Accuracy": round(metrics["accuracy"], 4),
            "Precision": round(metrics["precision"], 4),
            "Recall": round(metrics["recall"], 4),
            "F1 Score": round(metrics["f1_score"], 4),
            "# Classes": metrics["num_classes"],
            "# Test Samples": metrics["samples_tested"]
        })

    df = pd.DataFrame(summary_data)
    du.display_dataframe(df, title="ML Model Evaluation Comparison")
