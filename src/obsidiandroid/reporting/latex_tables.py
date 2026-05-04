"""Helpers for exporting publication-ready LaTeX tables.

This module centralizes table formatting to avoid drift across ad-hoc exporters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class LatexTableSpec:
    """Table rendering configuration.

    Attributes:
        align: LaTeX alignment string, e.g., "lccrr".
        use_booktabs: Whether to emit booktabs rules.
    """

    align: str
    use_booktabs: bool = True


def normalize_model_name(value: Any) -> str:
    """Return a publication-friendly model label."""
    token = str(value or "").strip().lower()
    mapping = {
        "random_forest": "Random Forest",
        "rf": "Random Forest",
        "xgboost": "XGBoost",
        "xgb": "XGBoost",
        "logistic_regression": "Logistic Regression",
        "log_reg": "Logistic Regression",
    }
    return mapping.get(token, str(value))


def latex_escape(value: Any) -> str:
    """Escape a scalar for LaTeX tabular cells."""
    text = "" if value is None else str(value)
    # Allow deliberate inline LaTeX commands (e.g., \textbf{...}).
    if text.startswith(r"\textbf{") and text.endswith("}"):
        return text
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    for token, repl in replacements.items():
        text = text.replace(token, repl)
    return text


def _format_scalar(value: Any, *, decimals: int = 3, percent: bool = False) -> Any:
    """Apply scalar formatting with safe fallbacks."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if percent:
        try:
            return f"{float(value) * 100:.1f}%"
        except Exception:
            return value
    try:
        num = float(value)
        return f"{num:.{decimals}f}"
    except Exception:
        return value


def _format_scientific(value: Any, *, digits: int = 2) -> Any:
    """Format value using scientific notation."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    try:
        return f"{float(value):.{digits}e}"
    except Exception:
        return value


def render_tabular(
    df: pd.DataFrame,
    *,
    spec: LatexTableSpec,
) -> str:
    """Render a DataFrame into LaTeX tabular code."""
    columns = [str(col) for col in df.columns.tolist()]
    lines: list[str] = []
    lines.append(r"\begin{tabular}{" + spec.align + "}")
    if spec.use_booktabs:
        lines.append(r"\toprule")
    else:
        lines.append(r"\hline")
    lines.append(" & ".join(latex_escape(col) for col in columns) + r" \\")
    if spec.use_booktabs:
        lines.append(r"\midrule")
    else:
        lines.append(r"\hline")
    for _, row in df.iterrows():
        cells = [latex_escape(row[col]) for col in columns]
        lines.append(" & ".join(cells) + r" \\")
    if spec.use_booktabs:
        lines.append(r"\bottomrule")
    else:
        lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def write_tabular(df: pd.DataFrame, *, output_path: Path, spec: LatexTableSpec) -> None:
    """Write a DataFrame as a LaTeX tabular file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_tabular(df, spec=spec), encoding="utf-8")


def build_model_comparison_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build formatted model-comparison table."""
    required = [
        "Model",
        "Accuracy",
        "Precision",
        "Recall",
        "F1-Score",
        "Macro F1-Score",
        "Rank",
    ]
    cols = [col for col in required if col in raw_df.columns]
    work = raw_df[cols].copy()
    rename_map = {
        "Model": "Model",
        "Accuracy": "Accuracy",
        "Precision": "Precision",
        "Recall": "Recall",
        "F1-Score": "F1",
        "Macro F1-Score": "Macro-F1",
        "Rank": "Rank",
    }
    work = work.rename(columns=rename_map)
    if "Model" in work.columns:
        work["Model"] = work["Model"].map(normalize_model_name)
    for metric in ("Accuracy", "Precision", "Recall", "F1", "Macro-F1"):
        if metric in work.columns:
            work[metric] = work[metric].map(lambda x: _format_scalar(x, decimals=3))
    if "Rank" in work.columns:
        work["Rank"] = pd.to_numeric(work["Rank"], errors="coerce").fillna(0).astype(int).astype(str)
    # Bold best model row.
    if "Rank" in work.columns and "Model" in work.columns:
        rank_num = pd.to_numeric(work["Rank"], errors="coerce")
        if not rank_num.dropna().empty:
            best_idx = rank_num.idxmin()
            work.loc[best_idx, "Model"] = r"\textbf{" + str(work.loc[best_idx, "Model"]) + "}"
    return work


def build_feature_ablation_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build formatted feature-ablation table with full metrics context."""
    work = raw_df.copy()
    rename_map = {
        "experiment": "Feature Set",
        "model": "Model",
        "accuracy": "Accuracy",
        "macro_precision": "Macro Precision",
        "macro_recall": "Macro Recall",
        "macro_f1_score": "Macro-F1",
    }
    wanted = [col for col in rename_map.keys() if col in work.columns]
    work = work[wanted].rename(columns={k: v for k, v in rename_map.items() if k in wanted})
    if "Model" in work.columns:
        work["Model"] = work["Model"].map(normalize_model_name)
    if "Feature Set" in work.columns:
        work["Feature Set"] = (
            work["Feature Set"]
            .astype(str)
            .str.replace("_", " ", regex=False)
            .str.title()
        )
    for metric in ("Accuracy", "Macro Precision", "Macro Recall", "Macro-F1"):
        if metric in work.columns:
            work[metric] = work[metric].map(lambda x: _format_scalar(x, decimals=3))
    return work


