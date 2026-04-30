import pandas as pd
import traceback
from utils import display_utils as du
from config import app_config
from utils import ml_console
from . import model_trainer_factory


def announce_training(model_type: str):
    """Print a training header for the model."""
    quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if quiet:
        return
    du.print_section(f"[TRAINING] Initializing model fit for: {model_type.upper()}")


def train_model(
    model_type: str, features_df: pd.DataFrame, labels: pd.Series
) -> dict:
    """Call the model trainer factory with optional grid search."""
    try:
        quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
        if not quiet and not ml_console.is_minimal():
            du.print_stat("Sample Count", len(features_df))
            du.print_stat("Feature Columns", features_df.shape[1])
        grid_flag = False
        if model_type == "random_forest":
            grid_flag = app_config.ENABLE_RF_GRID_SEARCH
        elif model_type == "svm":
            grid_flag = app_config.ENABLE_SVM_GRID_SEARCH
        elif model_type == "logistic_regression":
            grid_flag = app_config.ENABLE_LR_GRID_SEARCH

        if grid_flag:
            du.print_info(
                f"[TRAINING] Grid search enabled for {model_type.upper()}"
            )

        trainer_verbose = bool(getattr(app_config, "ML_TRAINER_VERBOSE", False))
        return model_trainer_factory.train_model_factory(
            features_df=features_df,
            labels=labels,
            model_type=model_type,
            verbose=trainer_verbose,
            enable_grid_search=grid_flag,
        )
    except Exception as e:
        du.print_error(
            f"[TRAINING] {model_type.upper()} failed: {e}"
        )
        du.print_debug(traceback.format_exc())
        return {}
