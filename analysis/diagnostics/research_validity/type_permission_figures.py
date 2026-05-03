"""Figures tying malware type to coarse permission summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def write_type_permission_figure_bundle(
    *,
    diagnostics_dir: Path,
    samples_df: pd.DataFrame | None,
    artifact_list: list[str],
) -> None:
    """Dangerous burden + grouped-permission heatmap + optional JSD family similarity."""
    if samples_df is None or samples_df.empty:
        return
    if "type_slug" not in samples_df.columns:
        return
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        from analysis.pipeline.stage_feature_enrichment import build_permission_enrichment_frame

        frame = build_permission_enrichment_frame(
            samples_df,
            feature_flags={"enable_permission_features": True},
        )
    except Exception:
        return
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return

    merged = samples_df[["sample_id", "type_slug"]].merge(frame, on="sample_id", how="inner")
    grp_cols = [c for c in merged.columns if str(c).startswith("perm_grp__")]
    total = pd.to_numeric(merged.get("perm__total_count", 1), errors="coerce").fillna(1).clip(lower=1)

    if grp_cols:
        norm = merged[grp_cols].div(total, axis=0)
        heat = norm.groupby(merged["type_slug"])[grp_cols].mean()
        fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(heat))), dpi=140)
        im = ax.imshow(heat.values, aspect="auto", cmap="magma")
        ax.set_yticks(range(len(heat.index)))
        ax.set_yticklabels(list(heat.index), fontsize=8)
        ax.set_xticks(range(len(grp_cols)))
        ax.set_xticklabels(grp_cols, rotation=45, ha="right", fontsize=7)
        ax.set_title("Grouped permissions (mean normalized burden) by malware type")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        out = diagnostics_dir / "grouped_permission_heatmap_by_type.png"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        _maybe_append(artifact_list, out)

    danger = pd.to_numeric(merged.get("perm__dangerous_count", 0), errors="coerce").fillna(0)
    burden = danger / total
    summary = burden.groupby(merged["type_slug"]).mean().reset_index()
    summary.columns = ["type_slug", "mean_norm_dangerous"]
    fig2, ax2 = plt.subplots(figsize=(9, max(3.5, 0.28 * len(summary))), dpi=140)
    ax2.barh(summary["type_slug"], summary["mean_norm_dangerous"], color="#dd8452")
    ax2.set_xlabel("Mean dangerous permission burden (normalized by declared permission count)")
    ax2.set_title("Dangerous permission burden by malware type")
    fig2.tight_layout()
    out2 = diagnostics_dir / "dangerous_permission_burden_by_type.png"
    fig2.savefig(out2, bbox_inches="tight")
    plt.close(fig2)
    _maybe_append(artifact_list, out2)

    if "family_canonical" not in samples_df.columns:
        return
    fam_frame = samples_df[["sample_id", "family_canonical"]].merge(frame, on="sample_id", how="inner")
    bow_cols = [
        c
        for c in fam_frame.columns
        if str(c).startswith("perm__")
        and not str(c).startswith("perm_grp__")
        and c
        not in {
            "perm__dangerous_count",
            "perm__normal_count",
            "perm__oem_count",
            "perm__total_count",
        }
    ]
    if len(bow_cols) < 4:
        return

    wide = fam_frame.groupby("family_canonical")[bow_cols].mean()
    fams = list(wide.index)

    try:
        import numpy as np
        from scipy.spatial.distance import jensenshannon

        mat = np.zeros((len(fams), len(fams)))
        for i, fam_a in enumerate(fams):
            probs_a = wide.loc[fam_a].values.astype(float)
            probs_a = probs_a / max(probs_a.sum(), 1e-9)
            for j, fam_b in enumerate(fams):
                probs_b = wide.loc[fam_b].values.astype(float)
                probs_b = probs_b / max(probs_b.sum(), 1e-9)
                mat[i, j] = float(jensenshannon(probs_a, probs_b))

        fig3, ax3 = plt.subplots(figsize=(12, 10), dpi=140)
        ax3.imshow(mat, cmap="viridis")
        ax3.set_xticks(range(len(fams)))
        ax3.set_yticks(range(len(fams)))
        ax3.set_xticklabels(fams, rotation=90, fontsize=6)
        ax3.set_yticklabels(fams, fontsize=6)
        ax3.set_title("Clustered-style JSD heatmap — permission prevalence by family")
        fig3.tight_layout()
        out3 = diagnostics_dir / "permission_jsd_clustered_heatmap.png"
        fig3.savefig(out3, bbox_inches="tight")
        plt.close(fig3)
        _maybe_append(artifact_list, out3)

        flat: list[tuple[float, str, str]] = []
        for i, fam_a in enumerate(fams):
            for j, fam_b in enumerate(fams):
                if i >= j:
                    continue
                flat.append((mat[i, j], fam_a, fam_b))
        flat.sort(key=lambda item: item[0])
        table_path = diagnostics_dir / "closest_family_pairs_jsd_permission.csv"
        pd.DataFrame(
            [{"distance": d, "family_a": a, "family_b": b} for d, a, b in flat[:60]],
            columns=["distance", "family_a", "family_b"],
        ).to_csv(table_path, index=False)
        _maybe_append(artifact_list, table_path)
    except Exception:
        return


def _maybe_append(artifact_list: list[str], path: Path) -> None:
    sp = str(path)
    if sp not in artifact_list:
        artifact_list.append(sp)


__all__ = ["write_type_permission_figure_bundle"]
