# Filename: evaluate_model_performance.py
# Purpose  : Backward-compatible wrapper around the canonical evaluator.

from ml_classification.ml_utils import ml_eval_engine


def evaluate_model_performance(
    model,
    X_test,
    y_test,
    label_encoder=None,
    model_name: str | None = None,
    verbose: bool = True,
) -> dict:
    """Evaluate model performance via the canonical ml_eval_engine implementation."""
    return ml_eval_engine.evaluate_model_performance(
        model=model,
        X_test=X_test,
        y_test=y_test,
        label_encoder=label_encoder,
        model_name=model_name,
        verbose=verbose,
    )
