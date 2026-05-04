# Filename: engine_scoring_summary.py
# Purpose  : Generate AV engine scoring summary using detection metadata from DB

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from scipy.stats import zscore

from config import app_config
from database import db_av_engine_detection_totals
from utils import display_utils as du
from obsidiandroid.common import output_paths
from utils.logging import get_logger, log_event

REQUIRED_FIELDS = {
    "engine_name",
    "malicious_count",
    "benign_count",
    "total_scanned",
    "malicious_pct",
    "coverage_pct",
    "threat_signal_score",
}

ML_SCORE_WEIGHTS = {
    "malicious_pct": 0.4,
    "coverage_pct": 0.3,
    "threat_signal_score": 0.3,
}

TIER_LABELS = {
    1: "Tier 1 (High)",
    2: "Tier 2 (Moderate)",
    3: "Tier 3 (Low)",
    4: "Tier 4 (Weak)",
    5: "Tier 5 (Poor)",
}

SUMMARY_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.evaluation.engine_scoring_summary",
    "analysis",
)


def build_av_engine_scoring_summary_from_db() -> pd.DataFrame:
    """Build and return engine scoring summary using detection metadata from DB."""
    log_event(SUMMARY_LOGGER, "engine_summary_start", event_id="SUMMARY_001")

    try:
        engine_df = db_av_engine_detection_totals.get_engine_detection_totals(as_dataframe=True)
    except Exception as exc:
        du.print_error(f"[FATAL] Failed to query detection totals: {exc}")
        log_event(
            SUMMARY_LOGGER,
            "engine_summary_failed",
            event_id="SUMMARY_500",
            reason="query_failed",
            error=str(exc),
        )
        return pd.DataFrame()

    if not isinstance(engine_df, pd.DataFrame) or engine_df.empty:
        du.print_error("[FAIL] Engine metadata query failed or returned no rows.")
        log_event(
            SUMMARY_LOGGER,
            "engine_summary_failed",
            event_id="SUMMARY_404",
            reason="empty_input",
        )
        return pd.DataFrame()

    missing = REQUIRED_FIELDS - set(engine_df.columns)
    for col in missing:
        engine_df[col] = 0.0

    summary_df = _compute_engine_scores(engine_df)

    if summary_df.empty:
        du.print_error("[FAIL] Scoring summary could not be built.")
        log_event(
            SUMMARY_LOGGER,
            "engine_summary_failed",
            event_id="SUMMARY_402",
            reason="empty_summary",
        )
        return pd.DataFrame()

    export_paths = _export_summary_log(summary_df)
    _print_summary_context(
        engine_df=engine_df,
        summary_df=summary_df,
        export_paths=export_paths,
    )
    du.print_success(f"[DONE] Engine scoring summary completed for {len(summary_df)} engines.")
    log_event(
        SUMMARY_LOGGER,
        "engine_summary_complete",
        event_id="SUMMARY_200",
        rows=int(summary_df.shape[0]),
        columns=int(summary_df.shape[1]),
    )
    return summary_df


