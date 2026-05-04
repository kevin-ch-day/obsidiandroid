# Filename: train_model_executor.py
# Purpose : Execute full training and evaluation pipeline for a given ML model

from pathlib import Path
from time import time

import pandas as pd

from config import app_config
from ml_classification.ml_utils import ml_result_validator
from utils import display_utils as du
from utils import ml_console
from obsidiandroid.common import output_paths
from utils.logging import get_logger, log_event

from .model_evaluation import evaluate_model, display_post_training_metrics
from .model_training import announce_training, train_model
from .prediction_builder import export_model, run_predictions_and_compile_result

ML_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.ml.executor",
    "ml",
)


def _model_output_root() -> Path:
    """Return canonical global output root for model exports."""
    return output_paths.output_root()


def train_and_evaluate_model(
    model_type: str,
    features_df: pd.DataFrame,
    labels: pd.Series,
    save_model: bool,
) -> dict:
    """Train, evaluate and optionally export a model."""

    announce_training(model_type)
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if not quiet and not ml_console.is_minimal():
        du.print_stat("Training Samples", len(features_df))
        du.print_stat("Feature Count", features_df.shape[1])
    start_time = time()
    if getattr(app_config, "ENABLE_ML_LOGGING", True):
        log_event(
            ML_LOGGER,
            "train_eval_start",
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
                model=model_type,
                reason="train_result_incomplete",
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
            log_event(ML_LOGGER, "train_eval_failed", model=model_type, reason="missing_evaluation")
        return {}

    evaluation["train_time"] = round(time() - start_time, 2)
    result["evaluation"] = evaluation

    if not ml_result_validator.validate_result_structure(result):
        du.print_warning(
            f"[VALIDATION] {model_type.upper()} "
            "result structure failed post-evaluation."
        )
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(ML_LOGGER, "train_eval_failed", model=model_type, reason="result_validation_failed")
        return {}

    display_post_training_metrics(model_type, result, evaluation, features_df)

    if save_model:
        export_model(result, model_type, features_df, evaluation, _model_output_root())

    final_result = run_predictions_and_compile_result(
        model_type,
        result,
        features_df,
        labels,
    )
    if getattr(app_config, "ENABLE_ML_LOGGING", True):
        log_event(
            ML_LOGGER,
            "train_eval_complete",
            model=model_type,
            duration_sec=round(time() - start_time, 2),
            accuracy=evaluation.get("accuracy"),
            f1_score=evaluation.get("f1_score"),
        )
    return final_result
