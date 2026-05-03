"""Matplotlib figures answering research-validity questions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _pyplot():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def write_validity_figures(
    *,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
) -> list[Path]:
    """Best-effort PNG exports (skip silently when inputs missing)."""
    plt = _pyplot()
    out: list[Path] = []

    comp = diagnostics_dir / "feature_set_macro_f1_comparison.png"
    leak = diagnostics_dir / "vendor_leakage_delta.png"
    perm_hm = diagnostics_dir / "grouped_permission_heatmap_by_type.png"
    jsd_hm = diagnostics_dir / "permission_jsd_clustered_heatmap.png"

    sum_path = diagnostics_dir / "signal_decomposition_summary.csv"
    leak_path = diagnostics_dir / "vendor_leakage_delta.csv"
    audit_path = diagnostics_dir / "permission_feature_audit.csv"

    # Macro-F1 comparison (default label target only).
    try:
        if sum_path.exists():
            df = pd.read_csv(sum_path)
            if {"experiment", "macro_f1_score"} <= set(df.columns):
                if "label_target" in df.columns:
                    df = df[df["label_target"] == "family_canonical_default"]
                agg = (
                    df.groupby("experiment", dropna=False)["macro_f1_score"].mean().sort_values(ascending=True)
                )
                fig, ax = plt.subplots(figsize=(9, max(3.6, 0.33 * len(agg))), dpi=140)
                ax.barh(list(agg.index), list(agg.values), color="#377eb8")
                ax.set_title("Mean Macro-F1 by feature set")
                ax.set_xlabel("Macro-F1 (mean across models)")
                fig.tight_layout()
                fig.savefig(comp, bbox_inches="tight")
                plt.close(fig)
                out.append(comp)
    except Exception:
        if comp.exists():
            comp.unlink(missing_ok=True)

    try:
        if leak_path.exists():
            dfl = pd.read_csv(leak_path)
            cols = {"experiment", "vendor_leakage_delta_vs_vendor_full"}
            alt = cols - set(dfl.columns)
            use_col = (
                "vendor_leakage_delta_vs_vendor_full"
                if "vendor_leakage_delta_vs_vendor_full" in dfl.columns
                else "leakage_sensitivity_delta"
            )
            if use_col in dfl.columns and "experiment" in dfl.columns:
                if "label_target" in dfl.columns:
                    dfl = dfl[dfl["label_target"] == "family_canonical_default"]
                agg = (
                    dfl.groupby("experiment", dropna=False)[use_col]
                    .mean()
                    .dropna()
                    .sort_values(ascending=True)
                )
                if not agg.empty:
                    fig2, ax2 = plt.subplots(figsize=(9, max(3.6, 0.33 * len(agg))), dpi=140)
                    ax2.barh(list(agg.index), list(agg.values), color="#e41a1c")
                    ax2.axvline(0, color="#333333", linewidth=1)
                    ax2.set_title("Vendor leakage Δ vs vendor_full (Macro-F1)")
                    ax2.set_xlabel("Δ Macro-F1")
                    fig2.tight_layout()
                    fig2.savefig(leak, bbox_inches="tight")
                    plt.close(fig2)
                    out.append(leak)
    except Exception:
        if leak.exists():
            leak.unlink(missing_ok=True)

    # Grouped-permission prevalence heatmap synthetic from audit + cohort is expensive;
    # require permission_feature_audit + samples—placeholder skipped when insufficient.
    try:
        if audit_path.exists() and isinstance(manifest_context.get("samples_path_hint"), str):
            _ = audit_path.read_text(encoding="utf-8")
    except Exception:
        pass

    return out


__all__ = ["write_validity_figures"]
