# Filename: model_runner_helpers.py
# Purpose  : Wrapper to delegate model training and handle prediction/reporting in the classification pipeline

import pandas as pd
from pathlib import Path
import traceback

from config import app_config
from utils import display_utils as du
from utils.logging import get_logger, log_event
from . import train_model_executor  # Executes full model lifecycle

# Directory where output models and diagnostics are saved
OUTPUT_DIR = Path("output")
ML_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.ml.helpers",
    "ml",
)

# Main entry point to run training, evaluation, export, and reporting
def run_model_pipeline(model_type: str, features_df: pd.DataFrame, labels: pd.Series, save_model: bool) -> dict:
    # Print pipeline banner for the selected model
    du.print_header(f"[PIPELINE] Starting ML pipeline for model: {model_type.upper()}")

    # Basic input validation
    if features_df is None or features_df.empty:
        du.print_error(f"[PIPELINE] Feature DataFrame is empty for model: {model_type}")
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(ML_LOGGER, "model_input_invalid", model=model_type, reason="empty_features")
        return {}

    if labels is None or labels.empty:
        du.print_error(f"[PIPELINE] Label DataFrame is empty for model: {model_type}")
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            log_event(ML_LOGGER, "model_input_invalid", model=model_type, reason="empty_labels")
        return {}

    try:
        # Delegate full pipeline logic to the train_model_executor module
        du.print_debug(f"[{model_type.upper()}] Calling train_and_evaluate_model()...")
        result = train_model_executor.train_and_evaluate_model(
            model_type=model_type,
            features_df=features_df,
            labels=labels,
            save_model=save_model
        )

        # Check result validity
        if not result or not isinstance(result, dict):
            du.print_error(f"[PIPELINE] Model pipeline failed for '{model_type}'. No valid result returned.")
            if getattr(app_config, "ENABLE_ML_LOGGING", True):
                log_event(ML_LOGGER, "model_result_invalid", model=model_type)
            return {}

        # Confirm success and log result keys
        du.print_success(f"[PIPELINE] Completed pipeline for '{model_type}'.")
        du.print_debug(f"[{model_type.upper()}] Returned result keys: {list(result.keys())}")
        return result

    except Exception as e:
        # Catch and log fatal errors
        du.print_error(f"[PIPELINE] Fatal error in model pipeline for '{model_type}': {e}")
        du.print_debug(traceback.format_exc())
        if getattr(app_config, "ENABLE_ML_LOGGING", True):
            ML_LOGGER.error("model_pipeline_fatal model=%r error=%r", model_type, e, exc_info=True)
        return {}
