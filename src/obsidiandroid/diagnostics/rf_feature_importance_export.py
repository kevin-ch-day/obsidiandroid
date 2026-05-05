"""Export RandomForest Gini impurity importances as a modality-tagged run diagnostic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.cli.ui import display as du


def _infer_modality(feature_name: str) -> str:
    """Coarse modality bucket from column naming (fallback when attrs are unavailable)."""
    n = str(feature_name).strip().lower()
    if not n:
        return "unknown"
    if n.startswith("android.permission.") or "permission_" in n or "_perm_" in n:
        return "permission"
    if n.startswith("dangerous_count") or n.startswith("normal_count") or n.startswith("total_count"):
        return "permission_count"
    if n.startswith("malware_type_") or n.startswith("parsed_family_") or "threat_class" in n:
        return "vendor_parsed_label"
    if "engine" in n or "detect" in n or "consensus" in n or "_av_" in n:
        return "av_detection_geometry"
    if n in {"sample_weight", "row_weight"}:
        return "weighting"
    return "other"


def export_rf_impurity_importances_csv(
    *,
    model: Any,
    feature_names: list[str],
    diagnostics_dir: Path,
    run_id: str,
    top_k: int = 50,
    modality_hints: dict[str, str] | None = None,
) -> Path | None:
    """Persist top impurity-based importances for a fitted sklearn RF."""
    feats = getattr(model, "feature_importances_", None)
    if feats is None or len(feats) == 0:
        return None
    if len(feature_names) != len(feats):
        du.print_warning(
            "[RF_IMPORTANCE] feature name count mismatches feature_importances_; skipped export."
        )
        return None

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    hints = modality_hints if isinstance(modality_hints, dict) else {}
    rows: list[dict[str, Any]] = []
    for name, score in zip(feature_names, feats, strict=True):
        mod = hints.get(str(name), _infer_modality(str(name)))
        rows.append(
            {
                "feature_name": str(name),
                "modality_guess": mod,
                "impurity_importance": float(score),
            }
        )
    frame = pd.DataFrame(rows).sort_values("impurity_importance", ascending=False).reset_index(drop=True)
    frame["rank"] = range(1, len(frame) + 1)
    out = diagnostics_dir / f"rf_impurity_importance_{run_id}.csv"
    frame.head(int(top_k)).to_csv(out, index=False)
    latest = diagnostics_dir / "rf_impurity_importance.latest.csv"
    frame.head(int(top_k)).to_csv(latest, index=False)
    du.print_debug(f"[ARTIFACT] RF impurity importance (top {top_k}): {out}")
    return out
