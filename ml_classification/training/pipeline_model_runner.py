# Filename: pipeline_model_runner.py
# Purpose  : Legacy compatibility wrapper for the canonical classifier pipeline.

from __future__ import annotations

import pandas as pd

from .pipeline_core import (
    ALL_SUPPORTED_MODELS,
    DEFAULT_MODEL_KEY,
    promote_default_model,
    run_classifier_pipeline as _run_classifier_pipeline,
)

SUPPORTED_MODELS = list(ALL_SUPPORTED_MODELS)


def run_classifier_pipeline(
    features_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    save_model: bool = True,
) -> dict:
    """Delegate legacy entrypoint calls to the canonical pipeline implementation."""
    return _run_classifier_pipeline(
        features_df=features_df,
        samples_df=samples_df,
        save_model=save_model,
        models=SUPPORTED_MODELS,
    )


def _promote_default_model_outputs(results: dict) -> None:
    """Preserve legacy helper name while using the canonical promotion logic."""
    promote_default_model(results, model_key=DEFAULT_MODEL_KEY)
