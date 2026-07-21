"""Advanced quantitative diagnostics for ML data problems."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _round_finite(value: Any, digits: int = 6, default: float = 0.0) -> float:
    parsed = _safe_float(value, None)
    if parsed is None or not math.isfinite(parsed):
        return default
    return round(float(parsed), digits)


def _distribution_metrics(counts: list[int]) -> dict[str, Any]:
    counts = [int(x) for x in counts if int(x) > 0]
    total = int(sum(counts))
    n = int(len(counts))
    if total <= 0 or n <= 0:
        return {
            "total": 0,
            "classes": 0,
            "entropy_bits": 0.0,
            "entropy_gap_bits": 0.0,
            "normalized_entropy": 0.0,
            "kl_to_uniform_bits": 0.0,
            "hhi": 0.0,
            "simpson_diversity": 0.0,
            "effective_class_count_entropy": 0.0,
            "effective_class_count_hhi": 0.0,
            "gini": 0.0,
            "theil_t": 0.0,
            "atkinson_0_5": 0.0,
            "bottom20_share": 0.0,
            "bottom50_share": 0.0,
            "top1_share": 0.0,
            "top3_share": 0.0,
            "top5_share": 0.0,
            "top10pct_share": 0.0,
            "palma_ratio": 0.0,
            "imbalance_ratio_max_min": 0.0,
            "hhi_marginal_relief_smallest_plus_one": 0.0,
            "hhi_marginal_damage_largest_plus_one": 0.0,
        }
    shares = [x / total for x in counts]
    entropy_bits = -sum(p * math.log(p, 2) for p in shares if p > 0)
    max_entropy_bits = math.log(n, 2) if n > 1 else 0.0
    entropy_gap_bits = max_entropy_bits - entropy_bits
    normalized_entropy = entropy_bits / math.log(n, 2) if n > 1 else 1.0
    hhi = sum(p * p for p in shares)
    sorted_counts = sorted(counts, reverse=True)
    sorted_asc = sorted(counts)
    gini_num = sum((2 * idx - n - 1) * val for idx, val in enumerate(sorted_asc, start=1))
    gini = gini_num / (n * total) if total else 0.0
    mean_count = total / n
    theil_t = sum((x / total) * math.log(x / mean_count) for x in counts if x > 0 and mean_count > 0)
    atkinson_0_5 = 1.0 - ((sum(math.sqrt(x) for x in counts) / n) ** 2 / mean_count)

    def top_share(k: int) -> float:
        return sum(sorted_counts[: min(k, n)]) / total

    def bottom_share(k: int) -> float:
        return sum(sorted_asc[: min(k, n)]) / total

    bottom40 = bottom_share(max(1, math.ceil(n * 0.40)))
    top10 = top_share(max(1, math.ceil(n * 0.10)))

    def hhi_after_add(index: int) -> float:
        changed = list(counts)
        changed[index] += 1
        new_total = total + 1
        return sum((x / new_total) ** 2 for x in changed)

    smallest_idx = counts.index(min(counts))
    largest_idx = counts.index(max(counts))

    return {
        "total": total,
        "classes": n,
        "entropy_bits": round(entropy_bits, 6),
        "entropy_gap_bits": round(entropy_gap_bits, 6),
        "normalized_entropy": round(normalized_entropy, 6),
        "kl_to_uniform_bits": round(entropy_gap_bits, 6),
        "hhi": round(hhi, 6),
        "simpson_diversity": round(1.0 - hhi, 6),
        "effective_class_count_entropy": round(2 ** entropy_bits, 6),
        "effective_class_count_hhi": round((1.0 / hhi) if hhi > 0 else 0.0, 6),
        "gini": round(float(gini), 6),
        "theil_t": round(float(theil_t), 6),
        "theil_t_normalized": round(float(theil_t / math.log(n)) if n > 1 else 0.0, 6),
        "atkinson_0_5": round(float(atkinson_0_5), 6),
        "bottom20_share": round(bottom_share(max(1, math.ceil(n * 0.20))), 6),
        "bottom50_share": round(bottom_share(max(1, math.ceil(n * 0.50))), 6),
        "top1_share": round(top_share(1), 6),
        "top3_share": round(top_share(3), 6),
        "top5_share": round(top_share(5), 6),
        "top10pct_share": round(top10, 6),
        "palma_ratio": round((top10 / bottom40) if bottom40 > 0 else 0.0, 6),
        "imbalance_ratio_max_min": round(max(counts) / max(min(counts), 1), 6),
        "hhi_marginal_relief_smallest_plus_one": round(hhi - hhi_after_add(smallest_idx), 9),
        "hhi_marginal_damage_largest_plus_one": round(hhi_after_add(largest_idx) - hhi, 9),
    }


def _family_distribution(diagnostics_dir: Path, run_id: str = "") -> pd.DataFrame:
    df = _read_csv(diagnostics_dir / "family_distribution.csv")
    if df.empty and run_id:
        labels = _read_csv(diagnostics_dir / f"aligned_labels_{run_id}.csv")
        if not labels.empty and "family_canonical" in labels.columns:
            df = (
                labels["family_canonical"]
                .fillna("")
                .astype(str)
                .str.strip()
                .loc[lambda s: s.ne("")]
                .value_counts()
                .rename_axis("family")
                .reset_index(name="sample_count")
            )
    if df.empty:
        for path in sorted(diagnostics_dir.glob("aligned_labels_*.csv")):
            labels = _read_csv(path)
            if not labels.empty and "family_canonical" in labels.columns:
                df = (
                    labels["family_canonical"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s.ne("")]
                    .value_counts()
                    .rename_axis("family")
                    .reset_index(name="sample_count")
                )
                break
    if df.empty:
        return pd.DataFrame(columns=["family", "sample_count"])
    if "sample_count" not in df.columns:
        count_col = next((c for c in df.columns if "count" in str(c).lower()), "")
        if count_col:
            df = df.rename(columns={count_col: "sample_count"})
    if "family" not in df.columns:
        family_col = next((c for c in df.columns if "family" in str(c).lower()), "")
        if family_col:
            df = df.rename(columns={family_col: "family"})
    if "sample_count" in df.columns:
        df["sample_count"] = pd.to_numeric(df["sample_count"], errors="coerce").fillna(0).astype(int)
    return df


def _support_performance_metrics(diagnostics_dir: Path) -> dict[str, Any]:
    df = _read_csv(diagnostics_dir / "family_support_vs_performance.csv")
    if df.empty:
        df = _read_csv(diagnostics_dir / "family_precision_recall.csv")
    if df.empty or "support" not in df.columns:
        return {}
    work = df.copy()
    work["support"] = pd.to_numeric(work["support"], errors="coerce").fillna(0)
    for col in ("recall", "precision", "f1_score"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    stable = work[work["support"] > 0].copy()
    out: dict[str, Any] = {
        "families_evaluated": int(len(work)),
        "zero_support_metric_rows": int((work["support"] <= 0).sum()),
        "positive_support_rows": int(len(stable)),
    }
    if stable.empty:
        return out
    if "recall" in stable.columns:
        out["zero_recall_positive_support_rows"] = int((stable["recall"].fillna(0) <= 0).sum())
        out["mean_recall_positive_support"] = round(float(stable["recall"].mean()), 6)
        if stable["support"].nunique() > 1 and stable["recall"].nunique() > 1:
            out["support_recall_corr_spearman"] = _round_finite(
                stable[["support", "recall"]].corr(method="spearman").iloc[0, 1]
            )
    if "f1_score" in stable.columns:
        out["mean_f1_positive_support"] = round(float(stable["f1_score"].mean()), 6)
        if stable["support"].nunique() > 1 and stable["f1_score"].nunique() > 1:
            out["support_f1_corr_spearman"] = _round_finite(
                stable[["support", "f1_score"]].corr(method="spearman").iloc[0, 1]
            )
    return out


def _support_gap_metrics(diagnostics_dir: Path, run_id: str, min_support: int = 20) -> dict[str, Any]:
    """Trainability-gap metrics against an explicit distribution surface.

    Prefer the full aligned prepared cohort (``aligned_labels_*.csv``) so the
    n>=20 gap is not silently empty when ``family_distribution.csv`` already
    reflects a post-support / trainable subset.
    """
    distribution_source = "family_distribution.csv"
    fam_df = pd.DataFrame(columns=["family", "sample_count"])
    if run_id:
        labels = _read_csv(diagnostics_dir / f"aligned_labels_{run_id}.csv")
        if not labels.empty and "family_canonical" in labels.columns:
            fam_df = (
                labels["family_canonical"]
                .fillna("")
                .astype(str)
                .str.strip()
                .loc[lambda s: s.ne("") & s.str.lower().ne("unknown")]
                .value_counts()
                .rename_axis("family")
                .reset_index(name="sample_count")
            )
            distribution_source = f"aligned_labels_{run_id}.csv"
    if fam_df.empty:
        fam_df = _family_distribution(diagnostics_dir, run_id)
        distribution_source = "family_distribution.csv"
    if fam_df.empty or "sample_count" not in fam_df.columns:
        return {}
    work = fam_df.copy()
    work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
    tail = work[(work["sample_count"] > 0) & (work["sample_count"] < min_support)].copy()
    out: dict[str, Any] = {
        "min_support": min_support,
        "trainability_threshold": min_support,
        "distribution_source": distribution_source,
        "below_support_family_count": int(len(tail)),
        "below_support_sample_count": int(tail["sample_count"].sum()) if not tail.empty else 0,
    }
    low_support_path = diagnostics_dir / "low_support_families.csv"
    if low_support_path.is_file():
        low_df = _read_csv(low_support_path)
        out["pretraining_families_below_runtime_min_support"] = int(len(low_df)) if not low_df.empty else 0
        out["pretraining_low_support_source"] = "low_support_families.csv"
    if tail.empty:
        out.update(
            {
                "samples_needed_to_make_all_families_trainable": 0,
                "families_with_gap_le_3": 0,
                "families_with_gap_le_5": 0,
                "families_with_gap_le_10": 0,
                "top_support_gap_family": "",
                "top_support_gap_needed": 0,
                "fastest_trainability_lift": [],
            }
        )
        return out
    tail["samples_needed"] = min_support - tail["sample_count"]
    tail["roi_family_per_added_sample"] = 1.0 / tail["samples_needed"].clip(lower=1)
    ordered = tail.sort_values(["samples_needed", "sample_count", "family"], ascending=[True, False, True])
    out.update(
        {
            "samples_needed_to_make_all_families_trainable": int(tail["samples_needed"].sum()),
            "families_with_gap_le_3": int((tail["samples_needed"] <= 3).sum()),
            "families_with_gap_le_5": int((tail["samples_needed"] <= 5).sum()),
            "families_with_gap_le_10": int((tail["samples_needed"] <= 10).sum()),
            "top_support_gap_family": str(ordered.iloc[0].get("family", "")),
            "top_support_gap_needed": int(ordered.iloc[0].get("samples_needed", 0) or 0),
            "fastest_trainability_lift": [
                {
                    "family": str(row.get("family", "")),
                    "current_support": int(row.get("sample_count", 0) or 0),
                    "samples_needed": int(row.get("samples_needed", 0) or 0),
                    "roi_family_per_added_sample": round(float(row.get("roi_family_per_added_sample", 0.0) or 0.0), 6),
                }
                for row in ordered.head(8).to_dict("records")
            ],
        }
    )
    return out


def _support_threshold_curve_from_counts(
    counts_raw: list[int],
    thresholds: tuple[int, ...] = (1, 2, 3, 5, 10, 15, 18, 20, 25, 30),
) -> dict[str, Any]:
    counts = pd.Series([int(value) for value in counts_raw if int(value) > 0], dtype="int64")
    total = int(counts.sum()) if not counts.empty else 0
    if total <= 0:
        return {}
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        kept = counts[counts >= threshold]
        kept_rows = int(kept.sum())
        dropped_rows = int(total - kept_rows)
        rows.append(
            {
                "threshold": int(threshold),
                "trainable_classes": int((counts >= threshold).sum()),
                "retained_rows": kept_rows,
                "dropped_rows": dropped_rows,
                "retained_share": round(kept_rows / total, 6),
                "dropped_share": round(dropped_rows / total, 6),
            }
        )

    def row_for(threshold: int) -> dict[str, Any]:
        return next((row for row in rows if row["threshold"] == threshold), {})

    baseline20 = row_for(20)
    alternatives = [
        row
        for row in rows
        if row["threshold"] < 20
        and row["threshold"] >= 10
        and row["retained_share"] >= 0.90
        and row["trainable_classes"] > int(baseline20.get("trainable_classes", 0) or 0)
    ]
    recommended = max(
        alternatives,
        key=lambda row: (
            row["trainable_classes"],
            row["threshold"],
            row["retained_share"],
        ),
        default={},
    )
    return {
        "curve": rows,
        "threshold_20": baseline20,
        "recommended_exploratory_threshold": recommended,
        "dual_track_recommended": bool(recommended),
        "dual_track_reason": (
            "Use threshold 20 for conservative evidence claims; run an exploratory lower-threshold "
            "family track when expanded classes create excessive tail drops."
            if recommended
            else ""
        ),
    }


def _support_threshold_curve(
    diagnostics_dir: Path,
    run_id: str,
    thresholds: tuple[int, ...] = (1, 2, 3, 5, 10, 15, 18, 20, 25, 30),
) -> dict[str, Any]:
    fam_df = _family_distribution(diagnostics_dir, run_id)
    if fam_df.empty or "sample_count" not in fam_df.columns:
        return {}
    counts = pd.to_numeric(fam_df["sample_count"], errors="coerce").fillna(0).astype(int)
    return _support_threshold_curve_from_counts(counts.astype(int).tolist(), thresholds)


def _confusion_metrics(diagnostics_dir: Path) -> dict[str, Any]:
    df = _read_csv(diagnostics_dir / "top_confusion_pairs.csv")
    if df.empty or "count" not in df.columns:
        return {}
    work = df.copy()
    work["count"] = pd.to_numeric(work["count"], errors="coerce").fillna(0).astype(int)
    total = int(work["count"].sum())
    out = {"top_confusion_mass": total, "top_confusion_pair_count": int(len(work))}
    if "shared_type" in work.columns and total > 0:
        cross = work[work["shared_type"].fillna("").astype(str).str.lower().isin({"no", "false", "0"})]
        cross_n = int(cross["count"].sum())
        out["cross_type_confusion_mass"] = cross_n
        out["cross_type_confusion_share"] = round(cross_n / total, 6)
    if not work.empty:
        top = work.sort_values("count", ascending=False).iloc[0].to_dict()
        out["top_confusion_pair"] = {
            "true_family": str(top.get("true_family", "")),
            "predicted_family": str(top.get("predicted_family", "")),
            "count": int(top.get("count", 0) or 0),
        }
    return out


def _prediction_error_metrics(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    path = diagnostics_dir / f"prediction_errors_{run_id}.csv"
    df = _read_csv(path)
    if df.empty:
        return {}
    expected_col = next((c for c in ("family_canonical_expected", "true_family", "family") if c in df.columns), "")
    predicted_col = next((c for c in ("predicted_family", "prediction") if c in df.columns), "")
    if not expected_col or not predicted_col:
        return {"prediction_error_rows": int(len(df))}
    work = df.copy()
    work[expected_col] = work[expected_col].fillna("").astype(str)
    work[predicted_col] = work[predicted_col].fillna("").astype(str)
    pair_counts = (
        work.groupby([expected_col, predicted_col], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    expected_counts = work.groupby(expected_col, dropna=False).size().sort_values(ascending=False)
    predicted_counts = work.groupby(predicted_col, dropna=False).size().sort_values(ascending=False)
    total = int(len(work))
    pair_dist = _distribution_metrics(pair_counts["count"].astype(int).tolist())
    top_pair = pair_counts.iloc[0].to_dict() if not pair_counts.empty else {}
    raw_col = next(
        (c for c in ("raw_model_predicted_family", "raw_predicted_family") if c in work.columns),
        "",
    )
    top_raw: dict[str, Any] = {}
    if raw_col:
        work[raw_col] = work[raw_col].fillna("").astype(str)
        raw_pairs = (
            work.groupby([expected_col, raw_col], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        if not raw_pairs.empty:
            raw_top = raw_pairs.iloc[0].to_dict()
            top_raw = {
                "expected_family": str(raw_top.get(expected_col, "")),
                "predicted_family": str(raw_top.get(raw_col, "")),
                "count": int(raw_top.get("count", 0) or 0),
            }
    guard_count = 0
    if "override_tag" in work.columns:
        guard_count = int(
            work["override_tag"].fillna("").astype(str).str.strip().eq("type_guard_family_suppressed").sum()
        )
    return {
        "prediction_error_rows": total,
        "prediction_error_surface": "structured_prediction_errors_post_label_resolution",
        "error_pair_count": int(len(pair_counts)),
        "error_pair_entropy_bits": pair_dist.get("entropy_bits", 0.0),
        "error_pair_hhi": pair_dist.get("hhi", 0.0),
        "top_error_pair_share": round(float(pair_counts.iloc[0]["count"]) / total, 6) if total and not pair_counts.empty else 0.0,
        "top3_error_pair_share": pair_dist.get("top3_share", 0.0),
        "top_expected_error_family": str(expected_counts.index[0]) if not expected_counts.empty else "",
        "top_expected_error_count": int(expected_counts.iloc[0]) if not expected_counts.empty else 0,
        "top_predicted_error_family": str(predicted_counts.index[0]) if not predicted_counts.empty else "",
        "top_predicted_error_count": int(predicted_counts.iloc[0]) if not predicted_counts.empty else 0,
        "type_guard_suppressed_count": guard_count,
        "top_error_pair": {
            "expected_family": str(top_pair.get(expected_col, "")),
            "predicted_family": str(top_pair.get(predicted_col, "")),
            "count": int(top_pair.get("count", 0) or 0),
            "scope": "post_type_guard",
        },
        "top_error_pair_raw_model": {**top_raw, "scope": "raw_model"} if top_raw else {},
    }


def _ablation_metrics(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    rid = oh.normalize_artifact_run_id(run_id)
    candidates = [
        diagnostics_dir / f"feature_set_ablation_summary_{rid}.csv",
        diagnostics_dir / "feature_set_ablation_summary.csv",
        diagnostics_dir / f"ablation_summary_{rid}.csv",
        diagnostics_dir / f"ablation_summary_partial_{rid}.csv",
    ]
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        path = oh.resolve_feature_set_ablation_summary_path(diagnostics_dir, run_id)
    if not path.is_file():
        path = oh.resolve_ablation_summary_path(diagnostics_dir, run_id, allow_partial=True)
    df = _read_csv(path)
    if df.empty:
        return {}
    df = df.rename(
        columns={
            "feature_set_label": "experiment",
            "macro_f1": "macro_f1_score",
            "MacroF1": "macro_f1_score",
        }
    )
    if "experiment" not in df.columns or "macro_f1_score" not in df.columns:
        return {}
    df["experiment"] = df["experiment"].fillna("").astype(str)
    df["label_target"] = df.get("label_target", "family_id")
    df["label_target"] = df["label_target"].fillna("").astype(str)
    df["macro_f1_score"] = pd.to_numeric(df["macro_f1_score"], errors="coerce")
    fam = df[
        df["label_target"].isin(["family_id", "family_canonical_default", "family_within_type"])
    ].dropna(
        subset=["macro_f1_score"],
    )
    if fam.empty:
        return {}
    best = fam.sort_values("macro_f1_score", ascending=False).iloc[0]
    by_exp = fam.groupby("experiment")["macro_f1_score"].max().to_dict()
    vendor_full = _safe_float(by_exp.get("vendor_parsed_full", by_exp.get("vendor_full")), None)
    vendor_safe = _safe_float(
        by_exp.get("vendor_parsed_no_family", by_exp.get("vendor_no_parsed_family")),
        None,
    )
    full_fused = _safe_float(by_exp.get("full_fused"), None)
    perm_best = max(
        [
            x
            for x in (
                _safe_float(by_exp.get("permissions_raw"), None),
                _safe_float(by_exp.get("permissions_grouped"), None),
            )
            if x is not None
        ],
        default=None,
    )
    out: dict[str, Any] = {
        "best_family_experiment": str(best.get("experiment", "")),
        "best_family_macro_f1": round(float(best["macro_f1_score"]), 6),
        "vendor_full_minus_safe": None
        if vendor_full is None or vendor_safe is None
        else round(vendor_full - vendor_safe, 6),
        "vendor_full_minus_full_fused": None
        if vendor_full is None or full_fused is None
        else round(vendor_full - full_fused, 6),
        "full_fused_minus_permission_best": None
        if full_fused is None or perm_best is None
        else round(full_fused - perm_best, 6),
    }
    type_perf = _read_csv(diagnostics_dir / "family_vs_type_performance.csv")
    if not type_perf.empty and {"label_target", "macro_f1"} <= set(type_perf.columns):
        type_perf["macro_f1"] = pd.to_numeric(type_perf["macro_f1"], errors="coerce")
        type_rows = type_perf[type_perf["label_target"].astype(str) == "type_slug"].dropna(
            subset=["macro_f1"]
        )
        if not type_rows.empty:
            type_best = float(type_rows["macro_f1"].max())
            out["type_minus_best_family_safe"] = round(
                type_best
                - max([x for x in (vendor_safe, full_fused, perm_best) if x is not None], default=0.0),
                6,
            )
    return out


def _priority_score(metrics: dict[str, Any]) -> dict[str, Any]:
    dist = metrics.get("family_distribution", {}) if isinstance(metrics.get("family_distribution"), dict) else {}
    support_gap = metrics.get("support_gap", {}) if isinstance(metrics.get("support_gap"), dict) else {}
    support_curve = (
        metrics.get("support_threshold_curve")
        if isinstance(metrics.get("support_threshold_curve"), dict)
        else {}
    )
    support = metrics.get("support_performance", {}) if isinstance(metrics.get("support_performance"), dict) else {}
    confusion = metrics.get("confusion", {}) if isinstance(metrics.get("confusion"), dict) else {}
    pred = metrics.get("prediction_errors", {}) if isinstance(metrics.get("prediction_errors"), dict) else {}
    ablation = metrics.get("ablation", {}) if isinstance(metrics.get("ablation"), dict) else {}

    concentration = min(1.0, (_safe_float(dist.get("top5_share")) or 0.0) / 0.50)
    support_debt = min(1.0, (_safe_float(support_gap.get("below_support_family_count")) or 0.0) / 10.0)
    zero_recall = min(1.0, (_safe_float(support.get("zero_recall_positive_support_rows")) or 0.0) / 5.0)
    cross_type = min(1.0, (_safe_float(confusion.get("cross_type_confusion_share")) or 0.0) / 0.25)
    pred_conc = min(1.0, (_safe_float(pred.get("top3_error_pair_share")) or 0.0) / 0.25)
    leakage = min(1.0, (_safe_float(ablation.get("vendor_full_minus_safe")) or 0.0) / 0.12)
    type_gap = min(1.0, (_safe_float(ablation.get("type_minus_best_family_safe")) or 0.0) / 0.20)
    score = (
        concentration * 12
        + support_debt * 14
        + zero_recall * 18
        + cross_type * 14
        + pred_conc * 10
        + leakage * 18
        + type_gap * 14
    )
    return {
        "composite_problem_score_0_100": round(min(100.0, score), 3),
        "components": {
            "family_concentration": round(concentration, 6),
            "support_debt": round(support_debt, 6),
            "zero_recall": round(zero_recall, 6),
            "cross_type_confusion": round(cross_type, 6),
            "prediction_error_concentration": round(pred_conc, 6),
            "vendor_semantic_leakage_delta": round(leakage, 6),
            "type_family_task_gap": round(type_gap, 6),
        },
    }


def _issue_flags(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    dist = metrics.get("family_distribution", {}) if isinstance(metrics.get("family_distribution"), dict) else {}
    support = metrics.get("support_performance", {}) if isinstance(metrics.get("support_performance"), dict) else {}
    support_gap = metrics.get("support_gap", {}) if isinstance(metrics.get("support_gap"), dict) else {}
    support_curve = (
        metrics.get("support_threshold_curve")
        if isinstance(metrics.get("support_threshold_curve"), dict)
        else {}
    )
    confusion = metrics.get("confusion", {}) if isinstance(metrics.get("confusion"), dict) else {}
    pred = metrics.get("prediction_errors", {}) if isinstance(metrics.get("prediction_errors"), dict) else {}
    ablation = metrics.get("ablation", {}) if isinstance(metrics.get("ablation"), dict) else {}

    def add(severity: str, issue: str, value: Any, threshold: str, action: str) -> None:
        flags.append(
            {
                "severity": severity,
                "issue": issue,
                "value": value,
                "threshold": threshold,
                "recommended_action": action,
            }
        )

    top5_share = _safe_float(dist.get("top5_share")) or 0.0
    hhi_effective = _safe_float(dist.get("effective_class_count_hhi")) or 0.0
    classes = _safe_float(dist.get("classes")) or 0.0
    cross_type_share = _safe_float(confusion.get("cross_type_confusion_share")) or 0.0
    top3_error_share = _safe_float(pred.get("top3_error_pair_share")) or 0.0
    vendor_full_minus_safe = _safe_float(ablation.get("vendor_full_minus_safe")) or 0.0
    type_minus_best_family_safe = _safe_float(ablation.get("type_minus_best_family_safe")) or 0.0
    gap_le_5 = int(support_gap.get("families_with_gap_le_5", 0) or 0)

    if top5_share >= 0.50:
        add(
            "high",
            "family_concentration",
            dist.get("top5_share"),
            "top5_share >= 0.50",
            "Use Macro-F1/recall tails; test dominance caps or stratified family caps.",
        )
    if hhi_effective and hhi_effective < max(3.0, classes * 0.35):
        add(
            "medium",
            "low_effective_family_count",
            dist.get("effective_class_count_hhi"),
            "HHI effective classes < 35% of classes",
            "Inspect dominant families and low-support tail before model tuning.",
        )
    if int(support.get("zero_recall_positive_support_rows", 0) or 0) > 0:
        add(
            "high",
            "zero_recall_supported_families",
            support.get("zero_recall_positive_support_rows"),
            "> 0",
            "Review family labels/features for supported families with zero recall.",
        )
    if gap_le_5 > 0:
        add(
            "medium",
            "near_threshold_trainability_lift",
            gap_le_5,
            "families needing <= 5 samples",
            "Prioritize small support-gap families where a few governed rows can add trainable classes.",
        )
    if support_curve.get("dual_track_recommended"):
        rec = (
            support_curve.get("recommended_exploratory_threshold")
            if isinstance(support_curve.get("recommended_exploratory_threshold"), dict)
            else {}
        )
        add(
            "medium",
            "dual_support_threshold_track",
            rec.get("threshold", ""),
            "lower threshold retains >=90% rows and more classes than threshold 20",
            "Keep threshold 20 for evidence claims, but add an exploratory expanded-class analysis track.",
        )
    if cross_type_share >= 0.25:
        add(
            "medium",
            "cross_type_confusion",
            confusion.get("cross_type_confusion_share"),
            ">= 0.25",
            "Evaluate hierarchical type_slug -> family-within-type prediction.",
        )
    if top3_error_share >= 0.25:
        add(
            "medium",
            "prediction_error_pair_concentration",
            pred.get("top3_error_pair_share"),
            "top3 error-pair share >= 0.25",
            "Audit the top expected->predicted family pairs before changing model hyperparameters.",
        )
    if vendor_full_minus_safe >= 0.12:
        add(
            "high",
            "vendor_semantic_leakage_delta",
            ablation.get("vendor_full_minus_safe"),
            ">= 0.12 Macro-F1",
            "Tune leakage-safe vendor surfaces before relying on parsed family strings.",
        )
    if type_minus_best_family_safe >= 0.20:
        add(
            "high",
            "type_family_task_gap",
            ablation.get("type_minus_best_family_safe"),
            ">= 0.20 Macro-F1",
            "Separate coarse type claims from family-level claims.",
        )
    return flags


def _training_policy_recommendations(metrics: dict[str, Any]) -> dict[str, Any]:
    """Translate math diagnostics into explicit training tracks."""
    support_curve = (
        metrics.get("support_threshold_curve")
        if isinstance(metrics.get("support_threshold_curve"), dict)
        else {}
    )
    support_gap = metrics.get("support_gap", {}) if isinstance(metrics.get("support_gap"), dict) else {}
    ablation = metrics.get("ablation", {}) if isinstance(metrics.get("ablation"), dict) else {}
    threshold_20 = (
        support_curve.get("threshold_20")
        if isinstance(support_curve.get("threshold_20"), dict)
        else {}
    )
    exploratory = (
        support_curve.get("recommended_exploratory_threshold")
        if isinstance(support_curve.get("recommended_exploratory_threshold"), dict)
        else {}
    )
    tracks: list[dict[str, Any]] = []
    if threshold_20:
        tracks.append(
            {
                "track": "evidence_conservative_threshold_20",
                "use": "publication and locked-profile headline evidence",
                "threshold": int(threshold_20.get("threshold", 20) or 20),
                "trainable_classes": int(threshold_20.get("trainable_classes", 0) or 0),
                "retained_rows": int(threshold_20.get("retained_rows", 0) or 0),
                "dropped_rows": int(threshold_20.get("dropped_rows", 0) or 0),
                "retained_share": _round_finite(threshold_20.get("retained_share")),
                "risk": "May hide newly curated but low-support families by dropping them before training.",
                "recommended_action": "Keep as the conservative evidence track; do not use it as the only tuning view.",
            }
        )
    if exploratory:
        baseline_classes = int(threshold_20.get("trainable_classes", 0) or 0)
        class_lift = int(exploratory.get("trainable_classes", 0) or 0) - baseline_classes
        dropped_relief = int(threshold_20.get("dropped_rows", 0) or 0) - int(
            exploratory.get("dropped_rows", 0) or 0
        )
        tracks.append(
            {
                "track": "exploratory_expanded_class_threshold",
                "use": "taxonomy-aware model tuning and failure discovery",
                "threshold": int(exploratory.get("threshold", 0) or 0),
                "trainable_classes": int(exploratory.get("trainable_classes", 0) or 0),
                "retained_rows": int(exploratory.get("retained_rows", 0) or 0),
                "dropped_rows": int(exploratory.get("dropped_rows", 0) or 0),
                "retained_share": _round_finite(exploratory.get("retained_share")),
                "class_lift_vs_threshold_20": class_lift,
                "dropped_row_relief_vs_threshold_20": dropped_relief,
                "risk": "Not publication-equivalent to the locked threshold-20 headline task.",
                "recommended_action": (
                    "Run this as a separate exploratory track so new family splits can be evaluated "
                    "without weakening conservative evidence claims."
                ),
            }
        )
    fastest = (
        support_gap.get("fastest_trainability_lift")
        if isinstance(support_gap.get("fastest_trainability_lift"), list)
        else []
    )
    if fastest:
        top = fastest[0] if isinstance(fastest[0], dict) else {}
        tracks.append(
            {
                "track": "curation_support_gap_closure",
                "use": "highest-ROI database curation queue",
                "threshold": int(support_gap.get("min_support", 20) or 20),
                "top_family": str(top.get("family", "") or ""),
                "top_family_current_support": int(top.get("current_support", 0) or 0),
                "top_family_samples_needed": int(top.get("samples_needed", 0) or 0),
                "families_with_gap_le_5": int(support_gap.get("families_with_gap_le_5", 0) or 0),
                "samples_needed_to_make_all_families_trainable": int(
                    support_gap.get("samples_needed_to_make_all_families_trainable", 0) or 0
                ),
                "risk": "Adding labels without source discipline can create false trainability.",
                "recommended_action": (
                    "Prioritize source-backed records for families closest to the support threshold; "
                    "avoid merging evidence-backed families solely to improve model metrics."
                ),
            }
        )
    vendor_delta = _safe_float(ablation.get("vendor_full_minus_safe"), 0.0) or 0.0
    if vendor_delta >= 0.12:
        tracks.append(
            {
                "track": "leakage_safe_feature_tuning",
                "use": "model validity repair before headline uplift claims",
                "macro_f1_delta": round(vendor_delta, 6),
                "risk": "Parsed vendor family strings may be carrying label-like information.",
                "recommended_action": (
                    "Tune and compare detection-only, consensus-score, permission-only, and safe-fused "
                    "feature contracts before treating parsed-family features as scientific signal."
                ),
            }
        )
    primary = "evidence_conservative_threshold_20" if threshold_20 else ""
    secondary = "exploratory_expanded_class_threshold" if exploratory else ""
    return {
        "primary_headline_track": primary,
        "secondary_tuning_track": secondary,
        "tracks": tracks,
    }


def build_data_problem_quantification(*, diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    """Build quantitative data-problem metrics from run diagnostics."""
    fam_df = _family_distribution(diagnostics_dir, run_id)
    family_counts = fam_df["sample_count"].astype(int).tolist() if "sample_count" in fam_df.columns else []
    metrics = {
        "run_id": run_id,
        "family_distribution": _distribution_metrics(family_counts),
        "support_gap": _support_gap_metrics(diagnostics_dir, run_id),
        "support_threshold_curve": _support_threshold_curve(diagnostics_dir, run_id),
        "support_performance": _support_performance_metrics(diagnostics_dir),
        "confusion": _confusion_metrics(diagnostics_dir),
        "prediction_errors": _prediction_error_metrics(diagnostics_dir, run_id),
        "ablation": _ablation_metrics(diagnostics_dir, run_id),
    }
    metrics["priority_score"] = _priority_score(metrics)
    metrics["issue_flags"] = _issue_flags(metrics)
    metrics["training_policy_recommendations"] = _training_policy_recommendations(metrics)
    return metrics


def write_data_problem_quantification(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    """Write quantitative data-problem metrics to JSON/CSV/Markdown."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_data_problem_quantification(diagnostics_dir=diagnostics_dir, run_id=run_id)
    json_path = diagnostics_dir / f"data_problem_quantification_{run_id}.json"
    csv_path = diagnostics_dir / f"data_problem_quantification_{run_id}.csv"
    md_path = diagnostics_dir / f"data_problem_quantification_{run_id}.md"

    json_text = json.dumps(payload, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for section, values in payload.items():
        if not isinstance(values, dict):
            continue
        for metric, value in values.items():
            if isinstance(value, (dict, list)):
                continue
            rows.append({"section": section, "metric": metric, "value": value})
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["section", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)

    lines = [f"# Data problem quantification - `{run_id}`", ""]
    dist = payload["family_distribution"]
    support_gap = payload.get("support_gap") if isinstance(payload.get("support_gap"), dict) else {}
    support_curve = (
        payload.get("support_threshold_curve")
        if isinstance(payload.get("support_threshold_curve"), dict)
        else {}
    )
    pred = payload.get("prediction_errors") if isinstance(payload.get("prediction_errors"), dict) else {}
    priority = payload.get("priority_score") if isinstance(payload.get("priority_score"), dict) else {}
    training_policy = (
        payload.get("training_policy_recommendations")
        if isinstance(payload.get("training_policy_recommendations"), dict)
        else {}
    )
    lines.extend(
        [
            "## Distribution Math",
            "",
            f"- Families/classes: `{dist.get('classes')}`",
            f"- Entropy: `{dist.get('entropy_bits')}` bits",
            f"- Normalized entropy: `{dist.get('normalized_entropy')}`",
            f"- HHI: `{dist.get('hhi')}`",
            f"- KL-to-uniform: `{dist.get('kl_to_uniform_bits')}` bits",
            "- Effective classes (entropy / HHI): "
            f"`{dist.get('effective_class_count_entropy')}` / "
            f"`{dist.get('effective_class_count_hhi')}`",
            f"- Gini: `{dist.get('gini')}`",
            f"- Theil T / Atkinson(0.5): `{dist.get('theil_t')}` / `{dist.get('atkinson_0_5')}`",
            f"- Bottom-20 / Bottom-50 share: `{dist.get('bottom20_share')}` / `{dist.get('bottom50_share')}`",
            "- Top-1 / Top-3 / Top-5 share: "
            f"`{dist.get('top1_share')}` / `{dist.get('top3_share')}` / "
            f"`{dist.get('top5_share')}`",
            f"- Palma ratio: `{dist.get('palma_ratio')}`",
            "",
            "## Marginal Fix Math",
            "",
            f"- Composite problem score: `{priority.get('composite_problem_score_0_100', 0.0)}` / 100",
            f"- Families below support threshold: `{support_gap.get('below_support_family_count', 0)}`",
            f"- Support-gap distribution source: `{support_gap.get('distribution_source', '')}`",
            f"- Samples needed to make all current families trainable: `{support_gap.get('samples_needed_to_make_all_families_trainable', 0)}`",
            f"- Families within <=5 samples of trainability: `{support_gap.get('families_with_gap_le_5', 0)}`",
            f"- Pre-training families below runtime min-support: `{support_gap.get('pretraining_families_below_runtime_min_support', 'n/a')}`",
            f"- Prediction-error top-3 pair share: `{pred.get('top3_error_pair_share', 0.0)}`",
            f"- Prediction-error surface: `{pred.get('prediction_error_surface', 'structured_prediction_errors')}`",
            f"- Type-guard suppressions in prediction_errors: `{pred.get('type_guard_suppressed_count', 0)}`",
            "",
            "### Support Threshold Curve",
            "",
        ]
    )
    curve = support_curve.get("curve") if isinstance(support_curve.get("curve"), list) else []
    if curve:
        lines.append("| threshold | trainable_classes | retained_rows | dropped_rows | retained_share |")
        lines.append("|---:|---:|---:|---:|---:|")
        for row in curve:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| {row.get('threshold')} | {row.get('trainable_classes')} | "
                f"{row.get('retained_rows')} | {row.get('dropped_rows')} | "
                f"{row.get('retained_share')} |"
            )
        rec = (
            support_curve.get("recommended_exploratory_threshold")
            if isinstance(support_curve.get("recommended_exploratory_threshold"), dict)
            else {}
        )
        if rec:
            lines.extend(
                [
                    "",
                    f"- Exploratory expanded-class threshold: `{rec.get('threshold')}` "
                    f"with `{rec.get('trainable_classes')}` trainable classes and "
                    f"`{rec.get('retained_rows')}` retained rows.",
                ]
            )
    else:
        lines.append("- No support threshold curve available.")
    tracks = training_policy.get("tracks") if isinstance(training_policy.get("tracks"), list) else []
    lines.extend(
        [
            "",
            "### Training Policy Recommendations",
            "",
            f"- Primary headline track: `{training_policy.get('primary_headline_track', '') or 'n/a'}`",
            f"- Secondary tuning track: `{training_policy.get('secondary_tuning_track', '') or 'n/a'}`",
        ]
    )
    if tracks:
        for track in tracks:
            if not isinstance(track, dict):
                continue
            lines.append(
                f"- `{track.get('track')}`: {track.get('recommended_action', '')}"
            )
    else:
        lines.append("- No training-policy recommendation available.")
    lines.extend(
        [
            "",
            "### Fastest Trainability Lift",
            "",
        ]
    )
    lift = (
        support_gap.get("fastest_trainability_lift")
        if isinstance(support_gap.get("fastest_trainability_lift"), list)
        else []
    )
    if lift:
        for row in lift[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('family')}`: support `{row.get('current_support')}`, "
                f"needs `{row.get('samples_needed')}` sample(s)"
            )
    else:
        lines.append("- No support-gap lift queue available.")
    top_pair = pred.get("top_error_pair") if isinstance(pred.get("top_error_pair"), dict) else {}
    if top_pair:
        lines.extend(
            [
                "",
                "### Concentrated Prediction Errors",
                "",
                f"- Top pair: `{top_pair.get('expected_family')}` -> `{top_pair.get('predicted_family')}` "
                f"with `{top_pair.get('count')}` row(s)",
                f"- Top expected error family: `{pred.get('top_expected_error_family')}` "
                f"({pred.get('top_expected_error_count')})",
                f"- Top predicted error family: `{pred.get('top_predicted_error_family')}` "
                f"({pred.get('top_predicted_error_count')})",
            ]
        )
    lines.extend(
        [
            "",
            "## Issue Flags",
            "",
        ]
    )
    flags = payload.get("issue_flags") if isinstance(payload.get("issue_flags"), list) else []
    if flags:
        for flag in flags:
            lines.append(
                f"- **{str(flag.get('severity', '')).upper()}** `{flag.get('issue')}`: "
                f"value=`{flag.get('value')}` threshold=`{flag.get('threshold')}`. "
                f"{flag.get('recommended_action')}"
            )
    else:
        lines.append("- No automatic quantitative issue flags triggered.")
    md_text = "\n".join(lines).rstrip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")

    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        text=json_text + "\n",
        global_latest_name="data_problem_quantification.latest.json",
    )
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_path.read_text(encoding="utf-8"),
        global_latest_name="data_problem_quantification.latest.csv",
    )
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="data_problem_quantification.latest.md",
    )
    return md_path, csv_path, json_path, payload


def _delta(current: dict[str, Any], baseline: dict[str, Any], key: str) -> float | None:
    cur = _safe_float(current.get(key), None)
    base = _safe_float(baseline.get(key), None)
    if cur is None or base is None:
        return None
    return round(cur - base, 6)


def compare_data_problem_quantification(
    *,
    current_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
) -> dict[str, Any]:
    """Compare two data-problem payloads and surface regression deltas."""
    cur_dist = current_payload.get("family_distribution")
    base_dist = baseline_payload.get("family_distribution")
    cur_support = current_payload.get("support_gap")
    base_support = baseline_payload.get("support_gap")
    cur_ablation = current_payload.get("ablation")
    base_ablation = baseline_payload.get("ablation")
    cur_priority = current_payload.get("priority_score")
    base_priority = baseline_payload.get("priority_score")

    cur_dist = cur_dist if isinstance(cur_dist, dict) else {}
    base_dist = base_dist if isinstance(base_dist, dict) else {}
    cur_support = cur_support if isinstance(cur_support, dict) else {}
    base_support = base_support if isinstance(base_support, dict) else {}
    cur_ablation = cur_ablation if isinstance(cur_ablation, dict) else {}
    base_ablation = base_ablation if isinstance(base_ablation, dict) else {}
    cur_priority = cur_priority if isinstance(cur_priority, dict) else {}
    base_priority = base_priority if isinstance(base_priority, dict) else {}
    comparable_sections = [
        "family_distribution",
        "support_gap",
        "support_performance",
        "confusion",
        "prediction_errors",
        "ablation",
    ]
    current_missing_sections = [
        name
        for name in comparable_sections
        if not isinstance(current_payload.get(name), dict) or not current_payload.get(name)
    ]
    baseline_missing_sections = [
        name
        for name in comparable_sections
        if not isinstance(baseline_payload.get(name), dict) or not baseline_payload.get(name)
    ]
    composite_comparable = not current_missing_sections and not baseline_missing_sections

    deltas = {
        "family_classes_delta": _delta(cur_dist, base_dist, "classes"),
        "normalized_entropy_delta": _delta(cur_dist, base_dist, "normalized_entropy"),
        "gini_delta": _delta(cur_dist, base_dist, "gini"),
        "atkinson_0_5_delta": _delta(cur_dist, base_dist, "atkinson_0_5"),
        "bottom20_share_delta": _delta(cur_dist, base_dist, "bottom20_share"),
        "bottom50_share_delta": _delta(cur_dist, base_dist, "bottom50_share"),
        "palma_ratio_delta": _delta(cur_dist, base_dist, "palma_ratio"),
        "below_support_family_count_delta": _delta(
            cur_support, base_support, "below_support_family_count"
        ),
        "samples_needed_to_trainable_delta": _delta(
            cur_support, base_support, "samples_needed_to_make_all_families_trainable"
        ),
        "best_family_macro_f1_delta": _delta(cur_ablation, base_ablation, "best_family_macro_f1"),
        "composite_problem_score_delta": _delta(
            cur_priority, base_priority, "composite_problem_score_0_100"
        )
        if composite_comparable
        else None,
    }
    regressions: list[dict[str, Any]] = []

    def add(name: str, value: Any, direction: str, action: str) -> None:
        regressions.append(
            {
                "metric": name,
                "delta": value,
                "direction": direction,
                "recommended_action": action,
            }
        )

    if (deltas["family_classes_delta"] or 0) > 0:
        add(
            "family_classes_delta",
            deltas["family_classes_delta"],
            "taxonomy_expansion",
            "Review whether newly split families are governed labels or alias/policy drift.",
        )
    if (deltas["below_support_family_count_delta"] or 0) > 0:
        add(
            "below_support_family_count_delta",
            deltas["below_support_family_count_delta"],
            "tail_debt_increase",
            "Prioritize near-threshold families before accepting new family splits.",
        )
    if (deltas["samples_needed_to_trainable_delta"] or 0) > 0:
        add(
            "samples_needed_to_trainable_delta",
            deltas["samples_needed_to_trainable_delta"],
            "trainability_cost_increase",
            "Quantify whether added tail families are worth the extra support burden.",
        )
    if (deltas["bottom50_share_delta"] or 0) < -0.02:
        add(
            "bottom50_share_delta",
            deltas["bottom50_share_delta"],
            "tail_mass_loss",
            "Check if taxonomy expansion fragmented already-small families.",
        )
    if (deltas["best_family_macro_f1_delta"] or 0) < -0.03:
        add(
            "best_family_macro_f1_delta",
            deltas["best_family_macro_f1_delta"],
            "family_model_quality_drop",
            "Compare label splits and dropped training rows before tuning hyperparameters.",
        )

    return {
        "current_run_id": current_payload.get("run_id", ""),
        "baseline_run_id": baseline_payload.get("run_id", ""),
        "composite_score_comparable": composite_comparable,
        "current_missing_sections": current_missing_sections,
        "baseline_missing_sections": baseline_missing_sections,
        "deltas": deltas,
        "regressions": regressions,
    }


def _aligned_label_frame(diagnostics_dir: Path, run_id: str) -> pd.DataFrame:
    path = diagnostics_dir / f"aligned_labels_{run_id}.csv"
    df = _read_csv(path)
    if df.empty:
        for candidate in sorted(diagnostics_dir.glob("aligned_labels_*.csv")):
            df = _read_csv(candidate)
            if not df.empty:
                break
    return df


def _taxonomy_transition_metrics(
    *,
    current_diagnostics_dir: Path,
    current_run_id: str,
    baseline_diagnostics_dir: Path,
    baseline_run_id: str,
) -> tuple[dict[str, Any], pd.DataFrame]:
    current = _aligned_label_frame(current_diagnostics_dir, current_run_id)
    baseline = _aligned_label_frame(baseline_diagnostics_dir, baseline_run_id)
    required = {"sample_id", "family_canonical", "type_slug"}
    if current.empty or baseline.empty or not required <= set(current.columns) or not required <= set(baseline.columns):
        return {"available": False, "reason": "aligned_labels_missing_or_incomplete"}, pd.DataFrame()

    optional_cols = [
        "sample_label_raw",
        "family_label_raw",
        "vt_family_token",
        "vt_suggested_label",
        "package_name",
        "vt_malicious_count",
        "effective_first_seen_at_utc",
    ]
    cols = ["sample_id", "family_canonical", "family_id", "type_slug"] + [
        col for col in optional_cols if col in current.columns and col in baseline.columns
    ]
    cur = current[[col for col in cols if col in current.columns]].copy()
    base = baseline[[col for col in cols if col in baseline.columns]].copy()
    cur["sample_id"] = pd.to_numeric(cur["sample_id"], errors="coerce")
    base["sample_id"] = pd.to_numeric(base["sample_id"], errors="coerce")
    cur = cur.dropna(subset=["sample_id"]).assign(sample_id=lambda df: df["sample_id"].astype(int))
    base = base.dropna(subset=["sample_id"]).assign(sample_id=lambda df: df["sample_id"].astype(int))
    merged = cur.set_index("sample_id").join(
        base.set_index("sample_id"),
        how="inner",
        lsuffix="_current",
        rsuffix="_baseline",
    )
    if merged.empty:
        return {"available": False, "reason": "no_shared_sample_ids"}, pd.DataFrame()

    family_changed = (
        merged["family_canonical_current"].fillna("").astype(str)
        != merged["family_canonical_baseline"].fillna("").astype(str)
    )
    type_changed = (
        merged["type_slug_current"].fillna("").astype(str)
        != merged["type_slug_baseline"].fillna("").astype(str)
    )
    changed = merged[family_changed | type_changed].reset_index()
    current_counts = current["family_canonical"].fillna("").astype(str).value_counts().to_dict()
    baseline_families = set(baseline["family_canonical"].fillna("").astype(str))
    current_families = set(current["family_canonical"].fillna("").astype(str))
    new_families = sorted(f for f in current_families - baseline_families if f)
    removed_families = sorted(f for f in baseline_families - current_families if f)

    transition_rows: list[dict[str, Any]] = []
    if not changed.empty:
        group_cols = ["family_canonical_baseline", "family_canonical_current"]
        grouped = changed.groupby(group_cols, dropna=False).size().reset_index(name="changed_rows")
        for row in grouped.sort_values("changed_rows", ascending=False).to_dict("records"):
            cur_family = str(row.get("family_canonical_current", "") or "")
            base_family = str(row.get("family_canonical_baseline", "") or "")
            subset = changed[
                (changed["family_canonical_current"].fillna("").astype(str) == cur_family)
                & (changed["family_canonical_baseline"].fillna("").astype(str) == base_family)
            ]
            transition_rows.append(
                {
                    "baseline_family": base_family,
                    "current_family": cur_family,
                    "changed_rows": int(row.get("changed_rows", 0) or 0),
                    "current_family_support": int(current_counts.get(cur_family, 0) or 0),
                    "is_current_new_family": cur_family in new_families,
                    "is_current_low_support": int(current_counts.get(cur_family, 0) or 0) < 20,
                    "sample_ids": ",".join(str(int(x)) for x in sorted(subset["sample_id"].tolist())),
                }
            )
    transition_df = pd.DataFrame(transition_rows)

    remerge_candidates = [
        row
        for row in transition_rows
        if bool(row.get("is_current_new_family"))
        and bool(row.get("is_current_low_support"))
        and str(row.get("baseline_family", "") or "").strip()
    ]
    remerge_simulation: dict[str, Any] = {}
    if remerge_candidates:
        adjusted_counts = {str(k): int(v) for k, v in current_counts.items() if str(k)}
        merge_groups: dict[str, dict[str, Any]] = {}
        for row in remerge_candidates:
            source = str(row.get("baseline_family", "") or "")
            target = str(row.get("current_family", "") or "")
            if not source or not target or source == target:
                continue
            target_support = int(adjusted_counts.get(target, 0) or 0)
            adjusted_counts[source] = int(adjusted_counts.get(source, 0) or 0) + target_support
            adjusted_counts.pop(target, None)
            group = merge_groups.setdefault(
                source,
                {
                    "source_family": source,
                    "source_current_support": int(current_counts.get(source, 0) or 0),
                    "merge_families": [],
                    "changed_sample_ids": [],
                },
            )
            group["merge_families"].append(target)
            sample_ids = [
                token.strip()
                for token in str(row.get("sample_ids", "") or "").split(",")
                if token.strip()
            ]
            group["changed_sample_ids"].extend(sample_ids)

        for group in merge_groups.values():
            source = str(group.get("source_family", "") or "")
            group["adjusted_support"] = int(adjusted_counts.get(source, 0) or 0)
            group["support_delta"] = int(group["adjusted_support"]) - int(
                group.get("source_current_support", 0) or 0
            )
            group["merge_family_count"] = len(group.get("merge_families") or [])
            group["changed_sample_count"] = len(set(group.get("changed_sample_ids") or []))
            group["merge_families"] = sorted(set(group.get("merge_families") or []))
            group["changed_sample_ids"] = sorted(set(group.get("changed_sample_ids") or []))

        current_count_values = [int(v) for v in current_counts.values() if int(v) > 0]
        adjusted_count_values = [int(v) for v in adjusted_counts.values() if int(v) > 0]
        current_threshold = _support_threshold_curve_from_counts(current_count_values)
        adjusted_threshold = _support_threshold_curve_from_counts(adjusted_count_values)
        remerge_simulation = {
            "candidate_group_count": len(merge_groups),
            "candidate_family_count": len(remerge_candidates),
            "candidate_changed_rows": sum(int(row.get("changed_rows", 0) or 0) for row in remerge_candidates),
            "current_family_count": len(current_count_values),
            "adjusted_family_count": len(adjusted_count_values),
            "family_count_delta": len(adjusted_count_values) - len(current_count_values),
            "current_threshold_20": current_threshold.get("threshold_20", {}),
            "adjusted_threshold_20": adjusted_threshold.get("threshold_20", {}),
            "trainable_class_delta_at_20": int(
                adjusted_threshold.get("threshold_20", {}).get("trainable_classes", 0) or 0
            )
            - int(current_threshold.get("threshold_20", {}).get("trainable_classes", 0) or 0),
            "dropped_row_delta_at_20": int(
                adjusted_threshold.get("threshold_20", {}).get("dropped_rows", 0) or 0
            )
            - int(current_threshold.get("threshold_20", {}).get("dropped_rows", 0) or 0),
            "merge_groups": sorted(
                merge_groups.values(),
                key=lambda row: (-int(row.get("support_delta", 0) or 0), str(row.get("source_family", ""))),
            ),
        }

    new_low_support = [fam for fam in new_families if int(current_counts.get(fam, 0) or 0) < 20]
    source_family_count = (
        int(changed["family_canonical_baseline"].nunique()) if not changed.empty else 0
    )
    largest_source_split = {}
    if not changed.empty:
        split_counts = (
            changed.groupby("family_canonical_baseline")["family_canonical_current"]
            .nunique()
            .sort_values(ascending=False)
        )
        if not split_counts.empty:
            src = str(split_counts.index[0])
            largest_source_split = {
                "baseline_family": src,
                "current_family_count": int(split_counts.iloc[0]),
                "changed_rows": int((changed["family_canonical_baseline"].astype(str) == src).sum()),
            }

    return (
        {
            "available": True,
            "shared_sample_ids": int(len(merged)),
            "changed_sample_rows": int(len(changed)),
            "family_changed_rows": int(family_changed.sum()),
            "type_changed_rows": int(type_changed.sum()),
            "new_current_families": new_families,
            "removed_baseline_families": removed_families,
            "new_low_support_family_count": int(len(new_low_support)),
            "new_low_support_families": new_low_support,
            "source_family_count": source_family_count,
            "largest_source_split": largest_source_split,
            "remerge_simulation": remerge_simulation,
        },
        transition_df,
    )


def write_data_problem_delta(
    *,
    current_diagnostics_dir: Path,
    current_run_id: str,
    baseline_diagnostics_dir: Path,
    baseline_run_id: str,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write current-vs-baseline data-problem delta artifacts."""
    _cur_md, _cur_csv, _cur_json, current_payload = write_data_problem_quantification(
        diagnostics_dir=current_diagnostics_dir,
        run_id=current_run_id,
    )
    _base_md, _base_csv, _base_json, baseline_payload = write_data_problem_quantification(
        diagnostics_dir=baseline_diagnostics_dir,
        run_id=baseline_run_id,
    )
    payload = compare_data_problem_quantification(
        current_payload=current_payload,
        baseline_payload=baseline_payload,
    )
    transition_summary, transition_df = _taxonomy_transition_metrics(
        current_diagnostics_dir=current_diagnostics_dir,
        current_run_id=current_run_id,
        baseline_diagnostics_dir=baseline_diagnostics_dir,
        baseline_run_id=baseline_run_id,
    )
    payload["taxonomy_transition_summary"] = transition_summary
    if transition_summary.get("available"):
        largest = (
            transition_summary.get("largest_source_split")
            if isinstance(transition_summary.get("largest_source_split"), dict)
            else {}
        )
        remerge = (
            transition_summary.get("remerge_simulation")
            if isinstance(transition_summary.get("remerge_simulation"), dict)
            else {}
        )
        if (
            int(transition_summary.get("new_low_support_family_count", 0) or 0) > 0
            and int(largest.get("current_family_count", 0) or 0) > 1
        ):
            payload.setdefault("regressions", []).append(
                {
                    "metric": "taxonomy_fragmentation_transition",
                    "delta": transition_summary.get("changed_sample_rows"),
                    "direction": "single_source_family_split_into_low_support_tail",
                    "recommended_action": (
                        "Review changed sample IDs before accepting new family splits; this can add many "
                        "classes while changing very few locked rows."
                    ),
                }
            )
        if int(remerge.get("trainable_class_delta_at_20", 0) or 0) > 0:
            payload.setdefault("regressions", []).append(
                {
                    "metric": "taxonomy_remerge_trainability_lift",
                    "delta": remerge.get("trainable_class_delta_at_20"),
                    "direction": "alias_remerge_recovers_min_support_class",
                    "recommended_action": (
                        "Review remerge candidates as alias/campaign-token splits; if accepted, this can recover "
                        "trainable classes under the conservative threshold-20 track."
                    ),
                }
            )
    json_path = current_diagnostics_dir / f"data_problem_delta_{current_run_id}_vs_{baseline_run_id}.json"
    md_path = current_diagnostics_dir / f"data_problem_delta_{current_run_id}_vs_{baseline_run_id}.md"
    transition_csv_path = (
        current_diagnostics_dir / f"data_problem_family_transitions_{current_run_id}_vs_{baseline_run_id}.csv"
    )
    json_text = json.dumps(payload, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    if not transition_df.empty:
        transition_df.to_csv(transition_csv_path, index=False)

    lines = [
        f"# Data problem delta - `{current_run_id}` vs `{baseline_run_id}`",
        "",
        "## Comparability",
        "",
        f"- Composite score comparable: `{payload.get('composite_score_comparable')}`",
        f"- Current missing sections: `{', '.join(payload.get('current_missing_sections') or []) or 'none'}`",
        f"- Baseline missing sections: `{', '.join(payload.get('baseline_missing_sections') or []) or 'none'}`",
        "",
        "## Deltas",
        "",
    ]
    for key, value in payload.get("deltas", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Regression Flags", ""])
    regressions = payload.get("regressions") if isinstance(payload.get("regressions"), list) else []
    if regressions:
        for row in regressions:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- `{row.get('metric')}` delta=`{row.get('delta')}` "
                f"direction=`{row.get('direction')}`. {row.get('recommended_action')}"
            )
    else:
        lines.append("- No automatic current-vs-baseline regression flags triggered.")
    lines.extend(["", "## Taxonomy Transition Summary", ""])
    if transition_summary.get("available"):
        lines.extend(
            [
                f"- Changed locked sample rows: `{transition_summary.get('changed_sample_rows')}`",
                f"- Family-changed rows: `{transition_summary.get('family_changed_rows')}`",
                f"- Type-changed rows: `{transition_summary.get('type_changed_rows')}`",
                f"- New current families: `{', '.join(transition_summary.get('new_current_families') or []) or 'none'}`",
                f"- New low-support families: `{', '.join(transition_summary.get('new_low_support_families') or []) or 'none'}`",
                f"- Transition CSV: `{transition_csv_path.name if transition_csv_path.is_file() else 'not written'}`",
            ]
        )
        largest = (
            transition_summary.get("largest_source_split")
            if isinstance(transition_summary.get("largest_source_split"), dict)
            else {}
        )
        if largest:
            lines.append(
                f"- Largest source split: `{largest.get('baseline_family')}` -> "
                f"`{largest.get('current_family_count')}` current families over "
                f"`{largest.get('changed_rows')}` row(s)"
            )
        remerge = (
            transition_summary.get("remerge_simulation")
            if isinstance(transition_summary.get("remerge_simulation"), dict)
            else {}
        )
        if remerge:
            current_20 = (
                remerge.get("current_threshold_20")
                if isinstance(remerge.get("current_threshold_20"), dict)
                else {}
            )
            adjusted_20 = (
                remerge.get("adjusted_threshold_20")
                if isinstance(remerge.get("adjusted_threshold_20"), dict)
                else {}
            )
            lines.extend(
                [
                    "",
                    "## Remerge Simulation",
                    "",
                    f"- Candidate source groups: `{remerge.get('candidate_group_count')}`",
                    f"- Candidate split families: `{remerge.get('candidate_family_count')}`",
                    f"- Family count delta if remerged: `{remerge.get('family_count_delta')}`",
                    f"- Threshold-20 trainable classes: `{current_20.get('trainable_classes')}` -> `{adjusted_20.get('trainable_classes')}`",
                    f"- Threshold-20 dropped rows: `{current_20.get('dropped_rows')}` -> `{adjusted_20.get('dropped_rows')}`",
                ]
            )
            merge_groups = (
                remerge.get("merge_groups") if isinstance(remerge.get("merge_groups"), list) else []
            )
            for group in merge_groups[:8]:
                if not isinstance(group, dict):
                    continue
                lines.append(
                    f"- `{group.get('source_family')}` absorb `{', '.join(group.get('merge_families') or [])}`: "
                    f"support `{group.get('source_current_support')}` -> `{group.get('adjusted_support')}`, "
                    f"sample_ids `{', '.join(group.get('changed_sample_ids') or [])}`"
                )
    else:
        lines.append(f"- Transition summary unavailable: `{transition_summary.get('reason', 'unknown')}`")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return md_path, json_path, payload
