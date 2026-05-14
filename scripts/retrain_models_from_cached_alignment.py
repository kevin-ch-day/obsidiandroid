"""Retrain models from cached aligned features and labels.

Use this to iterate quickly on model/CV settings without rerunning expensive
sample loading, AV matrix generation, and vendor parsing stages.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.pipeline import stage_modeling

run_training_stage = stage_modeling.run_training_stage


def _parse_models(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    models = [part.strip() for part in raw.split(",") if part.strip()]
    return models or None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrain models from cached aligned feature/label artifacts."
    )
    parser.add_argument(
        "--features",
        default=str(getattr(app_config, "ALIGNED_FEATURE_CACHE_FILE", "output/diagnostics/aligned_features.latest.csv.gz")),
        help="Path to aligned feature cache CSV(.gz).",
    )
    parser.add_argument(
        "--labels",
        default=str(getattr(app_config, "ALIGNED_LABEL_CACHE_FILE", "output/diagnostics/aligned_labels.latest.csv")),
        help="Path to aligned label cache CSV.",
    )
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model keys (e.g., random_forest,xgboost). Defaults to profile/model config.",
    )
    args = parser.parse_args()

    feature_path = Path(args.features)
    label_path = Path(args.labels)
    if not feature_path.exists():
        du.print_error(f"[RETRAIN] Feature cache not found: {feature_path}")
        return 1
    if not label_path.exists():
        du.print_error(f"[RETRAIN] Label cache not found: {label_path}")
        return 1

    du.print_section("Retrain Models from Cached Alignment")
    du.print_info(f"[RETRAIN] Loading features: {feature_path}")
    feature_df = pd.read_csv(feature_path)
    if "sample_id" not in feature_df.columns:
        du.print_error("[RETRAIN] Cached features missing required 'sample_id' column.")
        return 1
    feature_df = feature_df.set_index("sample_id")
    if "sample_id" not in feature_df.columns:
        feature_df["sample_id"] = feature_df.index

    du.print_info(f"[RETRAIN] Loading labels: {label_path}")
    label_df = pd.read_csv(label_path)
    if "sample_id" not in label_df.columns:
        du.print_error("[RETRAIN] Cached labels missing required 'sample_id' column.")
        return 1
    label_df = label_df.set_index("sample_id")
    if "sample_id" not in label_df.columns:
        label_df["sample_id"] = label_df.index

    selected_models = _parse_models(args.models)
    if selected_models:
        du.print_info(f"[RETRAIN] Requested models: {', '.join(selected_models)}")

    results = run_training_stage(
        aligned_feature_df=feature_df,
        aligned_labels_df=label_df,
        model_list=selected_models,
    )
    if not results:
        du.print_error("[RETRAIN] Training failed.")
        return 1
    du.print_success("[RETRAIN] Training completed using cached alignment inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
