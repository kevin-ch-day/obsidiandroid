# prediction_builder.py

import traceback
from pathlib import Path
import pandas as pd
from obsidiandroid.modeling import model_exporter
from obsidiandroid.cli.ui import display as du
from obsidiandroid.modeling import ml_result_analyzer
from obsidiandroid.modeling import model_prediction
from obsidiandroid.features import feature_schema_audit
from config import app_config


def export_model(
    result, model_type, features_df, evaluation, output_dir: Path
):
    """Export model and metadata to disk."""
    try:
        raw_feature_importances = result.get("metadata", {}).get("feature_importances")
        named_feature_importances = []
        if raw_feature_importances and hasattr(features_df, "columns"):
            feature_columns = list(features_df.columns)
            for idx, score in raw_feature_importances:
                feature_name = (
                    str(feature_columns[idx])
                    if isinstance(idx, int) and 0 <= idx < len(feature_columns)
                    else f"feature_{idx}"
                )
                named_feature_importances.append(
                    {
                        "feature_index": int(idx) if isinstance(idx, int) else idx,
                        "feature_name": feature_name,
                        "importance": float(score),
                    }
                )
        if isinstance(result.get("metadata"), dict):
            result["metadata"]["feature_importances_named"] = named_feature_importances

        metadata = {
            "model_type": model_type,
            "classes": result.get("label_classes", []),
            "label_name_map": result.get("label_name_map", {}),
            "evaluation": {
                k: v
                for k, v in evaluation.items()
                if isinstance(v, (int, float, str))
            },
            "num_samples": len(features_df),
            "cv_scores": result.get("cv_scores"),
            "cv_score_mean": result.get("cv_score_mean"),
            "feature_importances": raw_feature_importances,
            "feature_importances_named": named_feature_importances,
            "oob_score": result.get("metadata", {}).get("oob_score"),
        }
        model_path = model_exporter.export_model_to_file(
            model=result.get("model"),
            output_dir=output_dir,
            model_type=model_type,
            metadata_dict=metadata,
        )
        if not model_path:
            du.print_warning(f"[EXPORT] Model '{model_type}' export did not return a path.")
    except Exception as e:
        du.print_error(f"[EXPORT] Failed to export model: {e}")
        du.print_debug(traceback.format_exc())


def run_predictions_and_compile_result(
    model_type, result, features_df: pd.DataFrame, labels: pd.Series
):
    """Run predictions on the full dataset and assemble the final result."""
    try:
        du.print_debug(
            f"[{model_type.upper()}] Running full dataset prediction..."
        )

        model = result.get("model")
        if model is None:
            du.print_error(
                f"[{model_type.upper()}] Missing trained model instance."
            )
            return {}

        label_encoder = result.get("label_encoder")
        if label_encoder is None:
            du.print_error(f"[{model_type.upper()}] Missing label encoder.")
            return {}

        if features_df is None or features_df.empty:
            du.print_error(
                f"[{model_type.upper()}] Feature DataFrame is empty or "
                "missing."
            )
            return {}

        if labels is None or len(labels) == 0:
            du.print_error(
                f"[{model_type.upper()}] Label list is empty or missing."
            )
            return {}

        schema_row = feature_schema_audit.build_ablation_schema_audit_row(
            model=model,
            model_type=model_type,
            features_df=features_df,
        )
        if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
            fit_h = str(schema_row.get("fit_feature_column_hash") or "")
            setattr(app_config, "RUNTIME_LAST_FIT_FEATURE_COLUMN_HASH", fit_h)
        feature_schema_audit.append_ablation_schema_audit_row(schema_row)
        if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
            if not feature_schema_audit.schema_audit_passes(schema_row):
                du.print_error(
                    f"[ABLATION-SCHEMA] {model_type}: blocked full prediction/report "
                    f"(status={schema_row.get('status')}). "
                    f"fit_columns={schema_row.get('fit_column_count')} "
                    f"predict_columns={schema_row.get('predict_column_count')} "
                    f"missing_at_predict={schema_row.get('missing_at_predict_count')} "
                    f"extra_at_predict={schema_row.get('extra_at_predict_count')}. "
                    "Align prediction matrix columns to the fitted feature schema."
                )
                return {}

        preds, trues, decoded_labels, confidences = (
            model_prediction.predict_all_samples(
                model=model,
                features_df=features_df,
                labels=labels,
                label_encoder=label_encoder,
            )
        )

        sample_ids = features_df.index.tolist()
        pred_dict = dict(zip(sample_ids, preds))
        true_dict = dict(zip(sample_ids, trues))
        meta_dict = {
            sid: {
                "decoded_label": decoded_labels[i],
                "confidence": (
                    float(confidences[i]) if len(confidences) > i else 0.0
                ),
            }
            for i, sid in enumerate(sample_ids)
        }

        if bool(getattr(app_config, "ML_SHOW_PREDICTION_PREVIEWS", False)):
            ml_result_analyzer.show_prediction_sample(
                pred_dict,
                label_encoder=label_encoder,
                limit=3,
                model_name=model_type,
            )

        du.print_debug(
            f"[{model_type.upper()}] Prediction count: {len(preds)}"
        )
        du.print_debug(
            f"[{model_type.upper()}] True labels count: {len(trues)}"
        )
        du.print_debug(
            f"[{model_type.upper()}] Confidence shape: {len(confidences)}"
        )

        if not bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False)):
            model_prediction.report_prediction_stats(decoded_labels, confidences)

        label_name_map = {}
        try:
            maybe_map = getattr(labels, "attrs", {}).get("label_name_map", {})
            if isinstance(maybe_map, dict):
                label_name_map = {
                    str(k): str(v) for k, v in maybe_map.items()
                    if str(k).strip() and str(v).strip()
                }
        except Exception:
            label_name_map = {}

        final_result = {
            "model": model,
            "X_test": result.get("X_test"),
            "y_test": result.get("y_test"),
            "evaluation": result.get("evaluation"),
            "label_classes": result.get("label_classes", []),
            "label_encoder": label_encoder,
            "predictions": pred_dict,
            "true_labels": true_dict,
            "metadata": result.get("metadata", {}),
            "prediction_metadata": meta_dict,
            "confidences": confidences,
            "label_name_map": label_name_map,
        }

        du.print_debug(
            f"[{model_type.upper()}] Final result dictionary created with "
            f"{len(final_result)} keys."
        )
        return final_result

    except Exception as e:
        du.print_error(
            f"[PREDICT] Failed during full prediction/report: {e}"
        )
        du.print_debug(traceback.format_exc())
        return {}
