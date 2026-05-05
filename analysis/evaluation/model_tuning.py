import os
import sys
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np

# Allow imports when executed directly
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))
from obsidiandroid.modeling import model_trainer_factory


def tune_models(
    n_samples: int = 600,
    n_features: int = 20,
    n_classes: int = 3,
    random_state: int = 42,
    test_size: float = 0.25,
    *,
    rf_grid: bool = True,
    cv_folds: int | None = None,
) -> dict:
    """Train Random Forest and XGBoost models and report F1 metrics."""
    X, y = make_classification(
        n_samples=n_samples,
        n_features=n_features,
        n_informative=n_features - 5,
        n_redundant=0,
        n_classes=n_classes,
        random_state=random_state,
    )
    X_df = pd.DataFrame(X)
    y_ser = pd.Series(y)

    if cv_folds is not None:
        from config import app_config
        setattr(app_config, "CV_FOLDS", cv_folds)

    results = {}
    for model in ("random_forest", "xgboost"):
        results[model] = model_trainer_factory.train_model_factory(
            features_df=X_df,
            labels=y_ser,
            model_type=model,
            enable_grid_search=(rf_grid if model == "random_forest" else False),
            cross_validate=True,
            test_size=test_size,
            random_state=random_state,
        )
    return results


def print_summary(results: dict) -> None:
    """Display CV and hold-out F1 scores for each model."""
    for name, res in results.items():
        print(f"\n=== {name.upper()} ===")
        cv_mean = res.get("cv_score_mean")
        cv_scores = res.get("cv_scores")
        if cv_scores is not None:
            scores = [round(float(s), 4) for s in cv_scores]
            print("CV F1 scores:", scores)
        if cv_mean is not None:
            print("Mean CV F1:", round(float(cv_mean), 4))
        preds = pd.Series(res.get("predictions", []))
        true = pd.Series(res.get("true_labels", []))
        if not preds.empty and not true.empty:
            report = classification_report(true, preds, output_dict=True, zero_division=0)
            f1 = report.get("weighted avg", {}).get("f1-score")
            if f1 is not None:
                print("Hold-out F1:", round(float(f1), 4))
            conf = confusion_matrix(true, preds)
            print("Confusion matrix:\n", conf)


if __name__ == "__main__":
    summary = tune_models()
    print_summary(summary)