def _compute_engine_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute ML readiness scores and assign scoring tiers."""
    try:
        if not _normalize_numeric_fields(df, list(ML_SCORE_WEIGHTS.keys())):
            return pd.DataFrame()

        for field in ML_SCORE_WEIGHTS:
            df[f"{field}_norm"] = _min_max_scale(df[field])

        df["ML Readiness Score"] = _calculate_readiness_score(df, ML_SCORE_WEIGHTS)
        df["z_score"] = zscore(df["ML Readiness Score"].fillna(0.0))

        q1 = df["ML Readiness Score"].quantile(0.25)
        q3 = df["ML Readiness Score"].quantile(0.75)
        iqr = q3 - q1
        df["iqr_flag"] = (
            (df["ML Readiness Score"] < q1 - 1.5 * iqr)
            | (df["ML Readiness Score"] > q3 + 1.5 * iqr)
        ).astype(int)

        _assign_tiers(df)

        df["high_precision_flag"] = (df["malicious_pct"] >= 80).astype(int)
        df["low_coverage_flag"] = (df["coverage_pct"] < 50).astype(int)
        df["contributor_flag"] = (
            (df["ML Readiness Score"] > df["ML Readiness Score"].mean())
            & (df["z_score"] > 0)
        ).astype(int)

        _log_summary_stats(df)
        _analyze_metric_relationships(df)

        return df[
            [
                "engine_name",
                "malicious_count",
                "benign_count",
                "total_scanned",
                "malicious_pct",
                "coverage_pct",
                "threat_signal_score",
                "malicious_pct_norm",
                "coverage_pct_norm",
                "threat_signal_score_norm",
                "ML Readiness Score",
                "z_score",
                "Detection Tier",
                "Tier Label",
                "high_precision_flag",
                "low_coverage_flag",
                "contributor_flag",
                "iqr_flag",
            ]
        ]

    except Exception as exc:
        du.print_error(f"[ERROR] Engine score computation failed: {exc}")
        log_event(
            SUMMARY_LOGGER,
            "engine_score_compute_failed",
            event_id="SUMMARY_501",
            error=str(exc),
        )
        return pd.DataFrame()


def _normalize_numeric_fields(df: pd.DataFrame, fields: list) -> bool:
    """Ensure all numeric scoring fields are float-ready and non-null."""
    missing = [col for col in fields if col not in df.columns]
    if missing:
        du.print_error(f"[FAIL] Missing required scoring fields: {missing}")
        log_event(
            SUMMARY_LOGGER,
            "engine_score_missing_fields",
            event_id="SUMMARY_410",
            missing_fields=missing,
        )
        return False

    for col in fields:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).round(4)
    return True


def _calculate_readiness_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    """Compute weighted readiness score from normalized fields."""
    normalized_fields = [f"{field}_norm" for field in weights]
    weighted = sum(
        df[norm_field] * weights[norm_field.replace("_norm", "")]
        for norm_field in normalized_fields
    )
    return (weighted * 100.0).round(4)


def _min_max_scale(series: pd.Series) -> pd.Series:
    """Min-max normalize a numeric series to [0,1]."""
    vals = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    min_val = vals.min()
    max_val = vals.max()
    if max_val <= min_val:
        return pd.Series(0.0, index=vals.index)
    return (vals - min_val) / (max_val - min_val)


def _assign_tiers(df: pd.DataFrame):
    """Assign quantile-based or threshold-based tiers."""
    try:
        scores = df["ML Readiness Score"].astype(float)

        if bool(getattr(app_config, "ENABLE_ABSOLUTE_ENGINE_TIERING", True)):
            thresholds = getattr(app_config, "ENGINE_TIER_THRESHOLDS", {}) or {}
            high = float(thresholds.get("high", 80.0))
            moderate = float(thresholds.get("moderate", 60.0))
            low = float(thresholds.get("low", 40.0))
            weak = float(thresholds.get("weak", 20.0))

            def score_to_tier(score: float) -> int:
                if score >= high:
                    return 1
                if score >= moderate:
                    return 2
                if score >= low:
                    return 3
                if score >= weak:
                    return 4
                return 5

            df["Detection Tier"] = scores.apply(score_to_tier).astype(int)
            df["Tier Label"] = df["Detection Tier"].map(TIER_LABELS)
            return

        if scores.nunique() < 3:
            df["Detection Tier"] = 3
            df["Tier Label"] = TIER_LABELS[3]
            return

        tier_cats, bin_edges = pd.qcut(scores, q=5, retbins=True, duplicates="drop")
        n_bins = len(bin_edges) - 1
        labels = list(range(1, n_bins + 1))
        raw_tiers = tier_cats.cat.rename_categories(labels).astype(int)
        df["Detection Tier"] = (n_bins + 1 - raw_tiers).astype(int)
        df["Tier Label"] = df["Detection Tier"].map(TIER_LABELS)

    except Exception as exc:
        du.print_warning(f"[WARN] Tier assignment failed: {exc}")
        log_event(
            SUMMARY_LOGGER,
            "tier_assignment_failed",
            event_id="SUMMARY_420",
            error=str(exc),
        )
        df["Detection Tier"] = 3
        df["Tier Label"] = TIER_LABELS[3]


def _log_summary_stats(df: pd.DataFrame):
    """Log enhanced readiness statistics to console."""
    du.print_subheader("Score Statistics")

    metrics = {
        "Engine Count": len(df),
        "Score Minimum": df["ML Readiness Score"].min(),
        "Score Maximum": df["ML Readiness Score"].max(),
        "Score Mean": df["ML Readiness Score"].mean(),
        "Score Std Dev": df["ML Readiness Score"].std(),
        "Unique Tiers": df["Detection Tier"].nunique(),
        "Outliers (IQR)": int(df["iqr_flag"].sum()),
    }

    du.print_metric_summary(metrics, title="ML Readiness Score", precision=2)
    du.print_statistical_range("ML Readiness Score", df["ML Readiness Score"].tolist())
    du.print_statistical_range("Malicious %", df["malicious_pct"].tolist())
    du.print_statistical_range("Coverage %", df["coverage_pct"].tolist())
    du.print_statistical_range("Threat Signal Score", df["threat_signal_score"].tolist())
    du.print_tier_distribution(df["Tier Label"], label="Tier Distribution")

    show_top5 = bool(getattr(app_config, "ENGINE_SUMMARY_SHOW_TOP5_TABLE", False))
    if show_top5:
        top_five = df.sort_values("ML Readiness Score", ascending=False).head(5)
        du.print_table(
            top_five,
            title="Top 5 Engines by ML Readiness Score",
            columns=["engine_name", "ML Readiness Score", "Tier Label", "contributor_flag"],
            show_index=False,
        )


def _analyze_metric_relationships(df: pd.DataFrame):
    """Display correlations between core metrics and readiness score."""
    try:
        metrics = ["malicious_pct", "coverage_pct", "threat_signal_score", "ML Readiness Score"]
        corr = df[metrics].corr(method="spearman").round(2)
        readiness_corr = corr["ML Readiness Score"].drop("ML Readiness Score")
        du.print_subheader("Correlation with ML Readiness Score")
        du.print_info(f"[META] Correlation: Spearman, n={len(df)} engines, universe=observed")
        for metric, val in readiness_corr.items():
            du.print_info(f"  - {metric:<20}: {val:>5.2f}")
    except Exception as exc:
        du.print_warning(f"[WARN] Correlation analysis failed: {exc}")
        log_event(
            SUMMARY_LOGGER,
            "correlation_analysis_failed",
            event_id="SUMMARY_430",
            error=str(exc),
        )


def _resolve_summary_export_paths() -> tuple[Path, Path]:
    """Resolve summary export paths by runtime context.

    Returns:
        Tuple of (text_summary_path, csv_summary_path).
    """
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
    runtime_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if run_id and run_id != "unknown":
        if runtime_root and Path(runtime_root).resolve().name == run_id:
            base_dir = Path(runtime_root).resolve() / "diagnostics"
        else:
            base_dir = output_paths.runs_root() / run_id / "diagnostics"
    else:
        base_dir = output_paths.output_root() / "tools"
    base_dir.mkdir(parents=True, exist_ok=True)
    return (
        base_dir / "engine_scoring_summary_log.txt",
        base_dir / "engine_scoring_summary.csv",
    )


def _export_summary_log(df: pd.DataFrame) -> dict[str, str]:
    """Save AV engine scoring summary to text and CSV artifacts."""
    try:
        summary_export_path, summary_csv_path = _resolve_summary_export_paths()
        top_engines = df.sort_values("ML Readiness Score", ascending=False).head(10)

        lines = [
            "[SUMMARY] Top 10 AV Engines by ML Readiness Score",
            "-" * 70,
        ]
        for _, row in top_engines.iterrows():
            lines.append(
                f"{row['engine_name']:25s} -> Score: {row['ML Readiness Score']:.2f} "
                f"| Tier: {row['Tier Label']:18s} | Contributor: {row['contributor_flag']}"
            )

        lines.extend(
            [
                "-" * 70,
                f"Total Engines: {len(df)}",
                f"Score Range : {df['ML Readiness Score'].min():.2f} - {df['ML Readiness Score'].max():.2f}",
                f"Score Mean  : {df['ML Readiness Score'].mean():.2f}",
                f"Score Std   : {df['ML Readiness Score'].std():.2f}",
            ]
        )

        os.makedirs(os.path.dirname(str(summary_export_path)), exist_ok=True)
        with open(summary_export_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        df.sort_values("ML Readiness Score", ascending=False).to_csv(summary_csv_path, index=False)

        du.print_table(
            top_engines,
            title="Top 10 AV Engines by ML Readiness Score",
            columns=["engine_name", "ML Readiness Score", "Tier Label", "contributor_flag"],
            show_index=False,
        )
        du.print_info(f"[EXPORT] Summary log saved to: {summary_export_path.as_posix()}")
        du.print_info(f"[EXPORT] Summary CSV saved to: {summary_csv_path.as_posix()}")
        log_event(
            SUMMARY_LOGGER,
            "summary_log_exported",
            event_id="SUMMARY_210",
            path=str(summary_export_path),
            rows=int(top_engines.shape[0]),
        )
        return {"log_path": str(summary_export_path), "csv_path": str(summary_csv_path)}

    except Exception as exc:
        du.print_warning(f"[WARN] Failed to export summary log: {exc}")
        log_event(
            SUMMARY_LOGGER,
            "summary_log_export_failed",
            event_id="SUMMARY_510",
            error=str(exc),
        )
        return {"log_path": "", "csv_path": ""}


def _print_summary_context(
    *,
    engine_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    export_paths: dict[str, str],
) -> None:
    """Print compact context for engine-scoring execution."""
    observed = int(len(engine_df))
    canonical = int(summary_df["engine_name"].nunique()) if "engine_name" in summary_df.columns else observed
    included_after_gating = int(getattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", 0) or 0)
    if included_after_gating <= 0:
        included_after_gating = canonical
    du.print_subheader("Engine Scoring Context")
    du.print_stat("Source", "DB only (engine scoring table)")
    du.print_stat(
        "Engine Universe",
        f"observed={observed} | canonical={canonical} | included_after_gating={included_after_gating}",
    )
    if export_paths.get("csv_path"):
        du.print_stat("Export", str(export_paths["csv_path"]).replace("\\", "/"))
