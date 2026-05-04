"""Per-column feature survival across the training shrink chain (all modalities)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from utils import display_utils as du


def nonzero_counts_for_columns(features_df: pd.DataFrame | None) -> dict[str, int]:
    """Count rows with nonzero numeric mass per column (permission/vendor/metadata/etc.)."""
    out: dict[str, int] = {}
    if features_df is None or features_df.empty:
        return out
    for col in features_df.columns:
        name = str(col)
        if name == "sample_id":
            continue
        ser = pd.to_numeric(features_df[col], errors="coerce").fillna(0)
        try:
            out[name] = int((ser != 0).sum())
        except Exception:
            out[name] = 0
    return out


def infer_feature_modality(column_name: str, feature_attrs: dict[str, Any] | None) -> str:
    """Assign a coarse modality label for reporting."""
    c = str(column_name)
    attrs = feature_attrs or {}
    vendor_cols = list(attrs.get("vendor_feature_column_names") or [])
    if c in vendor_cols:
        return "vendor"
    if c.startswith("perm_grp__"):
        return "grouped_permission"
    if c.startswith("perm__"):
        return "permission"
    if c.startswith("meta__"):
        return "metadata"
    lower = c.lower()
    if "consensus" in lower:
        return "consensus"
    return "other"


def export_feature_column_survival_matrix(
    *,
    diagnostics_dir: Path,
    run_id: str,
    feature_attrs: dict[str, Any] | None,
    enabled: bool | None = None,
) -> Path | None:
    """Write a CSV describing each feature column's survival through pruning stages.

    Expects ``app_config`` snapshots set by ``pipeline_core.run_classifier_pipeline``:
    ``RUNTIME_FEATURE_NONZERO_*``, ``RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS``,
    ``RUNTIME_LEAKAGE_PRUNING_AUDIT``.
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_COLUMN_SURVIVAL_EXPORT", True))
    if not enabled:
        return None

    nz_cohort = getattr(app_config, "RUNTIME_FEATURE_NONZERO_COHORT_FUSED", None)
    nz_align = getattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_ALIGN", None)
    nz_fam = getattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_FAMILY_SUPPORT", None)
    nz_low = getattr(app_config, "RUNTIME_FEATURE_NONZERO_AFTER_LOW_INFORMATION", None)
    nz_final = getattr(app_config, "RUNTIME_FEATURE_NONZERO_FINAL_TRAINING", None)
    if not isinstance(nz_cohort, dict) or not nz_cohort:
        return None

    low_drop = set(
        str(x)
        for x in (getattr(app_config, "RUNTIME_LOW_INFORMATION_PRUNED_COLUMNS", None) or [])
    )
    leak_audit = getattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", None) or []
    leak_drop = {str(row.get("column_name")) for row in leak_audit if row.get("column_name")}

    universe = sorted(nz_cohort.keys())
    rows: list[dict[str, Any]] = []
    for name in universe:
        modality = infer_feature_modality(name, feature_attrs)
        n_c = int(nz_cohort.get(name, 0) or 0)
        n_a = int(nz_align.get(name, 0) or 0) if isinstance(nz_align, dict) else None
        n_f = int(nz_fam.get(name, 0) or 0) if isinstance(nz_fam, dict) else None
        n_l = int(nz_low.get(name, 0) or 0) if isinstance(nz_low, dict) else None
        n_fin = int(nz_final.get(name, 0) or 0) if isinstance(nz_final, dict) else None
        d_low = name in low_drop
        d_leak = name in leak_drop
        in_final = isinstance(nz_final, dict) and name in nz_final
        retained = bool(in_final)
        rows.append(
            {
                "feature_name": name,
                "modality": modality,
                "present_in_cohort_fused_matrix": True,
                "nonzero_count_cohort_fused": n_c,
                "nonzero_count_after_align": n_a,
                "nonzero_count_after_family_support": n_f,
                "nonzero_count_after_low_information_prune": n_l if not d_low else None,
                "dropped_by_low_information_prune": d_low,
                "dropped_by_leakage_prune": d_leak,
                "retained_for_training": retained,
                "nonzero_count_final_training": n_fin if retained else None,
            }
        )

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    out = diagnostics_dir / f"feature_column_survival_{run_id}.csv"
    latest = diagnostics_dir / "feature_column_survival.latest.csv"
    df.to_csv(out, index=False)
    df.to_csv(latest, index=False)
    meta = {
        "run_id": str(run_id),
        "row_count": int(len(df)),
        "artifact_csv": str(out),
    }
    meta_path = diagnostics_dir / f"feature_column_survival_{run_id}.meta.json"
    meta_latest = diagnostics_dir / "feature_column_survival.latest.meta.json"
    js = json.dumps(meta, indent=2, sort_keys=True) + "\n"
    meta_path.write_text(js, encoding="utf-8")
    meta_latest.write_text(js, encoding="utf-8")
    setattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", str(out))
    du.print_info(f"[FEATURE_SURVIVAL] Wrote {len(df)} feature column row(s) → {latest}")
    return latest


__all__ = [
    "export_feature_column_survival_matrix",
    "infer_feature_modality",
    "nonzero_counts_for_columns",
]
