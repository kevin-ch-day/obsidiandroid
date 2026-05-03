"""Feature schema comparison for ablation runs (fit vs prediction matrix)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import app_config


def build_ablation_schema_audit_row(
    *,
    model: Any,
    model_type: str,
    features_df: pd.DataFrame,
) -> dict[str, Any]:
    """Compare fitted model feature names to the prediction DataFrame columns.

    Returns:
        Dict suitable for ``ablation_feature_schema_audit.csv`` rows.
    """
    pred_names = [str(c) for c in features_df.columns]
    pred_count = len(pred_names)
    fit_names: list[str] | None = None
    if hasattr(model, "feature_names_in_"):
        fit_names = [str(x) for x in model.feature_names_in_]

    if fit_names is not None:
        fit_set = set(fit_names)
        pred_set = set(pred_names)
        missing = len(fit_set - pred_set)
        extra = len(pred_set - fit_set)
        order_ok = fit_names == pred_names
        if missing == 0 and extra == 0 and order_ok:
            status = "OK"
        elif missing == 0 and extra == 0 and not order_ok:
            status = "column_order_mismatch"
        else:
            status = "schema_mismatch"
        fit_count = len(fit_names)
    else:
        fit_count = int(getattr(model, "n_features_in_", pred_count))
        missing = extra = 0
        status = "OK" if fit_count == pred_count else "feature_count_mismatch"

    return {
        "feature_set": str(getattr(app_config, "RUNTIME_EXPERIMENT_ID", "") or ""),
        "model": model_type,
        "fit_column_count": fit_count,
        "predict_column_count": pred_count,
        "missing_at_predict_count": missing,
        "extra_at_predict_count": extra,
        "status": status,
    }


def schema_audit_passes(row: dict[str, Any]) -> bool:
    """Return True when prediction may proceed without schema mismatch."""
    return row.get("status") == "OK"


def append_ablation_schema_audit_row(row: dict[str, Any]) -> None:
    """Append a row to run-scoped ``RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS`` when active."""
    if not bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        return
    bucket = getattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", None)
    if isinstance(bucket, list):
        bucket.append(row)
