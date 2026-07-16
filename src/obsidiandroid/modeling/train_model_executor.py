# Filename: train_model_executor.py
# Purpose : Execute full training and evaluation pipeline for a given ML model

from pathlib import Path
from time import time

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common import output_paths
from obsidiandroid.modeling import ml_result_validator
from obsidiandroid.observability.logging import get_logger, log_event

from .model_evaluation import evaluate_model, display_post_training_metrics
from .feature_selection_contract import apply_feature_selection_contract
from .model_training import announce_training, train_model
from .prediction_builder import export_model, run_predictions_and_compile_result

ML_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.ml.executor",
    "ml",
)


def _model_output_root() -> Path:
    """Return canonical global output root for model exports."""
    return output_paths.output_root()


def _prediction_feature_matrix(features_df: pd.DataFrame, result: dict) -> pd.DataFrame:
    """Apply the train-fitted column contract before full-cohort prediction.

    ``train_model_factory`` fits feature selection on the training partition
    and returns the frozen contract. The full-cohort prediction/export path
    must apply that ordered column list; otherwise scikit-learn rejects the
    prediction schema and feature-importance names can be wrong. Older trainer
    results without a contract retain their original behavior.
    """
    contract = result.get("feature_selection_contract")
    if not isinstance(contract, dict):
        return features_df
    return apply_feature_selection_contract(features_df, contract)


def train_and_evaluate_model(
    model_type: str,
    features_df: pd.DataFrame,
    labels: pd.Series,
    save_model: bool,
) -> dict:
    """Train, evaluate and optionally export a model."""

    announce_training(model_type)
    from obsidiandroid.evaluation.ml_terminal_presentation import should_defer_headline_training_terminal

    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    defer_terminal = should_defer_headline_training_terminal()
    if not quiet and not ml_console.is_minimal() and not defer_terminal:
        du.print_stat("Training Samples", len(features_df))
        du.print_stat("Feature Count", features_df.shape[1])
    start_time = time()
    if getattr(app_config, "ENABLE_ML_LOGGING", True):
        log_event(
            ML_LOGGER,
            "train_eval_start",
            event_id="ML_EXEC_001",
            model=model_type,
            samples=int(len(features_df)),
            features=int(features_df.shape[1]),
        )

    # Train the model
    result = train_model(model_type, features_df, labels)
    required_result_keys = ("model", "X_test", "y_test", "label_encoder")
    if (
        not isinstance(result, dict)
        or any(result.get(key) is None for key in required_result_keys)
    ):
        du.print_error(
            f"[{model_type.upper()}] Training failed - result payload is incomplete."
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(
                ML_LOGGER,
                "train_eval_failed",
                event_id="ML_EXEC_500",
                level="ERROR",
                model=model_type,
                reason="train_result_incomplete",
            )
        return {}

    try:
        prediction_features = _prediction_feature_matrix(features_df, result)
    except (TypeError, ValueError) as exc:
        du.print_error(
            f"[{model_type.upper()}] Frozen feature contract could not be applied for full prediction: {exc}"
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(
                ML_LOGGER,
                "train_eval_failed",
                event_id="ML_EXEC_409",
                level="ERROR",
                model=model_type,
                reason="prediction_feature_contract_unavailable",
            )
        return {}

    # Evaluate the model on test data
    evaluation = evaluate_model(
        model=result.get("model"),
        X_test=result.get("X_test"),
        y_test=result.get("y_test"),
        label_encoder=result.get("label_encoder"),
        model_name=model_type,
    )
    if not isinstance(evaluation, dict) or not evaluation:
        du.print_warning(
            f"[{model_type.upper()}] No evaluation metrics returned."
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(
                ML_LOGGER,
                "train_eval_failed",
                event_id="ML_EXEC_404",
                level="WARNING",
                model=model_type,
                reason="missing_evaluation",
            )
        return {}

    evaluation["train_time"] = round(time() - start_time, 2)
    result["evaluation"] = evaluation

    if not ml_result_validator.validate_result_structure(result):
        du.print_warning(
            f"[VALIDATION] {model_type.upper()} "
            "result structure failed post-evaluation."
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(
                ML_LOGGER,
                "train_eval_failed",
                event_id="ML_EXEC_422",
                level="WARNING",
                model=model_type,
                reason="result_validation_failed",
            )
        return {}

    display_post_training_metrics(model_type, result, evaluation, prediction_features)

    final_result = run_predictions_and_compile_result(
        model_type,
        result,
        prediction_features,
        labels,
    )
    if not isinstance(final_result, dict) or not final_result:
        du.print_error(
            f"[{model_type.upper()}] Full prediction/report failed; model export is withheld."
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(
                ML_LOGGER,
                "train_eval_failed",
                event_id="ML_EXEC_424",
                level="ERROR",
                model=model_type,
                reason="full_prediction_or_result_compilation_failed",
            )
        return {}

    if save_model:
        export_model(result, model_type, prediction_features, evaluation, _model_output_root())
        export_paths = dict(result.get("export_paths", {}) or {})
        if export_paths:
            final_result["export_paths"] = export_paths

    if getattr(app_config, "ENABLE_ML_LOGGING", True):
        log_event(
            ML_LOGGER,
            "train_eval_complete",
            event_id="ML_EXEC_200",
            model=model_type,
            duration_sec=round(time() - start_time, 2),
            accuracy=evaluation.get("accuracy"),
            f1_score=evaluation.get("f1_score"),
        )
    return final_result
