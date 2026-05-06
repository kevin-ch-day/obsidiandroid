import traceback
from obsidiandroid.cli.ui import display as du
from config import app_config
from obsidiandroid.common import ml_console
from obsidiandroid.modeling import distribution_reporter
from obsidiandroid.modeling import ml_result_analyzer


def evaluate_model(model, X_test, y_test, label_encoder, model_name: str | None = None):
    """Run evaluation module and return metrics dictionary."""
    from ml_classification.ml_utils import ml_eval_engine

    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    verbose_eval = ml_console.is_debug() or (not quiet and not ml_console.is_minimal())
    if not quiet:
        du.print_section("[EVALUATION] Executing evaluation module")
        du.print_stat("Evaluation Samples", len(X_test))
    try:
        return ml_eval_engine.evaluate_model_performance(
            model=model,
            X_test=X_test,
            y_test=y_test,
            label_encoder=label_encoder,
            model_name=model_name,
            verbose=verbose_eval,
        )
    except Exception as e:
        du.print_error(f"[EVALUATION] Error during evaluation: {e}")
        du.print_debug(traceback.format_exc())
        return {}


def display_post_training_metrics(model_type, result, evaluation, features_df):
    """Display stats, label class info, and prediction preview."""
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if quiet:
        line = (
            f"[{model_type.upper()}] "
            f"Acc={evaluation.get('accuracy', 0.0):.4f} | "
            f"MacroF1={evaluation.get('macro_f1_score', 0.0):.4f} | "
            f"F1={evaluation.get('f1_score', 0.0):.4f} | "
            f"{evaluation.get('train_time', 0.0):.2f}s"
        )
        du.print_info(line)
        return
    du.print_success(
        (
            f"[{model_type.upper()}] Model trained in "
            f"{evaluation['train_time']:.2f} sec."
        )
    )
    du.print_stat("Test Set Size", len(result.get("X_test", [])))
    distribution_reporter.print_split_distributions(
        result.get("y_test", []),
        verbose=app_config.DEBUG_MODE,
    )
    if bool(getattr(app_config, "ML_SHOW_LABEL_ENCODER_INFO", False)):
        ml_result_analyzer.display_label_encoder_info(result.get("label_encoder"))
    if bool(getattr(app_config, "ML_SHOW_PREDICTION_PREVIEWS", False)):
        ml_result_analyzer.show_prediction_sample(
            evaluation.get("y_pred", []),
            label_encoder=None,
        )
    if result.get("cv_score_mean") is not None:
        du.print_stat(
            "CV F1 Mean",
            f"{result['cv_score_mean']:.4f}"
        )
    metrics = {
        k: evaluation[k]
        for k in (
            "accuracy",
            "precision",
            "recall",
            "f1_score",
            "macro_precision",
            "macro_recall",
            "macro_f1_score",
        )
        if k in evaluation
    }
    if metrics:
        metric_labels = {
            "accuracy": "Acc",
            "precision": "Prec",
            "recall": "Rec",
            "f1_score": "F1",
            "macro_precision": "Macro Prec",
            "macro_recall": "Macro Rec",
            "macro_f1_score": "Macro F1",
        }
        display_metrics = {
            metric_labels.get(key, key): value
            for key, value in metrics.items()
        }
        du.print_metric_summary(
            display_metrics,
            title="Evaluation Metrics",
            key_width=20,
            normalize_keys=False,
        )