def build_dangerous_stats_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build formatted dangerous-permission statistical table."""
    work = raw_df.copy()
    rename_map = {
        "metric": "Metric",
        "group_a": "Group A",
        "group_b": "Group B",
        "statistic": "Statistic",
        "p_value": "p-value",
        "p_value_fdr_bh": "FDR p-value",
        "effect_size": "Effect Size",
        "effect_size_name": "Effect Name",
        "test_type": "Test",
    }
    wanted = [col for col in rename_map.keys() if col in work.columns]
    work = work[wanted].rename(columns={k: v for k, v in rename_map.items() if k in wanted})
    # Paper-facing label cleanup for internal tokens.
    if "Metric" in work.columns:
        work["Metric"] = (
            work["Metric"]
            .astype(str)
            .str.replace("dangerous_count_strict", "Dangerous Permission Count", regex=False)
            .str.replace("_", " ", regex=False)
            .str.title()
        )
    if "Test" in work.columns:
        work["Test"] = (
            work["Test"]
            .astype(str)
            .str.replace("kruskal_wallis", "Kruskal-Wallis", regex=False)
            .str.replace("pairwise_dunn", "Dunn Post Hoc", regex=False)
        )
    if "Effect Name" in work.columns:
        work["Effect Name"] = (
            work["Effect Name"]
            .astype(str)
            .str.replace("cliffs_delta", "Cliff's Delta", regex=False)
            .str.replace("epsilon_squared", "Epsilon-Squared", regex=False)
        )
    if "p-value" in work.columns:
        work = work.sort_values("p-value", ascending=True, kind="mergesort")
    if "Statistic" in work.columns:
        work["Statistic"] = work["Statistic"].map(lambda x: _format_scalar(x, decimals=3))
    if "Effect Size" in work.columns:
        work["Effect Size"] = work["Effect Size"].map(lambda x: _format_scalar(x, decimals=3))
    for p_col in ("p-value", "FDR p-value"):
        if p_col in work.columns:
            work[p_col] = work[p_col].map(lambda x: _format_scientific(x, digits=2))
    # Avoid visually ambiguous blank cells in paper tables.
    work = work.fillna("--")
    for col in work.columns:
        work[col] = work[col].replace("", "--")
    return work


def build_family_temporal_scope_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build family temporal scope table with year-only bounds."""
    work = raw_df.copy()
    if "first_seen" in work.columns:
        first = pd.to_datetime(work["first_seen"], errors="coerce", utc=True).dt.year
        work["First Seen"] = first.fillna(0).astype(int).replace({0: ""})
    if "last_seen" in work.columns:
        last = pd.to_datetime(work["last_seen"], errors="coerce", utc=True).dt.year
        work["Last Seen"] = last.fillna(0).astype(int).replace({0: ""})
    rename_map = {
        "family_canonical": "Family",
        "sample_count": "Samples",
    }
    work = work.rename(columns=rename_map)
    wanted = [col for col in ("Family", "Samples", "First Seen", "Last Seen") if col in work.columns]
    out = work[wanted].copy()
    if "Samples" in out.columns:
        out["Samples"] = pd.to_numeric(out["Samples"], errors="coerce").fillna(0).astype(int).astype(str)
    return out


def build_cohort_summary_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Build cohort summary table with integer/percentage formatting."""
    work = raw_df.copy()
    if {"Metric", "Value"}.issubset(work.columns):
        metric_col = "Metric"
        value_col = "Value"
    else:
        return work
    work[metric_col] = work[metric_col].astype(str)
    value_map = {}
    for _, row in work.iterrows():
        metric = str(row[metric_col]).strip().lower()
        value = row[value_col]
        if "share" in metric:
            value_map[metric] = _format_scalar(value, percent=True)
        elif any(token in metric for token in ("samples", "families", "types", "year", "window")):
            try:
                value_map[metric] = str(int(float(value)))
            except Exception:
                value_map[metric] = value
        else:
            value_map[metric] = value
    work[value_col] = [value_map.get(str(m).strip().lower(), v) for m, v in zip(work[metric_col], work[value_col])]
    return work


__all__ = [
    "LatexTableSpec",
    "build_cohort_summary_table",
    "build_dangerous_stats_table",
    "build_family_temporal_scope_table",
    "build_feature_ablation_table",
    "build_model_comparison_table",
    "latex_escape",
    "normalize_model_name",
    "render_tabular",
    "write_tabular",
]
