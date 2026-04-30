import os
import sys
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.metrics import confusion_matrix, classification_report
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from ml_classification.training import model_trainer_factory


def run_diagnostics(
    n_samples: int = 400,
    random_state: int = 42,
    f1_threshold: float = 0.6,
    *,
    enable_grid_search: bool = True,
    cross_validate: bool = True,
    test_size: float = 0.25,
    compare_baseline: bool = False,
):
    """Train the Random Forest model on a synthetic dataset and report metrics.

    The routine prints cross-validation scores, hold-out accuracy, a confusion
    matrix, misclassified sample indices, classes with weak F1 scores, and the
    top feature importances. Setting ``compare_baseline`` runs a second training
    round without grid search and reports the difference in mean F1 score.
    """
    X, y = make_classification(
        n_samples=n_samples,
        n_features=20,
        n_informative=15,
        n_redundant=0,
        n_classes=3,
        random_state=random_state,
    )
    X_df = pd.DataFrame(X)
    y_ser = pd.Series(y)

    baseline_result = None
    if compare_baseline:
        baseline_result = model_trainer_factory.train_model_factory(
            features_df=X_df,
            labels=y_ser,
            model_type="random_forest",
            enable_grid_search=False,
            cross_validate=cross_validate,
            test_size=test_size,
            random_state=random_state,
        )

    result = model_trainer_factory.train_model_factory(
        features_df=X_df,
        labels=y_ser,
        model_type="random_forest",
        enable_grid_search=enable_grid_search,
        cross_validate=cross_validate,
        test_size=test_size,
        random_state=random_state,
    )

    preds = pd.Series(result["predictions"])
    true = pd.Series(result["true_labels"])
    accuracy = (preds == true).mean()
    misclassified_idx = preds.index[preds != true].tolist()
    conf = confusion_matrix(true, preds)

    # Extract classification report and identify weak classes
    report = classification_report(true, preds, output_dict=True, zero_division=0)
    report_df = pd.DataFrame(report).transpose()
    weak_classes = report_df[report_df["f1-score"] < f1_threshold].index.tolist()

    class_counts = y_ser.value_counts().to_dict()
    imbalance_ratio = max(class_counts.values()) / min(class_counts.values()) if class_counts else 1

    cv_scores = result.get("cv_scores")
    cv_mean = result.get("cv_score_mean")
    cv_std = float(np.std(cv_scores)) if cv_scores is not None else None
    oob_score = result.get("metadata", {}).get("oob_score")

    baseline_cv = None
    improvement = None
    if baseline_result is not None:
        baseline_cv = baseline_result.get("cv_score_mean")
        if baseline_cv is not None and cv_mean is not None:
            improvement = cv_mean - baseline_cv

    # Feature importance ranking
    model = result.get("model")
    importances = getattr(model, "feature_importances_", [])
    ranked_features = sorted(enumerate(importances), key=lambda x: x[1], reverse=True)[:5]

    if cv_scores is not None:
        print("Cross-validation F1 scores:", [round(s, 4) for s in cv_scores])
    print("Cross-validation F1 mean:", cv_mean)
    if cv_std is not None:
        print("Cross-validation F1 std :", round(cv_std, 4))
    if oob_score is not None:
        print("Out-of-bag score:", round(oob_score, 4))
    if baseline_cv is not None:
        print("Baseline CV mean:", round(baseline_cv, 4))
    if improvement is not None:
        print("CV mean improvement:", round(improvement, 4))
    print("Hold-out accuracy:", accuracy)
    print("Confusion matrix:\n", conf)
    print("Misclassified sample indices (first 10):", misclassified_idx[:10])
    print("Class distribution:", class_counts)
    if imbalance_ratio > 3:
        print(f"Warning: dataset imbalance ratio is {imbalance_ratio:.2f}. Consider SMOTE or class weighting.")
    if weak_classes:
        print(f"Classes with F1-score < {f1_threshold}:", weak_classes)
    if ranked_features:
        print("Top 5 feature importances:")
        for idx, score in ranked_features:
            print(f"  Feature {idx}: {score:.4f}")

    return {
        "accuracy": accuracy,
        "cv_scores": cv_scores,
        "cv_mean": cv_mean,
        "cv_std": cv_std,
        "oob_score": oob_score,
        "misclassified": misclassified_idx,
        "weak_classes": weak_classes,
        "ranked_features": ranked_features,
        "class_counts": class_counts,
        "imbalance_ratio": imbalance_ratio,
        "baseline_cv_mean": baseline_cv,
        "cv_improvement": improvement,
    }


if __name__ == "__main__":
    run_diagnostics(compare_baseline=True)
