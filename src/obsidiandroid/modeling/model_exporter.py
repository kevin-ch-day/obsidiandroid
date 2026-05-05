"""Export trained ML models and metadata to disk (joblib + JSON sidecar)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from config import app_config
from obsidiandroid.cli.ui import display as du


def export_model_to_file(
    model,
    output_dir: Path,
    model_type: str = "unknown_model",
    metadata_dict: dict | None = None,
) -> Path | None:
    """Save a trained model and optional metadata under a run-scoped output tree.

    Args:
        model: Trained scikit-learn-compatible estimator.
        output_dir: Root output directory (e.g. project ``output/``).
        model_type: Short descriptor (e.g. ``random_forest``); used in path segments.
        metadata_dict: Optional extra metadata (metrics, features, etc.) written as JSON.

    Returns:
        Path to the saved ``.joblib`` file, or ``None`` if export failed.
    """
    try:
        model_type_clean = model_type.lower().replace(" ", "_")
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
        primary_root = output_dir
        if run_id and run_id.lower() != "unknown":
            primary_root = output_dir / "runs" / run_id
        model_dir = primary_root / "models" / model_type_clean
        model_dir.mkdir(parents=True, exist_ok=True)

        model_path = model_dir / f"{model_type_clean}_classifier_model.joblib"
        metadata_path = model_dir / f"{model_type_clean}_classifier_model_metadata.json"

        joblib.dump(model, model_path)
        du.print_success(f"Model exported successfully to: {model_path.resolve()}")

        if metadata_dict:
            enriched_metadata = _inject_model_metadata(model, model_type_clean, metadata_dict)
            cleaned_meta = _clean_metadata_for_json(enriched_metadata)
            with open(metadata_path, "w", encoding="utf-8") as meta_file:
                json.dump(cleaned_meta, meta_file, indent=2, allow_nan=False)
            du.print_success(f"Model metadata saved to: {metadata_path.resolve()}")

        return model_path

    except Exception as e:
        du.print_error(f"[EXPORT FAIL] Could not save model or metadata: {e}")
        return None


def _inject_model_metadata(model, model_type: str, metadata: dict) -> dict:
    metadata = metadata.copy()
    metadata.setdefault("model_type", model_type)
    metadata.setdefault("sklearn_class", model.__class__.__name__)
    metadata.setdefault("parameters", _safe_get_params(model))
    return metadata


def _safe_get_params(model):
    try:
        return model.get_params()
    except Exception:
        return "<unavailable>"


def _clean_metadata_for_json(metadata: dict) -> dict:
    return _sanitize_for_json(metadata)


def _sanitize_for_json(value):
    if value is None:
        return None

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating, float)):
        value = float(value)
        if not math.isfinite(value):
            return None
        return value

    if isinstance(value, (int, str, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}

    if isinstance(value, pd.DataFrame):
        return _sanitize_for_json(value.to_dict(orient="records"))

    if isinstance(value, (np.ndarray, pd.Series, list, tuple, set)):
        return [_sanitize_for_json(v) for v in list(value)]

    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return str(value)


__all__ = ["export_model_to_file"]
