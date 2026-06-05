"""Headline held-out test tables (predictions + errors) for evidence contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import json

from config import app_config


def _headline_split_meta() -> dict[str, Any]:
    headline = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    if isinstance(headline, dict) and headline.get("split_hash"):
        return headline
    fallback = getattr(app_config, "RUNTIME_SPLIT_METADATA", None)
    return dict(fallback) if isinstance(fallback, dict) else {}


def export_headline_test_tables(
    *,
    results: dict[str, Any],
    promoted_model_key: str,
    diagnostics_dir: Path,
    run_id: str,
    label_field: str,
) -> tuple[Path | None, Path | None]:
    """Write ``headline_test_predictions_*`` and ``headline_test_errors_*`` (strict test split only)."""
    result = results.get(promoted_model_key) if isinstance(results, dict) else None
    if not isinstance(result, dict):
        return None, None
    X_test = result.get("X_test")
    y_test = result.get("y_test")
    model = result.get("model")
    label_encoder = result.get("label_encoder")
    evaluation = result.get("evaluation", {}) if isinstance(result.get("evaluation"), dict) else {}
    if (
        not isinstance(X_test, pd.DataFrame)
        or y_test is None
        or model is None
        or len(X_test) != len(np.asarray(y_test).ravel())
    ):
        return None, None

    y_true = evaluation.get("y_true")
    y_pred = evaluation.get("y_pred")
    if y_true is None or y_pred is None:
        return None, None

    test_ids = pd.to_numeric(X_test.index, errors="coerce")
    if test_ids.isna().any():
        return None, None
    test_ids = test_ids.astype(int)

    split_meta = _headline_split_meta()
    split_hash = str(split_meta.get("split_hash", "") or "")
    feature_hash = str(getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or "")
    runtime_label_name_map = getattr(app_config, "RUNTIME_LABEL_NAME_MAP", {})
    result_label_name_map = result.get("label_name_map", {}) if isinstance(result, dict) else {}
    label_name_map: dict[str, str] = {}
    for candidate in (result_label_name_map, runtime_label_name_map):
        if isinstance(candidate, dict):
            for key, value in candidate.items():
                skey = str(key).strip()
                sval = str(value).strip()
                if skey and sval:
                    label_name_map[skey] = sval

    meta = getattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", None)
    meta_by_id: dict[int, dict[str, Any]] = {}
    if isinstance(meta, pd.DataFrame) and not meta.empty and "sample_id" in meta.columns:
        m = meta.copy()
        m["sample_id"] = pd.to_numeric(m["sample_id"], errors="coerce").astype("Int64")
        m = m.dropna(subset=["sample_id"])
        for _, row in m.iterrows():
            sid = int(row["sample_id"])
            meta_by_id[sid] = row.to_dict()

    perm_cols = [
        c for c in X_test.columns if str(c).startswith("perm__") or str(c).startswith("perm_grp__")
    ]
    vendor_markers = ("parsed_family", "threat_class", "malware_type")
    vend_cols = [
        c
        for c in X_test.columns
        if any(marker in str(c).lower() for marker in vendor_markers)
    ]

    def _row_flags(sid: int) -> tuple[int, int, int]:
        try:
            xr = X_test.loc[[sid]]
        except Exception:
            return 0, 0, 0
        perm_ok = 0
        if perm_cols:
            mass = xr[perm_cols].fillna(0).abs().sum(axis=1).iloc[0]
            perm_ok = int(float(mass) > 0)
        vend_ok = 0
        if vend_cols:
            mass_v = xr[vend_cols].fillna(0).abs().sum(axis=1).iloc[0]
            vend_ok = int(float(mass_v) > 0)
        mismatch = 0
        info = meta_by_id.get(sid)
        if isinstance(info, dict):
            ts = str(info.get("type_slug", "") or "").strip().lower()
            ex = str(info.get("type_slug_expected", "") or "").strip().lower()
            if ts and ex and ts != ex:
                mismatch = 1
        return perm_ok, vend_ok, mismatch

    def _name_for_label(val: Any) -> str:
        normalized_key = str(val).strip()
        if normalized_key in label_name_map:
            return label_name_map[normalized_key]
        if label_encoder is not None:
            try:
                inv = label_encoder.inverse_transform(
                    [int(val) if not isinstance(val, (str, np.str_)) else int(float(str(val)))]
                )
                return str(inv[0])
            except Exception:
                pass
        return str(val)

    proba = None
    if hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(X_test)
        except Exception:
            proba = None

    classes = list(getattr(label_encoder, "classes_", [])) if label_encoder is not None else []
    n_classes = len(classes)

    rows_pred: list[dict[str, Any]] = []
    for i, sid in enumerate(test_ids.tolist()):
        yt = np.asarray(y_true).ravel()[i]
        yp = np.asarray(y_pred).ravel()[i]
        perm_f, vend_f, tax_f = _row_flags(int(sid))
        conf = None
        top2_label_id = ""
        top2_confidence_val = None
        if isinstance(proba, np.ndarray) and proba.shape[0] > i:
            rowp = proba[i]
            conf = float(np.max(rowp))
            order = np.argsort(-rowp)
            if order.size >= 2:
                i2 = int(order[1])
                top2_cls = classes[i2] if i2 < n_classes else i2
                top2_label_id = str(top2_cls)
                top2_confidence_val = float(rowp[i2])
        info = meta_by_id.get(int(sid), {})
        pkg = str(info.get("package_name", "") or "") if isinstance(info, dict) else ""
        sha = str(info.get("sha256", "") or "") if isinstance(info, dict) else ""
        rows_pred.append(
            {
                "sample_id": int(sid),
                "sha256": sha,
                "package_name": pkg,
                "true_label_id": str(yt),
                "true_label_name": _name_for_label(yt),
                "predicted_label_id": str(yp),
                "predicted_label_name": _name_for_label(yp),
                "confidence": conf,
                "second_best_label_id": top2_label_id,
                "second_best_confidence": top2_confidence_val,
                "split_role": "test",
                "split_hash": split_hash,
                "feature_column_hash": feature_hash,
                "supervision_label_field": str(label_field),
                "taxonomy_type_mismatch_flag": tax_f,
                "permission_coverage_flag": perm_f,
                "vendor_coverage_flag": vend_f,
            }
        )

    pred_df = pd.DataFrame(rows_pred)
    err_df = pred_df[pred_df["true_label_id"].astype(str) != pred_df["predicted_label_id"].astype(str)].copy()

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    pred_path = diagnostics_dir / f"headline_test_predictions_{run_id}.csv"
    err_path = diagnostics_dir / f"headline_test_errors_{run_id}.csv"
    pred_df.to_csv(pred_path, index=False)
    err_df.to_csv(err_path, index=False)
    _write_headline_confidence_audit(
        pred_df=pred_df,
        err_df=err_df,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        promoted_model_key=promoted_model_key,
    )
    return pred_path, err_path


def _write_headline_confidence_audit(
    *,
    pred_df: pd.DataFrame,
    err_df: pd.DataFrame,
    diagnostics_dir: Path,
    run_id: str,
    promoted_model_key: str,
) -> None:
    """Write compact held-out confidence calibration risk summaries."""
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": str(run_id),
        "model": str(promoted_model_key),
        "confidence_available": False,
        "total_predictions": int(len(pred_df)),
        "total_errors": int(len(err_df)),
        "overall_error_rate": (float(len(err_df)) / float(len(pred_df))) if len(pred_df) else 0.0,
        "high_confidence_error_count_0_95": 0,
        "high_confidence_error_count_0_99": 0,
    }

    if "confidence" not in pred_df.columns:
        audit_path = diagnostics_dir / f"headline_confidence_audit_{run_id}.json"
        audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    conf_series = pd.to_numeric(pred_df["confidence"], errors="coerce")
    valid_conf = conf_series.dropna()
    if valid_conf.empty:
        audit_path = diagnostics_dir / f"headline_confidence_audit_{run_id}.json"
        audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    payload["confidence_available"] = True
    payload["median_confidence"] = float(valid_conf.median())
    payload["p95_confidence"] = float(valid_conf.quantile(0.95))
    payload["p99_confidence"] = float(valid_conf.quantile(0.99))
    payload["max_confidence"] = float(valid_conf.max())

    err_conf = pd.to_numeric(err_df.get("confidence"), errors="coerce").dropna()
    payload["high_confidence_error_count_0_95"] = int((err_conf >= 0.95).sum())
    payload["high_confidence_error_count_0_99"] = int((err_conf >= 0.99).sum())
    if not err_conf.empty:
        payload["median_error_confidence"] = float(err_conf.median())
        payload["max_error_confidence"] = float(err_conf.max())

    bucket_edges = [0.0, 0.5, 0.7, 0.9, 0.95, 0.99, 1.000001]
    bucket_labels = [
        "[0.00,0.50)",
        "[0.50,0.70)",
        "[0.70,0.90)",
        "[0.90,0.95)",
        "[0.95,0.99)",
        "[0.99,1.00]",
    ]
    audit_df = pred_df.copy()
    audit_df["confidence_num"] = conf_series
    audit_df["is_error"] = (
        audit_df["true_label_id"].astype(str) != audit_df["predicted_label_id"].astype(str)
    ).astype(int)
    audit_df = audit_df.dropna(subset=["confidence_num"]).copy()
    audit_df["confidence_bucket"] = pd.cut(
        audit_df["confidence_num"],
        bins=bucket_edges,
        labels=bucket_labels,
        include_lowest=True,
        right=False,
    ).astype(str)
    bucket_rows: list[dict[str, Any]] = []
    for bucket in bucket_labels:
        bucket_df = audit_df[audit_df["confidence_bucket"] == bucket]
        pred_n = int(len(bucket_df))
        err_n = int(bucket_df["is_error"].sum()) if pred_n else 0
        bucket_rows.append(
            {
                "confidence_bucket": bucket,
                "prediction_count": pred_n,
                "error_count": err_n,
                "error_rate": (float(err_n) / float(pred_n)) if pred_n else 0.0,
            }
        )
    bucket_path = diagnostics_dir / f"headline_confidence_buckets_{run_id}.csv"
    pd.DataFrame(bucket_rows).to_csv(bucket_path, index=False)
    payload["confidence_bucket_csv"] = str(bucket_path)

    top_err_rows: list[dict[str, Any]] = []
    if not err_df.empty and "confidence" in err_df.columns:
        err_sorted = err_df.copy()
        err_sorted["confidence_num"] = pd.to_numeric(err_sorted["confidence"], errors="coerce")
        err_sorted = err_sorted.dropna(subset=["confidence_num"]).sort_values(
            by="confidence_num", ascending=False
        )
        for _, row in err_sorted.head(5).iterrows():
            top_err_rows.append(
                {
                    "sample_id": int(row["sample_id"]),
                    "true_label_name": str(row.get("true_label_name", "") or ""),
                    "predicted_label_name": str(row.get("predicted_label_name", "") or ""),
                    "confidence": float(row["confidence_num"]),
                    "second_best_confidence": (
                        float(row["second_best_confidence"])
                        if pd.notna(row.get("second_best_confidence"))
                        else None
                    ),
                }
            )
    payload["top_high_confidence_errors"] = top_err_rows

    audit_path = diagnostics_dir / f"headline_confidence_audit_{run_id}.json"
    audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["export_headline_test_tables"]
