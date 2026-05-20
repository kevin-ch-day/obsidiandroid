"""Derive vendor-leakage and feature-set comparison tables from ablation summaries."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh


def _find_ablation_summary_csv(diagnostics_dir: Path, run_id: str) -> Path | None:
    candidate = oh.resolve_ablation_summary_path(diagnostics_dir, run_id)
    return candidate if candidate.exists() else None


def write_signal_decomposition_artifacts(*, diagnostics_dir: Path, run_id: str) -> list[Path]:
    """Write signal decomposition CSVs beside ablation summaries."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    src = _find_ablation_summary_csv(diagnostics_dir, run_id)
    if src is None or not src.exists():
        stub = diagnostics_dir / "signal_decomposition_summary.csv"
        stub.write_text("status,notes\nstub,no_ablation_summary_found\n", encoding="utf-8")
        (diagnostics_dir / "vendor_leakage_delta.csv").write_text(
            "status,notes\nstub,no_ablation_summary_found\n", encoding="utf-8"
        )
        (diagnostics_dir / "feature_set_model_comparison.csv").write_text(
            "status,notes\nstub,no_ablation_summary_found\n", encoding="utf-8"
        )
        return [
            diagnostics_dir / "signal_decomposition_summary.csv",
            diagnostics_dir / "vendor_leakage_delta.csv",
            diagnostics_dir / "feature_set_model_comparison.csv",
        ]

    df = pd.read_csv(src)
    baseline_name = "vendor_full"
    if baseline_name not in set(df.get("experiment", pd.Series(dtype=str)).astype(str).unique()):
        if "vendor_only" in set(df["experiment"].astype(str).unique()):
            baseline_name = "vendor_only"

    out_summary = diagnostics_dir / "signal_decomposition_summary.csv"
    df.to_csv(out_summary, index=False)
    paths.append(out_summary)

    leakage_rows: list[dict[str, Any]] = []
    if "experiment" in df.columns and "model" in df.columns and "macro_f1_score" in df.columns:
        lt_values = (
            sorted(df["label_target"].dropna().unique())
            if "label_target" in df.columns
            else [None]
        )
        for lt in lt_values:
            if lt is None or "label_target" not in df.columns:
                sub = df
            else:
                sub = df[df["label_target"] == lt]
            base_block = sub[sub["experiment"] == baseline_name]
            base_map = {
                str(r["model"]): float(r["macro_f1_score"])
                for _, r in base_block.iterrows()
                if pd.notna(r.get("macro_f1_score"))
            }
            if not base_map:
                continue
            for _, row in sub.iterrows():
                experiment = str(row.get("experiment", ""))
                model = str(row.get("model", ""))
                f1 = row.get("macro_f1_score")
                if pd.isna(f1):
                    continue
                base_v = base_map.get(model)
                delta = round(float(f1) - float(base_v), 6) if base_v is not None else None
                leakage_rows.append(
                    {
                        "label_target": lt if lt is not None else "family_canonical_default",
                        "experiment": experiment,
                        "model": model,
                        "macro_f1_score": float(f1),
                        "baseline_macro_f1_vendor_full": base_v,
                        "vendor_leakage_delta_vs_vendor_full": delta,
                        "semantic_family_removed": experiment
                        in {
                            "vendor_no_parsed_family",
                            "vendor_no_family_no_type",
                            "permissions_raw",
                            "permissions_grouped",
                            "vendor_detection_binary_only",
                            "vendor_consensus_scores_only",
                        },
                    }
                )
    leak_path = diagnostics_dir / "vendor_leakage_delta.csv"
    if leakage_rows:
        keys = sorted({k for r in leakage_rows for k in r})
        with leak_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(leakage_rows)
    else:
        leak_path.write_text("status,notes\nempty,no_rows\n", encoding="utf-8")
    paths.append(leak_path)

    compare_path = diagnostics_dir / "feature_set_model_comparison.csv"
    if {"experiment", "model", "macro_f1_score"} <= set(df.columns):
        pivot_df = df.copy()
        if "label_target" in pivot_df.columns:
            pivot_df = pivot_df[pivot_df["label_target"] == "family_canonical_default"]
        wide = pivot_df.pivot_table(
            index="model",
            columns="experiment",
            values="macro_f1_score",
            aggfunc="first",
        ).reset_index()
        wide.to_csv(compare_path, index=False)
    else:
        compare_path.write_text("status,notes\nempty,unsupported_columns\n", encoding="utf-8")
    paths.append(compare_path)
    return paths
