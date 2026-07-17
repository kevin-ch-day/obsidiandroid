"""Higher-level statistical report builders for permission trends.

Pure helper layer: dataframe transforms and statistical test summaries only.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.pipeline.permission_trends.stats_core import bh_fdr, cliffs_delta


def build_sample_level_permission_metrics(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
) -> pd.DataFrame:
    if permission_rows_df.empty:
        return sample_core_df[["sample_id"]].assign(
            permission_entropy=0.0,
            dangerous_count_strict=0,
            dangerous_count_inclusive=0,
        )
    work = permission_rows_df.copy()
    work["bucket"] = np.where(
        work["protection_level"].str.contains("DANGEROUS", regex=False),
        "dangerous",
        np.where(work["protection_level"].str.contains("NORMAL", regex=False), "normal", "unknown"),
    )
    counts = work.groupby(["sample_id", "bucket"])["permission_string"].count().unstack(fill_value=0)
    for bucket in ("dangerous", "normal", "unknown"):
        if bucket not in counts.columns:
            counts[bucket] = 0
    counts = counts[["dangerous", "normal", "unknown"]].astype(float)
    totals = counts.sum(axis=1)
    probabilities = counts.div(totals.replace(0.0, np.nan), axis=0)
    positive_probabilities = probabilities.where(probabilities > 0.0)
    entropy = -(positive_probabilities * np.log(positive_probabilities)).sum(axis=1, skipna=True)
    out = pd.DataFrame(
        {
            "sample_id": counts.index.astype(int),
            "permission_entropy": entropy.fillna(0.0).astype(float),
            "dangerous_count_strict": counts["dangerous"].astype(int),
            "dangerous_count_inclusive": (counts["dangerous"] + counts["unknown"]).astype(int),
        }
    ).reset_index(drop=True)
    return sample_core_df[["sample_id"]].merge(out, on="sample_id", how="left").fillna(0)


def build_consensus_correlation_report(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
    *,
    spearman_with_bootstrap_ci: Callable[[pd.Series, pd.Series], tuple[float, float, float, float]],
) -> tuple[pd.DataFrame, str]:
    metrics_df = build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = safe_int_config_value(
        getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5),
        default=5,
    )
    consensus_keep = consensus_df[consensus_df["vendor_count"] >= min_vendor_count][["sample_id", "consensus_score_all_vendors"]].copy()
    merged = metrics_df.merge(consensus_keep, on="sample_id", how="inner")
    if merged.empty:
        out = pd.DataFrame([
            {"run_id": run_id, "metric_x": "consensus_score_all_vendors", "metric_y": "permission_entropy", "spearman_rho": 0.0, "p_value": np.nan, "ci_low": np.nan, "ci_high": np.nan, "n_samples": 0}
        ])
        return out, "No valid samples after consensus vendor-count filtering; association analysis not computed.\n"
    rows: list[dict[str, Any]] = []
    checks = [("permission_entropy", "consensus vs permission entropy"), ("dangerous_count_strict", "consensus vs dangerous_count_strict"), ("dangerous_count_inclusive", "consensus vs dangerous_count_inclusive")]
    lines = [f"Run ID: {run_id}", "Association analysis only (not causation).", ""]
    for metric, label in checks:
        x = pd.to_numeric(merged["consensus_score_all_vendors"], errors="coerce")
        y = pd.to_numeric(merged[metric], errors="coerce")
        rho, p_value, ci_low, ci_high = spearman_with_bootstrap_ci(x, y)
        n = int(pd.concat([x, y], axis=1).dropna().shape[0])
        rows.append({"run_id": run_id, "metric_x": "consensus_score_all_vendors", "metric_y": metric, "spearman_rho": round(rho, 6), "p_value": p_value, "ci_low": round(ci_low, 6), "ci_high": round(ci_high, 6), "n_samples": n})
        lines.append(f"- {label}: rho={rho:.4f}, 95% bootstrap CI=[{ci_low:.4f}, {ci_high:.4f}], p={p_value:.3e}, n={n}")
    return pd.DataFrame(rows), "\n".join(lines) + "\n"


def build_permission_discriminability_rank(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    if not permission_cols:
        return pd.DataFrame()
    label = merged["type_slug"].astype(str)
    rows: list[dict[str, Any]] = []
    for permission in permission_cols:
        present = pd.to_numeric(merged[permission], errors="coerce").fillna(0).astype(int)
        p_value, cramers_v = chi2_presence_vs_multiclass(label, present)
        rows.append({"run_id": run_id, "permission": permission, "chi2_p_value": p_value, "cramers_v": cramers_v, "global_support": int(present.sum())})
    out = pd.DataFrame(rows)
    out["chi2_p_value_fdr_bh"] = bh_fdr(out["chi2_p_value"].tolist())
    out["mutual_information"] = mutual_information_scores(label, merged[permission_cols])
    return out.sort_values(["cramers_v", "mutual_information"], ascending=[False, False]).reset_index(drop=True)


def chi2_presence_vs_multiclass(label: pd.Series, present: pd.Series) -> tuple[float, float]:
    table = pd.crosstab(label, present)
    if table.empty or table.shape[0] < 2 or table.shape[1] < 2:
        return 1.0, 0.0
    try:
        from scipy.stats import chi2_contingency

        chi2, p_value, _, _ = chi2_contingency(table.values, correction=False)
    except Exception:
        return 1.0, 0.0
    n = float(table.values.sum())
    k = min(table.shape[0] - 1, table.shape[1] - 1)
    if n <= 0 or k <= 0:
        return float(p_value), 0.0
    return float(p_value), float(np.sqrt(max(chi2, 0.0) / (n * k)))


def mutual_information_scores(label: pd.Series, features_df: pd.DataFrame) -> list[float]:
    try:
        from sklearn.feature_selection import mutual_info_classif
        from sklearn.preprocessing import LabelEncoder

        y = LabelEncoder().fit_transform(label.astype(str))
        scores = mutual_info_classif(features_df.astype(int).values, y, discrete_features=True, random_state=42)
        return [round(float(s), 6) for s in scores]
    except Exception:
        return [0.0 for _ in range(features_df.shape[1])]


def build_dangerous_stats_tests(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    metrics_df = build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    frame = sample_core_df[["sample_id", "type_slug"]].merge(metrics_df, on="sample_id", how="left").fillna(0)
    metric = "dangerous_count_strict"
    groups = {str(k): pd.to_numeric(g[metric], errors="coerce").dropna().astype(float) for k, g in frame.groupby("type_slug", dropna=False)}
    group_values = [vals.values for vals in groups.values() if len(vals) > 0]
    kw_stat = np.nan
    kw_p = np.nan
    if len(group_values) >= 2:
        try:
            from scipy.stats import kruskal

            kw = kruskal(*group_values)
            kw_stat, kw_p = float(kw.statistic), float(kw.pvalue)
        except Exception:
            pass
    rows: list[dict[str, Any]] = [{"run_id": run_id, "test_type": "kruskal_wallis", "metric": metric, "group_a": "all", "group_b": "all", "statistic": kw_stat, "p_value": kw_p, "p_value_fdr_bh": kw_p, "effect_size": np.nan, "effect_size_name": "epsilon_squared", "method_notes": "global_nonparametric"}]
    pair_rows = build_pairwise_dunn_or_mannwhitney(frame=frame, metric=metric, run_id=run_id, groups=groups)
    if pair_rows:
        rows.extend(pair_rows)
    return pd.DataFrame(rows)


def build_pairwise_dunn_or_mannwhitney(frame: pd.DataFrame, metric: str, run_id: str, groups: dict[str, pd.Series]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        import scikit_posthocs as sp

        dunn_matrix = sp.posthoc_dunn(frame[[metric, "type_slug"]].rename(columns={metric: "value", "type_slug": "group"}), val_col="value", group_col="group", p_adjust="fdr_bh")
        keys = sorted(groups.keys())
        for i, left in enumerate(keys):
            for right in keys[i + 1 :]:
                p_value = float(dunn_matrix.loc[left, right]) if left in dunn_matrix.index and right in dunn_matrix.columns else np.nan
                rows.append({"run_id": run_id, "test_type": "pairwise_dunn", "metric": metric, "group_a": left, "group_b": right, "statistic": np.nan, "p_value": p_value, "p_value_fdr_bh": p_value, "effect_size": round(cliffs_delta(groups[left], groups[right]), 6), "effect_size_name": "cliffs_delta", "method_notes": "dunn_with_bh_fdr"})
        return rows
    except Exception:
        pass

    keys = sorted(groups.keys())
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            a = groups[left]
            b = groups[right]
            if a.empty or b.empty:
                continue
            p_value = np.nan
            stat = np.nan
            try:
                from scipy.stats import mannwhitneyu

                res = mannwhitneyu(a.values, b.values, alternative="two-sided")
                stat, p_value = float(res.statistic), float(res.pvalue)
            except Exception:
                pass
            rows.append({"run_id": run_id, "test_type": "pairwise_mannwhitney", "metric": metric, "group_a": left, "group_b": right, "statistic": stat, "p_value": p_value, "effect_size": round(cliffs_delta(a, b), 6), "effect_size_name": "cliffs_delta", "method_notes": "pairwise_nonparametric_fallback_for_dunn"})
    if not rows:
        return rows
    pair_df = pd.DataFrame(rows)
    pair_df["p_value_fdr_bh"] = bh_fdr(pair_df["p_value"].fillna(1.0).astype(float).tolist())
    return pair_df.to_dict(orient="records")
