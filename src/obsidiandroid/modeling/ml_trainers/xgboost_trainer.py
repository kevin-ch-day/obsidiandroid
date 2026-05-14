# Filename: training/ml_trainers/xgboost_trainer.py
# Purpose : Train an XGBoost classifier with structured metadata output

import time
import xgboost as xgb
import numpy as np
import pandas as pd
from collections import Counter
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from config import app_config
from obsidiandroid.modeling.parallel_layout import (
    grid_search_job_counts,
    stratified_kfold_for_grid_search,
)


def _resolve_xgb_runtime_guardrails(num_classes: int) -> dict:
    """Resolve adaptive XGBoost guardrails based on class cardinality.

    Args:
        num_classes: Number of unique labels in the training set.

    Returns:
        Dictionary containing capped n_estimators, early stopping rounds,
        and profile metadata for diagnostics.
    """
    base_estimators = int(getattr(app_config, "XGB_NUM_ESTIMATORS", 200))
    base_early_stopping = int(getattr(app_config, "XGB_EARLY_STOPPING_ROUNDS", 20))
    adaptive_enabled = bool(getattr(app_config, "XGB_ADAPTIVE_ESTIMATORS_ENABLED", True))

    medium_threshold = int(getattr(app_config, "XGB_GUARDRAIL_MEDIUM_CLASS_THRESHOLD", 25))
    large_threshold = int(getattr(app_config, "XGB_GUARDRAIL_LARGE_CLASS_THRESHOLD", 60))

    profile = "default"
    if num_classes >= large_threshold:
        profile = "large_multiclass"
    elif num_classes >= medium_threshold:
        profile = "medium_multiclass"

    profile_caps = dict(getattr(app_config, "XGB_GUARDRAIL_PROFILE_CAPS", {}) or {})
    default_caps = {
        "default": {
            "estimator_cap": base_estimators,
            "early_stopping_rounds": base_early_stopping,
        },
        "medium_multiclass": {
            "estimator_cap": int(getattr(app_config, "XGB_GUARDRAIL_MEDIUM_ESTIMATOR_CAP", 180)),
            "early_stopping_rounds": int(getattr(app_config, "XGB_GUARDRAIL_MEDIUM_EARLY_STOPPING", 15)),
        },
        "large_multiclass": {
            "estimator_cap": int(getattr(app_config, "XGB_GUARDRAIL_LARGE_ESTIMATOR_CAP", 120)),
            "early_stopping_rounds": int(getattr(app_config, "XGB_GUARDRAIL_LARGE_EARLY_STOPPING", 10)),
        },
    }
    merged_caps = {
        name: {
            **values,
            **dict(profile_caps.get(name, {}) or {}),
        }
        for name, values in default_caps.items()
    }
    selected_caps = merged_caps.get(profile, merged_caps["default"])

    cap = int(selected_caps.get("estimator_cap", base_estimators))
    early_stopping = min(
        base_early_stopping,
        int(selected_caps.get("early_stopping_rounds", base_early_stopping)),
    )
    resolved_estimators = min(base_estimators, cap) if adaptive_enabled else base_estimators

    return {
        "adaptive_enabled": adaptive_enabled,
        "profile": profile,
        "base_estimators": base_estimators,
        "resolved_estimators": resolved_estimators,
        "estimator_cap": cap,
        "base_early_stopping_rounds": base_early_stopping,
        "resolved_early_stopping_rounds": early_stopping,
    }


def _xgb_global_labels_need_contiguous_remap(encoded_y: np.ndarray, ontology_n: int) -> bool:
    """Return True iff sklearn+XGB multiclass rejects ``encoded_y`` gaps (sparse index set)."""
    if ontology_n <= 2:
        return False
    uniq = np.unique(np.asarray(encoded_y, dtype=np.int64).ravel())
    if uniq.size < 2:
        return False
    return bool(not np.array_equal(uniq, np.arange(int(uniq[-1]) + 1)))


