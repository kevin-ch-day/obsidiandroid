"""Utility script to train Random Forest and XGBoost models on
Android malware samples pulled from the database.

The script loads sample metadata using the helper functions in
``database/db_sample_metadata_queries.py`` and builds a small
feature table from a handful of metadata fields. Results include
cross‑validation F1 scores and a hold‑out evaluation summary.

Run directly to execute with default parameters::

    python model_tuning.py
"""

from __future__ import annotations

import argparse
import pandas as pd
from typing import Dict, Any
from utils import display_utils as du
from utils.sample_metadata_preprocessor import prepare_sample_dataframe
from utils import profile_manager
from database import db_sample_metadata_queries
from ml_classification.training import model_trainer_factory
from config import app_config


def _load_samples(
    profile_ref: str = "banker",
    min_family_size: int | None = None,
) -> pd.DataFrame:
    """Load samples using profile-driven dataset selection."""
    profile = profile_manager.load_profile(profile_ref)
    gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
    type_slug = profile.get("type_slug_filter")
    min_support = (
        int(min_family_size)
        if min_family_size is not None
        else int(gates.get("min_samples_per_family", 3))
    )
    if not type_slug:
        min_support = None

    df = db_sample_metadata_queries.load_samples_by_type(
        type_slug=type_slug,
        min_samples_per_family=min_support,
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        limit=gates.get("limit", None),
    )
    if df.empty:
        du.print_error("[DATA] No samples retrieved from the database.")
        return pd.DataFrame()

    df = prepare_sample_dataframe(
        df,
        label="DB Samples",
        enforce_index=False,
        drop_duplicate_rows=True,
    )
    return df


def _build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    """Create a simple feature table from sample metadata."""
    if df.empty:
        return pd.DataFrame()

    du.print_subheader("Building Feature Table")
    work = df.copy()

    # Rough permission count feature
    work["permission_count"] = work["permissions"].fillna("").apply(
        lambda x: len(str(x).split()) if isinstance(x, str) else int(x or 0)
    )

    cols = [
        "category_primary",
        "category_subtype",
        "vt_scan_status",
        "target_min_version",
        "target_sdk_version",
        "permission_count",
    ]
    feat = work[cols].copy()

    cat_cols = ["category_primary", "category_subtype", "vt_scan_status"]
    for col in cat_cols:
        feat[col] = feat[col].astype("category").cat.codes

    feat = feat.fillna(0)
    du.print_success(f"[FEATURES] Final shape: {feat.shape}")
    return feat


def tune_models(
    *,
    profile_ref: str = "banker",
    min_family_size: int = 3,
    rf_grid: bool = True,
    xgb_grid: bool = False,
    test_size: float = 0.25,
    random_state: int = 42,
    cv_folds: int | None = None,
) -> Dict[str, Any]:
    """Train Random Forest and XGBoost models and return the result dictionary."""
    samples = _load_samples(profile_ref=profile_ref, min_family_size=min_family_size)
    if samples.empty:
        return {}

    features = _build_feature_table(samples)
    label_col = next(
        (c for c in ["family_id", "family_canonical", "family_name"] if c in samples.columns),
        None,
    )
    if label_col is None:
        du.print_error("[DATA] No usable label column found in sample metadata.")
        return {}
    labels = samples[label_col].astype(str)

    if cv_folds is not None:
        setattr(app_config, "CV_FOLDS", cv_folds)

    results: Dict[str, Any] = {}
    for model in ("random_forest", "xgboost"):
        du.print_section(f"Training {model.upper()}")
        grid_flag = rf_grid if model == "random_forest" else xgb_grid
        results[model] = model_trainer_factory.train_model_factory(
            features_df=features,
            labels=labels,
            model_type=model,
            enable_grid_search=grid_flag,
            cross_validate=True,
            test_size=test_size,
            random_state=random_state,
        )
    return results


def print_summary(results: Dict[str, Any]) -> None:
    """Display CV and hold‑out F1 metrics for each trained model."""
    if not results:
        du.print_error("No results to summarize.")
        return

    for name, res in results.items():
        du.print_subheader(f"Results: {name.upper()}")
        cv_scores = res.get("cv_scores")
        if cv_scores is not None:
            scores = [round(float(s), 4) for s in cv_scores]
            du.print_info(f"CV F1 scores : {scores}")
            du.print_info(f"CV F1 mean   : {round(float(res.get('cv_score_mean', 0)), 4)}")
        preds = pd.Series(res.get("predictions", []))
        true = pd.Series(res.get("true_labels", []))
        if not preds.empty and not true.empty:
            from sklearn.metrics import classification_report, confusion_matrix

            report = classification_report(true, preds, output_dict=True, zero_division=0)
            f1 = report.get("weighted avg", {}).get("f1-score")
            if f1 is not None:
                du.print_success(f"Hold-out F1 : {round(float(f1), 4)}")
            du.print_info("Confusion matrix:\n" + str(confusion_matrix(true, preds)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tune ML models on DB samples")
    parser.add_argument(
        "--profile",
        default="banker",
        help="Profile id from /profiles (default: banker)",
    )
    parser.add_argument("--min-family-size", type=int, default=3, help="Minimum samples per family")
    parser.add_argument("--rf-grid", action="store_true", help="Enable RandomForest grid search")
    parser.add_argument("--xgb-grid", action="store_true", help="Enable XGBoost grid search")
    parser.add_argument("--cv-folds", type=int, help="Override number of CV folds")
    args = parser.parse_args()

    summary = tune_models(
        profile_ref=args.profile,
        min_family_size=args.min_family_size,
        rf_grid=args.rf_grid,
        xgb_grid=args.xgb_grid,
        cv_folds=args.cv_folds,
    )
    print_summary(summary)
