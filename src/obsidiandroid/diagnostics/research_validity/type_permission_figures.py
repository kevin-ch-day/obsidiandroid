"""Figures tying malware type to coarse permission summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json

import pandas as pd

from config import app_config


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
            log_frame_built=False,
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

        from analysis.pipeline.permission_trends.stats_core import js_distance

        mat = np.zeros((len(fams), len(fams)))
        skipped_pairs = 0

        def _safe_prob(vec: Any) -> Any:
            v = np.asarray(vec, dtype=float)
            v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
            s = float(v.sum())
            if s <= 0.0:
                return None
            return v / s

        for i, fam_a in enumerate(fams):
            probs_a = _safe_prob(wide.loc[fam_a].values)
            for j, fam_b in enumerate(fams):
                probs_b = _safe_prob(wide.loc[fam_b].values)
                if probs_a is None or probs_b is None:
                    mat[i, j] = np.nan
                    if i < j:
                        skipped_pairs += 1
                    continue
                pa = np.asarray(probs_a, dtype=float)
                pb = np.asarray(probs_b, dtype=float)
                mat[i, j] = float(js_distance(pa, pb))
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
        if skipped_pairs and diagnostics_dir:
            p = diagnostics_dir / "permission_jsd_skipped_degenerate_pairs.count.txt"
            p.write_text(str(skipped_pairs), encoding="utf-8")
            artifact_list.append(str(p))
        if diagnostics_dir:
            diag = {
                "run_id": run_id,
                "skipped_degenerate_pair_count": int(skipped_pairs),
                "reason": "zero_sum_or_invalid_probability_vector",
                "family_vector_count": int(len(fams)),
            }
            dj = diagnostics_dir / f"permission_jsd_degenerate_diagnostics_{run_id}.json"
            djl = diagnostics_dir / "permission_jsd_degenerate_diagnostics.latest.json"
            js_payload = json.dumps(diag, indent=2, sort_keys=True) + "\n"
            dj.write_text(js_payload, encoding="utf-8")
            djl.write_text(js_payload, encoding="utf-8")
            artifact_list.append(str(djl))
        max_skips = int(
            getattr(app_config, "PERMISSION_JSD_DEGENERATE_EVIDENCE_MAX_SKIPS", 10**9) or 10**9
        )
        if (
            skipped_pairs > max_skips
            and bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
        ):
            raise RuntimeError(
                "[JSD] Degenerate permission probability vectors: "
                f"skipped_pair_count={skipped_pairs} exceeds evidence threshold={max_skips}. "
                "See permission_jsd_degenerate_diagnostics JSON in diagnostics."
            )

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