def train_xgboost(
    X_train,
    y_train,
    X_test=None,
    y_test=None,
    sample_ids=None,
    label_encoder=None,
    random_state=42,
    verbose=False,
    grid_search=False,
    cv_folds=None,
    **kwargs
):
    # Multiclass sklearn XGBoost requires ``unique(y) == arange(max(y)+1)``.
    # Rare train splits + SMOTE/ROS can drop a middle encoded class; remap to contiguous indices.
    y_train_ser = y_train if isinstance(y_train, pd.Series) else pd.Series(np.asarray(y_train).ravel())
    y_train_flat = np.asarray(y_train_ser.to_numpy(dtype=np.int64, copy=False)).ravel()

    if label_encoder is not None and hasattr(label_encoder, "classes_"):
        ontology_n = int(len(label_encoder.classes_))
    elif y_train_flat.size:
        ontology_n = int(y_train_flat.max()) + 1
    else:
        ontology_n = 0

    present_codes, present_uniques_series = pd.factorize(y_train_ser, sort=True)
    present_encoded_order = np.asarray(present_uniques_series, dtype=np.int64)
    remap_to_contiguous = _xgb_global_labels_need_contiguous_remap(y_train_flat, ontology_n)

    if remap_to_contiguous:
        y_supervised = pd.Series(np.asarray(present_codes, dtype=np.int64), index=y_train_ser.index)
        present_encoded_lookup = present_encoded_order
    else:
        y_supervised = pd.Series(y_train_ser.to_numpy(dtype=np.int64, copy=False), index=y_train_ser.index)
        present_encoded_lookup = None

    if y_supervised.size:
        num_classes = int(np.max(y_supervised.to_numpy(dtype=np.int64, copy=False))) + 1
    else:
        num_classes = 0

    def _global_to_supervised(ys) -> pd.Series:
        if ys is None:
            return ys
        raw = ys if isinstance(ys, pd.Series) else pd.Series(np.asarray(ys).ravel())
        if present_encoded_lookup is None:
            return raw.astype(np.int64, copy=False)
        lut = {int(c): i for i, c in enumerate(present_encoded_lookup.tolist())}
        return pd.Series(
            [lut[int(v)] for v in raw.to_numpy(dtype=np.int64, copy=False)],
            index=raw.index,
        )

    class_counts = Counter(y_supervised)

    train_cardinality = int(len(present_encoded_order))
    guardrail_n = max(int(ontology_n or train_cardinality), train_cardinality or 1)
    guardrails = _resolve_xgb_runtime_guardrails(num_classes=guardrail_n)

    objective = "binary:logistic" if num_classes == 2 else "multi:softprob"
    eval_metric = "logloss" if num_classes == 2 else "mlogloss"

    # Main XGBoost parameter set
    params = {
        "n_estimators": guardrails["resolved_estimators"],
        "max_depth": getattr(app_config, "XGB_MAX_DEPTH", 6),
        "learning_rate": getattr(app_config, "XGB_LEARNING_RATE", 0.1),
        "objective": objective,
        "eval_metric": eval_metric,
        "tree_method": "hist",
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 2,
        "gamma": 0.2,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "n_jobs": -1,
        "random_state": random_state,
        "verbosity": 0 if not getattr(app_config, "DEBUG_MODE", False) else 1,
    }
    if num_classes > 2:
        params["num_class"] = num_classes

    # scale_pos_weight is only applicable to binary classification objectives.
    if num_classes == 2:
        majority_class_size = max(class_counts.values())
        params["scale_pos_weight"] = majority_class_size / np.mean(list(class_counts.values()))

    early_stopping_rounds = kwargs.pop(
        "early_stopping_rounds",
        guardrails["resolved_early_stopping_rounds"],
    )

    # Merge custom parameters after removing fit-time only kwargs.
    model_params = {**params, **kwargs}
    if guardrails["adaptive_enabled"]:
        requested_estimators = int(model_params.get("n_estimators", guardrails["resolved_estimators"]))
        model_params["n_estimators"] = min(requested_estimators, int(guardrails["estimator_cap"]))

    start = time.time()
    fit_kwargs = {}
    calibration_enabled = bool(getattr(app_config, "ENABLE_PROBABILITY_CALIBRATION", False))
    calibration_method = getattr(app_config, "CALIBRATION_METHOD", "sigmoid")
    calibration_holdout = float(getattr(app_config, "CALIBRATION_HOLDOUT", 0.15))
    X_fit, y_fit = X_train, y_supervised
    X_cal, y_cal = None, None

    if calibration_enabled:
        try:
            min_class_size = min(class_counts.values())
            if min_class_size >= 2:
                X_fit, X_cal, y_fit, y_cal = train_test_split(
                    X_train,
                    y_supervised,
                    test_size=calibration_holdout,
                    stratify=y_supervised,
                    random_state=random_state,
                )
                if verbose:
                    print(
                        f"[XGBOOST] Calibration holdout prepared: fit={len(X_fit)}, cal={len(X_cal)}"
                    )
            else:
                calibration_enabled = False
        except Exception:
            calibration_enabled = False

    model = None
    if grid_search or getattr(app_config, "ENABLE_XGB_GRID_SEARCH", False):
        from sklearn.model_selection import GridSearchCV

        param_grid = getattr(
            app_config,
            "XGB_PARAM_GRID",
            {
                "n_estimators": [200, 300],
                "max_depth": [6, 8],
                "learning_rate": [0.05, 0.1],
            },
        )
        if guardrails["adaptive_enabled"] and "n_estimators" in param_grid:
            cap = int(guardrails["estimator_cap"])
            capped_estimators = sorted(
                {min(int(value), cap) for value in param_grid.get("n_estimators", [])}
            )
            if capped_estimators:
                param_grid = {**param_grid, "n_estimators": capped_estimators}

        min_class_size = min(class_counts.values())
        cv_splitter = stratified_kfold_for_grid_search(
            min_class_size, random_state=random_state
        )
        if cv_splitter is None:
            if verbose:
                print(
                    "[XGBOOST] Grid search skipped: need ≥2 samples per class "
                    f"(minimum count was {min_class_size}). Fitting default parameters."
                )
        else:
            inner_jobs, grid_jobs = grid_search_job_counts()
            base_params = {k: v for k, v in model_params.items() if k not in param_grid}
            base_params["n_jobs"] = inner_jobs
            estimator = xgb.XGBClassifier(**base_params)

            grid = GridSearchCV(
                estimator=estimator,
                param_grid=param_grid,
                cv=cv_splitter,
                scoring="f1_macro",
                n_jobs=grid_jobs,
            )
            grid.fit(X_fit, y_fit)
            model = grid.best_estimator_
            model_params.update(grid.best_params_)

    if model is None:
        model = xgb.XGBClassifier(**model_params)

        eval_x = X_test
        eval_y = y_test
        if X_cal is not None and y_cal is not None:
            eval_x, eval_y = X_cal, y_cal
        elif y_test is not None and present_encoded_lookup is not None:
            eval_y = _global_to_supervised(y_test)

        if early_stopping_rounds and eval_x is not None and eval_y is not None:
            fit_verbose = bool(verbose and getattr(app_config, "DEBUG_MODE", False))
            fit_kwargs = {
                "eval_set": [(eval_x, eval_y)],
                "early_stopping_rounds": early_stopping_rounds,
                "verbose": fit_verbose,
            }

        try:
            model.fit(X_fit, y_fit, **fit_kwargs)
        except TypeError:
            esr = fit_kwargs.pop("early_stopping_rounds", None)
            model.set_params(early_stopping_rounds=esr)
            model.fit(X_fit, y_fit, **fit_kwargs)

    if calibration_enabled and X_cal is not None and y_cal is not None:
        try:
            calibrated = CalibratedClassifierCV(model, method=calibration_method, cv="prefit")
            calibrated.fit(X_cal, y_cal)
            model = calibrated
        except Exception:
            calibration_enabled = False

    duration = time.time() - start

    results = {
        "metadata": {
            "duration": duration,
            "params": model_params,
            "num_classes": num_classes,
            "ontology_classes": ontology_n if ontology_n else None,
            "xgb_encoded_label_remap": present_encoded_lookup.tolist()
            if present_encoded_lookup is not None
            else None,
            "top_classes": class_counts.most_common(5),
            "best_iteration": getattr(model, "best_iteration", None),
            "xgb_guardrail_profile": guardrails["profile"],
            "xgb_adaptive_estimators_enabled": guardrails["adaptive_enabled"],
            "xgb_base_estimators": guardrails["base_estimators"],
            "xgb_estimator_cap": guardrails["estimator_cap"],
            "xgb_effective_estimators": model_params.get("n_estimators"),
            "xgb_base_early_stopping_rounds": guardrails["base_early_stopping_rounds"],
            "xgb_effective_early_stopping_rounds": early_stopping_rounds,
            "calibrated": bool(calibration_enabled),
            "calibration_method": calibration_method if calibration_enabled else None,
            "calibration_holdout_size": len(X_cal) if X_cal is not None else 0,
        }
    }

    # Evaluate model if test set provided
    if X_test is not None and y_test is not None:
        y_pred = model.predict(X_test)
        y_pred_global_idx = np.asarray(y_pred, dtype=np.int64).ravel()
        if present_encoded_lookup is not None:
            y_pred_global_idx = present_encoded_lookup[y_pred_global_idx]

        y_prob = model.predict_proba(X_test)
        confidences = np.max(y_prob, axis=1)

        def _decoded_row(encoded_idx: int):
            return (
                label_encoder.classes_[encoded_idx]
                if label_encoder is not None and 0 <= encoded_idx < len(label_encoder.classes_)
                else str(encoded_idx)
            )

        if sample_ids and len(sample_ids) == len(y_pred_global_idx):
            predictions_dict = {sid: int(pred) for sid, pred in zip(sample_ids, y_pred_global_idx)}
            labels_dict = {sid: int(label) for sid, label in zip(sample_ids, y_test)}
            meta_dict = {sid: _decoded_row(pred) for sid, pred in predictions_dict.items()}
        else:
            predictions_dict = list(y_pred_global_idx)
            labels_dict = list(y_test)
            meta_dict = [_decoded_row(int(pred)) for pred in y_pred_global_idx]

        report = classification_report(
            pd.Series(np.asarray(y_test).ravel(), dtype=np.int64),
            y_pred_global_idx,
            output_dict=True,
            zero_division=0,
        )

        results.update({
            "predictions": predictions_dict,
            "true_labels": labels_dict,
            "confidences": confidences,
            "metadata": {
                **results["metadata"],
                "classification_report": report,
                "average_confidence": float(np.mean(confidences))
            },
            "label_encoder": label_encoder,
            "label_classes": list(label_encoder.classes_) if label_encoder else None,
            "enriched_labels": meta_dict
        })

    return model, results


def get_default_xgboost_params():
    return {
        "n_estimators": getattr(app_config, "XGB_NUM_ESTIMATORS", 200),
        "max_depth": getattr(app_config, "XGB_MAX_DEPTH", 6),
        "learning_rate": getattr(app_config, "XGB_LEARNING_RATE", 0.1),
        "min_child_weight": 2,
        "gamma": 0.2,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "objective": "multi:softprob",
        "eval_metric": "mlogloss",
        "tree_method": "hist",
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "n_jobs": -1,
    }


def get_model_name():
    return "xgboost"
