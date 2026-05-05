"""Generate publication-facing structural diagnostics from latest artifacts.

This script consolidates key structural diagnostics for reproducibility and
publication review:
- Global top feature importances (named)
- Vendor removed vs fused comparison
- Families driving macro/weighted divergence
- Cross-type confusion summary availability
- selected_vendor_count distribution across runs
- type_slug-only baseline
- temporal split baseline (early->late)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
for _p in (_REPO_ROOT, _SRC):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from obsidiandroid.database import db_engine


def _resolve_paths() -> dict[str, Path]:
    """Resolve structural diagnostics input/output paths.

    Prefers run-scoped diagnostics when ``SCYTALEDROID_RUN_ID`` is provided.
    """
    output_root = Path(os.environ.get("SCYTALEDROID_OUTPUT_ROOT", "output")).resolve()
    run_id = str(os.environ.get("SCYTALEDROID_RUN_ID", "")).strip()
    run_root = output_root / "runs" / run_id if run_id else output_root
    run_diag = run_root / "diagnostics"
    global_diag = output_root / "diagnostics"
    bundles_root = output_root / "bundles"
    latest_bundle = bundles_root / "latest" / "permission_trends"
    run_bundle = run_root / "bundles" / "permission_trends" if run_id else latest_bundle
    return {
        "output_root": output_root,
        "run_root": run_root,
        "run_diag": run_diag,
        "global_diag": global_diag,
        "run_bundle": run_bundle,
        "latest_bundle": latest_bundle,
        "run_id": Path(run_id) if run_id else Path(""),
    }


def _pick_existing(*candidates: Path) -> Path:
    """Return first existing path from candidates, else first candidate."""
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_named_importances() -> pd.DataFrame:
    paths = _resolve_paths()
    meta_path = _pick_existing(
        paths["run_root"] / "models" / "random_forest" / "random_forest_classifier_model_metadata.json",
        paths["output_root"] / "models" / "random_forest" / "random_forest_classifier_model_metadata.json",
    )
    contract_path = _pick_existing(
        paths["run_diag"] / "feature_contract.latest.json",
        paths["global_diag"] / "feature_contract.latest.json",
    )
    if not meta_path.exists():
        return pd.DataFrame()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    named = metadata.get("feature_importances_named")
    if isinstance(named, list) and named:
        df = pd.DataFrame(named)
        if "importance" in df.columns:
            return df.sort_values("importance", ascending=False).head(20).reset_index(drop=True)

    # Backward compatibility for older metadata that stored only (index, score).
    raw = metadata.get("feature_importances") or []
    if not raw:
        return pd.DataFrame()
    feature_cols: list[str] = []
    if contract_path.exists():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        feature_cols = [str(c) for c in contract.get("feature_columns", [])]
    rows: list[dict[str, Any]] = []
    for idx, score in raw:
        name = feature_cols[idx] if isinstance(idx, int) and idx < len(feature_cols) else f"feature_{idx}"
        rows.append(
            {
                "feature_index": int(idx) if isinstance(idx, int) else idx,
                "feature_name": name,
                "importance": float(score),
            }
        )
    return pd.DataFrame(rows).sort_values("importance", ascending=False).head(20).reset_index(drop=True)


def _vendor_removed_vs_fused(abl_df: pd.DataFrame) -> pd.DataFrame:
    if abl_df.empty:
        return pd.DataFrame()
    sub = abl_df[abl_df["model"] == "random_forest"].copy()
    keep = sub[sub["experiment"].isin(["permissions_only", "vendor_permissions_fused", "vendor_only"])]
    cols = ["experiment", "accuracy", "macro_f1_score", "macro_precision", "macro_recall", "samples_tested"]
    return keep[cols].sort_values("experiment").reset_index(drop=True)


def _family_drag(abl_per_family_df: pd.DataFrame) -> pd.DataFrame:
    if abl_per_family_df.empty:
        return pd.DataFrame()
    sub = abl_per_family_df[
        (abl_per_family_df["experiment"] == "vendor_permissions_fused")
        & (abl_per_family_df["model"] == "random_forest")
    ].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["support"] = pd.to_numeric(sub["support"], errors="coerce").fillna(0.0)
    sub["f1_score"] = pd.to_numeric(sub["f1_score"], errors="coerce").fillna(0.0)
    total_support = float(sub["support"].sum()) or 1.0
    sub["weighted_error_contrib"] = (1.0 - sub["f1_score"]).clip(lower=0.0) * sub["support"] / total_support
    out = sub.sort_values(["weighted_error_contrib", "support"], ascending=[False, False]).head(15)
    return out[["family", "support", "f1_score", "weighted_error_contrib"]].reset_index(drop=True)


def _selected_vendor_distribution() -> pd.DataFrame:
    query = """
        SELECT
            profile_id,
            COUNT(*) AS run_count,
            AVG(selected_vendor_count) AS avg_selected_vendor_count,
            MIN(selected_vendor_count) AS min_selected_vendor_count,
            MAX(selected_vendor_count) AS max_selected_vendor_count,
            SUM(vendor_constrained_run_flag) AS constrained_run_count
        FROM analysis_run
        GROUP BY profile_id
        ORDER BY run_count DESC, profile_id
    """
    try:
        df = db_engine.execute_query(query, fetch=True, as_dataframe=True)
    except Exception:
        return pd.DataFrame()
    if df is None:
        return pd.DataFrame()
    return df


def _type_slug_baseline(snapshot_df: pd.DataFrame) -> dict[str, Any]:
    required = {"type_slug", "family_id"}
    if snapshot_df.empty or not required.issubset(snapshot_df.columns):
        return {}
    frame = snapshot_df[list(required)].dropna().copy()
    if frame.empty or frame["family_id"].nunique() < 2:
        return {}
    x = frame[["type_slug"]]
    y = frame["family_id"].astype(str)
    model = Pipeline(
        steps=[
            ("prep", ColumnTransformer([("type", OneHotEncoder(handle_unknown="ignore"), ["type_slug"])])),
            ("clf", LogisticRegression(max_iter=3000)),
        ]
    )
    model.fit(x, y)
    pred = model.predict(x)
    return {
        "samples": int(len(frame)),
        "families": int(frame["family_id"].nunique()),
        "macro_f1_train": float(f1_score(y, pred, average="macro")),
        "weighted_f1_train": float(f1_score(y, pred, average="weighted")),
    }


def _temporal_split_baseline(snapshot_df: pd.DataFrame) -> dict[str, Any]:
    required = {"type_slug", "family_id", "effective_first_seen_year"}
    if snapshot_df.empty or not required.issubset(snapshot_df.columns):
        return {}
    frame = snapshot_df[list(required)].dropna().copy()
    if frame.empty:
        return {}
    frame["effective_first_seen_year"] = pd.to_numeric(
        frame["effective_first_seen_year"], errors="coerce"
    ).astype("Int64")
    frame = frame.dropna(subset=["effective_first_seen_year"])
    if frame.empty:
        return {}

    years = sorted(int(y) for y in frame["effective_first_seen_year"].unique().tolist())
    if len(years) < 2:
        return {"note": "Insufficient year spread for early->late split."}
    split_year = years[len(years) // 2]
    train = frame[frame["effective_first_seen_year"] <= split_year]
    test = frame[frame["effective_first_seen_year"] > split_year]
    if train.empty or test.empty:
        return {"note": "Temporal split produced empty train or test set."}

    x_train = train[["type_slug"]]
    y_train = train["family_id"].astype(str)
    x_test = test[["type_slug"]]
    y_test = test["family_id"].astype(str)
    model = Pipeline(
        steps=[
            ("prep", ColumnTransformer([("type", OneHotEncoder(handle_unknown="ignore"), ["type_slug"])])),
            ("clf", LogisticRegression(max_iter=3000)),
        ]
    )
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    return {
        "split_year": split_year,
        "train_samples": int(len(train)),
        "test_samples": int(len(test)),
        "test_macro_f1": float(f1_score(y_test, pred, average="macro")),
        "test_weighted_f1": float(f1_score(y_test, pred, average="weighted")),
    }


def main() -> None:
    paths = _resolve_paths()
    diagnostics_dir = paths["run_diag"]
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    snapshot_df = _safe_read_csv(
        _pick_existing(
            paths["run_diag"] / "analysis_snapshot.latest.csv",
            paths["global_diag"] / "analysis_snapshot.latest.csv",
        )
    )
    ablation_df = _safe_read_csv(
        _pick_existing(
            paths["run_diag"] / "ablation_summary.latest.csv",
            paths["global_diag"] / "ablation_summary.latest.csv",
        )
    )
    ablation_family_df = _safe_read_csv(
        _pick_existing(
            paths["run_diag"] / "ablation_per_family.latest.csv",
            paths["global_diag"] / "ablation_per_family.latest.csv",
        )
    )
    confusion_source = _pick_existing(
        paths["run_diag"] / "confusion_within_vs_cross_type.latest.csv",
        paths["global_diag"] / "confusion_within_vs_cross_type.latest.csv",
        paths["run_bundle"] / "tables" / "confusion_within_vs_cross_type.latest.csv",
        paths["latest_bundle"] / "tables" / "confusion_within_vs_cross_type.latest.csv",
        paths["run_bundle"] / "confusion_within_vs_cross_type.latest.csv",
        paths["latest_bundle"] / "confusion_within_vs_cross_type.latest.csv",
    )
    confusion_df = _safe_read_csv(confusion_source)

    top_features_df = _load_named_importances()
    compare_df = _vendor_removed_vs_fused(ablation_df)
    family_drag_df = _family_drag(ablation_family_df)
    vendor_dist_df = _selected_vendor_distribution()
    type_baseline = _type_slug_baseline(snapshot_df)
    temporal_baseline = _temporal_split_baseline(snapshot_df)

    top_features_path = diagnostics_dir / "structural_top20_global_feature_importance.latest.csv"
    compare_path = diagnostics_dir / "structural_vendor_removed_vs_fused.latest.csv"
    family_drag_path = diagnostics_dir / "structural_family_macro_weighted_gap_drivers.latest.csv"
    vendor_dist_path = diagnostics_dir / "structural_selected_vendor_count_distribution.latest.csv"
    summary_path = diagnostics_dir / "structural_diagnostics.latest.md"

    if not top_features_df.empty:
        top_features_df.to_csv(top_features_path, index=False)
    if not compare_df.empty:
        compare_df.to_csv(compare_path, index=False)
    if not family_drag_df.empty:
        family_drag_df.to_csv(family_drag_path, index=False)
    if not vendor_dist_df.empty:
        vendor_dist_df.to_csv(vendor_dist_path, index=False)

    lines = [
            "# Structural Diagnostics (Latest)",
        "",
        "## 1) Top Global Feature Importances",
        f"- rows: {len(top_features_df)}",
        f"- file: {top_features_path.as_posix()}",
        "",
        "## 2) Importance Shift (Banker-only vs Multi-type)",
        "- status: pending dedicated paired runs + merged comparison export",
        "",
        "## 3) Vendor Features Removed",
        f"- rows: {len(compare_df)}",
        f"- file: {compare_path.as_posix()}",
        "",
        "## 4) Families Driving Macro vs Weighted Divergence",
        f"- rows: {len(family_drag_df)}",
        f"- file: {family_drag_path.as_posix()}",
        "",
        "## 5) Cross-Type Confusion Structure",
        f"- rows (summary artifact): {len(confusion_df)}",
        f"- source: {confusion_source.as_posix()}",
        "",
        "## 6) selected_vendor_count Distribution Across Runs",
        f"- rows: {len(vendor_dist_df)}",
        f"- file: {vendor_dist_path.as_posix()}",
        "",
        "## 7) type_slug-only Baseline",
        f"- result: {json.dumps(type_baseline, sort_keys=True)}",
        "",
        "## 8) Temporal Drift Baseline (Early->Late)",
        f"- result: {json.dumps(temporal_baseline, sort_keys=True)}",
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {summary_path.as_posix()}")


if __name__ == "__main__":
    main()
