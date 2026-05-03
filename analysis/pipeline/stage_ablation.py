"""Ablation experiment helpers for leakage sensitivity evaluation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
import shutil

import pandas as pd

from config import app_config
from ml_classification.ml_utils import distribution_reporter
from ml_classification.training import pipeline_core
from ml_classification.vectorization import feature_vector_builder
from utils import display_utils as du
from utils import ml_console
from utils.runtime_paths import resolve_diagnostics_dir

from analysis.diagnostics.ablation_cohort_diagnostics import write_ablation_cohort_gap_artifacts


class PaperCohortSource(str, Enum):
    """Source modes for paper cohort sample-id loading."""

    RUNTIME_ONLY = "runtime_only"
    DISK_ONLY = "disk_only"
    AUTO = "auto"


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory for current runtime context."""
    return resolve_diagnostics_dir()


def _build_vendor_matrix(
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    include_fields: list[str],
    extra_features_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    score_field = str(getattr(app_config, "FEATURE_SCORE_FIELD", "Final ML Score"))
    if bool(getattr(app_config, "ENABLE_LEAKAGE_SAFE_VENDOR_SCORING", True)):
        leakage_field = str(getattr(app_config, "LEAKAGE_SAFE_SCORE_FIELD", "Leakage Safe Score"))
        if leakage_field in weights_df.columns:
            score_field = leakage_field

    return feature_vector_builder.build_feature_vector(
        weights_df=weights_df,
        parsed_vendor_data=parsed_data,
        top_k=int(getattr(app_config, "FEATURE_TOP_K", 8)),
        score_preference=score_field,
        exclude_categories=list(getattr(app_config, "FEATURE_EXCLUDE_VENDOR_CATEGORIES", [])),
        min_score=getattr(app_config, "FEATURE_MIN_VENDOR_SCORE", 0.0),
        include_fields=include_fields,
        encoding="category",
        verbose=False,
        extra_features_df=extra_features_df,
    )


def _prepare_training_inputs(
    feature_df: pd.DataFrame,
    samples_df: pd.DataFrame,
) -> tuple[pd.DataFrame | None, pd.Series | None]:
    aligned_features, labels_df = pipeline_core.align_data(feature_df, samples_df)
    if aligned_features is None or labels_df is None:
        return None, None

    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    group_label = (
        "other" if bool(getattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False)) else None
    )
    aligned_features, labels_df, _, _ = distribution_reporter.apply_min_family_support(
        features_df=aligned_features,
        labels_df=labels_df,
        min_support=min_support,
        group_label=group_label,
    )
    aligned_features = pipeline_core._prune_low_information_features(aligned_features)  # pylint: disable=protected-access
    aligned_features = pipeline_core._prune_potential_leakage_features(  # pylint: disable=protected-access
        aligned_features,
        labels_df,
    )
    return aligned_features, labels_df


def _extract_feature_sample_ids(feature_df: pd.DataFrame) -> set[int]:
    """Extract normalized sample IDs from feature matrix index/column."""
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return set()
    if "sample_id" in feature_df.columns:
        ids = pd.to_numeric(feature_df["sample_id"], errors="coerce")
    else:
        ids = pd.to_numeric(pd.Index(feature_df.index), errors="coerce")
    return set(ids.dropna().astype(int).tolist())


def reindex_ablation_features_to_frozen_ids(
    feature_df: pd.DataFrame,
    frozen_sorted: list[int],
) -> pd.DataFrame:
    """Reindex a feature matrix to the frozen paper cohort, filling missing rows with 0.

    Decouples ablation **feature effects** from **row drops** when vendor-only matrices omit
    samples that lack parsed top-k vendor rows.
    """
    if not frozen_sorted:
        return pd.DataFrame()
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return pd.DataFrame(index=frozen_sorted)

    work = feature_df.copy()
    if "sample_id" in work.columns:
        work = work.drop_duplicates("sample_id", keep="last")
        sid = pd.to_numeric(work["sample_id"], errors="coerce")
        work = work.assign(_abl_sid=sid).dropna(subset=["_abl_sid"])
        work["_abl_sid"] = work["_abl_sid"].astype(int)
        work = work.set_index("_abl_sid")
        drop_cols = [c for c in work.columns if str(c).startswith("_abl_")]
        if drop_cols:
            work = work.drop(columns=drop_cols, errors="ignore")
    else:
        work.index = pd.to_numeric(work.index, errors="coerce")
        work = work[~pd.Index(work.index).isna()]
        work = work[~work.index.duplicated(keep="last")]

    work = work.reindex(frozen_sorted)
    return work.fillna(0)


def _print_ablation_cohort_integrity_table(rows: list[dict[str, Any]]) -> None:
    """Compact terminal table: cohort vs raw matrix vs reindexed alignment."""
    if not rows or ml_console.is_minimal():
        return
    frame = pd.DataFrame(rows)
    rename_map = {
        "feature_set": "Feature Set",
        "expected_ids": "Expected IDs",
        "raw_matrix_ids": "Matrix IDs",
        "missing_vs_expected": "Missing IDs",
        "final_aligned_ids": "Final Aligned IDs",
        "status": "Status",
    }
    cols = [c for c in rename_map if c in frame.columns]
    if not cols:
        return
    du.print_table(
        frame[cols].rename(columns=rename_map),
        title="Ablation cohort integrity (pre-train)",
        show_index=False,
    )


def _load_paper_cohort_sample_ids(
    samples_df: pd.DataFrame,
    source: PaperCohortSource = PaperCohortSource.AUTO,
    cohort_path: Path | None = None,
) -> set[int]:
    """Load paper cohort IDs from runtime rows and/or frozen disk snapshot.

    Args:
        samples_df: Runtime sample frame.
        source: Loading source mode.
        cohort_path: Optional explicit cohort path when disk loading is used.

    Returns:
        Set of normalized sample IDs.
    """
    resolved_path = cohort_path or Path(
        str(
            getattr(
                app_config,
                "PAPER_COHORT_SAMPLE_IDS_FILE",
                "output/diagnostics/paper_cohort_sample_ids.csv",
            )
        )
    )
    allow_disk = source in {PaperCohortSource.AUTO, PaperCohortSource.DISK_ONLY}
    if allow_disk and resolved_path.exists():
        try:
            df = pd.read_csv(resolved_path)
            if "sample_id" in df.columns:
                ids = pd.to_numeric(df["sample_id"], errors="coerce").dropna().astype(int)
                return set(ids.tolist())
        except Exception:
            if source == PaperCohortSource.DISK_ONLY:
                return set()
    if source == PaperCohortSource.DISK_ONLY:
        return set()
    if "sample_id" not in samples_df.columns:
        return set()
    ids = pd.to_numeric(samples_df["sample_id"], errors="coerce").dropna().astype(int)
    return set(ids.tolist())


def _copy_confusion_matrix_artifact(
    source_path: str | None,
    run_id: str,
    experiment: str,
    model_name: str,
) -> str | None:
    """Copy confusion matrix to a run/experiment-specific filename to avoid overwrite."""
    if not source_path:
        return None
    src = Path(str(source_path))
    if not src.exists():
        return source_path
    # If source is already run-scoped (Phase A), reuse it directly.
    run_scoped_token = str(Path("runs") / run_id).replace("\\", "/").lower()
    if run_scoped_token in str(src).replace("\\", "/").lower():
        return str(src)
    out_dir = Path(app_config.DEFAULT_OUTPUT_DIR) / "conf_matrices"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"confusion_matrix_{run_id}__{experiment}__{model_name}.png"
    try:
        shutil.copyfile(src, dst)
        return str(dst)
    except Exception:
        return source_path


def _collect_experiment_rows(
    experiment: str,
    results: dict[str, dict],
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    per_family_rows: list[dict[str, Any]] = []

    for model_name, result in sorted(results.items()):
        evaluation = result.get("evaluation", {}) if isinstance(result, dict) else {}
        metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
        class_report = metadata.get("classification_report", {}) if isinstance(metadata, dict) else {}
        summary_rows.append(
            {
                "experiment": experiment,
                "model": model_name,
                "accuracy": evaluation.get("accuracy"),
                "macro_f1_score": evaluation.get("macro_f1_score"),
                "macro_precision": evaluation.get("macro_precision"),
                "macro_recall": evaluation.get("macro_recall"),
                "samples_tested": evaluation.get("samples_tested"),
                "confusion_matrix_path": _copy_confusion_matrix_artifact(
                    source_path=evaluation.get("confusion_matrix_path"),
                    run_id=run_id,
                    experiment=experiment,
                    model_name=model_name,
                ),
            }
        )

        if isinstance(class_report, dict):
            for family, metrics in class_report.items():
                if not isinstance(metrics, dict):
                    continue
                if family in {"accuracy", "macro avg", "weighted avg"}:
                    continue
                per_family_rows.append(
                    {
                        "experiment": experiment,
                        "model": model_name,
                        "family": str(family),
                        "precision": metrics.get("precision"),
                        "recall": metrics.get("recall"),
                        "f1_score": metrics.get("f1-score"),
                        "support": metrics.get("support"),
                    }
                )
    return summary_rows, per_family_rows


def run_ablation_experiments(
    samples_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    model_list: list[str] | None,
    run_id: str,
) -> list[str]:
    """Run methodology ablations and export summary artifacts."""
    experiments = [
        ("vendor_only", lambda: _build_vendor_matrix(weights_df, parsed_data, ["Parsed Family", "Threat Class", "Malware Type"])),
        ("vendor_no_parsed_family", lambda: _build_vendor_matrix(weights_df, parsed_data, ["Threat Class", "Malware Type"])),
        ("permissions_only", lambda: _build_permissions_only_matrix(permission_features_df)),
        (
            "vendor_permissions_fused",
            lambda: _build_vendor_matrix(
                weights_df,
                parsed_data,
                ["Parsed Family", "Threat Class", "Malware Type"],
                extra_features_df=permission_features_df,
            ),
        ),
    ]

    selected_models = list(model_list or getattr(app_config, "ABLATION_MODEL_LIST", []) or [])
    ablation_cv_enabled = bool(getattr(app_config, "ENABLE_ABLATION_CROSS_VALIDATION", False))
    ablation_save_models = bool(getattr(app_config, "ENABLE_ABLATION_MODEL_EXPORT", False))
    artifact_paths: list[str] = []
    summary_rows: list[dict[str, Any]] = []
    per_family_rows: list[dict[str, Any]] = []

    if not ml_console.is_minimal():
        du.print_subheader("Ablation Experiments")

    reindex_zero_fill = bool(getattr(app_config, "ABLATION_COHORT_REINDEX_ZERO_FILL", True))
    strict_evidence = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    if (strict_evidence or paper_mode) and not reindex_zero_fill:
        du.print_error(
            "[ABLATION] Evidence/paper mode requires ABLATION_COHORT_REINDEX_ZERO_FILL=True "
            "so ablations do not mix row-drop effects with feature ablations."
        )
        return artifact_paths

    base_ids = _load_paper_cohort_sample_ids(samples_df)
    if not base_ids:
        du.print_warning("[ABLATION] Empty frozen cohort — skipping ablations.")
        return artifact_paths

    frozen_sorted = sorted(base_ids)
    experiment_matrices_raw: dict[str, pd.DataFrame] = {}
    for experiment_name, builder in experiments:
        try:
            feature_df = builder()
            if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
                du.print_warning(f"[ABLATION] Skipping '{experiment_name}' due to empty feature matrix.")
                continue
            experiment_matrices_raw[experiment_name] = feature_df
        except Exception as exc:
            du.print_warning(f"[ABLATION] '{experiment_name}' failed during build: {exc}")

    if not experiment_matrices_raw:
        return artifact_paths

    gap_table_rows: list[dict[str, Any]] = []
    missing_long_rows: list[dict[str, Any]] = []
    for exp_name, raw_df in experiment_matrices_raw.items():
        raw_ids = _extract_feature_sample_ids(raw_df)
        missing_ct = len(set(base_ids) - raw_ids)
        gap_table_rows.append(
            {
                "feature_set": exp_name,
                "expected_ids": len(base_ids),
                "raw_matrix_ids": len(raw_ids),
                "missing_vs_expected": missing_ct,
                "final_aligned_ids": len(frozen_sorted) if reindex_zero_fill else None,
                "status": "reindex_zero_fill" if reindex_zero_fill else "raw_matrix_only",
            }
        )
        for sid in sorted(set(base_ids) - raw_ids):
            missing_long_rows.append({"feature_set": exp_name, "sample_id": sid})

    missing_df = pd.DataFrame(missing_long_rows) if missing_long_rows else pd.DataFrame()

    experiment_matrices: dict[str, pd.DataFrame] = {}
    if reindex_zero_fill:
        du.print_info(
            "[ABLATION] Reindexing all feature sets to frozen cohort with zero-fill "
            f"({len(frozen_sorted)} sample_ids)."
        )
        for exp_name, raw_df in experiment_matrices_raw.items():
            reindexed = reindex_ablation_features_to_frozen_ids(raw_df, frozen_sorted)
            if reindexed.shape[1] == 0:
                du.print_warning(f"[ABLATION] '{exp_name}' has zero columns after reindex — skipping.")
                continue
            experiment_matrices[exp_name] = reindexed
        for exp_name, df in list(experiment_matrices.items()):
            idx_set = set(pd.to_numeric(df.index, errors="coerce").dropna().astype(int).tolist())
            if idx_set != set(frozen_sorted) or len(df) != len(frozen_sorted):
                msg = (
                    f"[ABLATION] Post-reindex index mismatch for '{exp_name}': "
                    f"rows={len(df)} expected={len(frozen_sorted)}."
                )
                if strict_evidence or paper_mode:
                    du.print_error(msg)
                    return artifact_paths
                du.print_warning(msg)
        common_ids = set(frozen_sorted)
    else:
        experiment_matrices = dict(experiment_matrices_raw)
        common_ids = set(base_ids)
        for df in experiment_matrices.values():
            common_ids &= _extract_feature_sample_ids(df)
        require_frozen_universe = bool(getattr(app_config, "ABLATION_REQUIRE_FROZEN_UNIVERSE", True))
        if require_frozen_universe and common_ids != base_ids:
            mismatch_count = max(0, len(base_ids) - len(common_ids))
            base_count = max(1, len(base_ids))
            mismatch_ratio = mismatch_count / base_count
            allowed_ratio = float(getattr(app_config, "ABLATION_MAX_MISMATCH_RATIO", 0.01))
            if mismatch_ratio > allowed_ratio:
                du.print_error(
                    "[ABLATION] Frozen cohort mismatch detected. "
                    f"base_ids={len(base_ids)} common_ids={len(common_ids)} "
                    f"mismatch={mismatch_count} ({mismatch_ratio:.2%}). "
                    "Enable ABLATION_COHORT_REINDEX_ZERO_FILL=True or raise ABLATION_MAX_MISMATCH_RATIO."
                )
                return artifact_paths
            du.print_warning(
                "[ABLATION] Minor frozen-cohort mismatch tolerated. "
                f"base_ids={len(base_ids)} common_ids={len(common_ids)} "
                f"mismatch={mismatch_count} ({mismatch_ratio:.2%})"
            )
        if not common_ids:
            du.print_warning("[ABLATION] No common sample_id universe across experiments.")
            return artifact_paths

    du.print_info(f"[ABLATION] Training sample universe: {len(common_ids)} sample_ids")

    for row in gap_table_rows:
        row["final_aligned_ids"] = len(common_ids)
        row["input_label_sample_ids"] = len(base_ids)
        if reindex_zero_fill:
            row["status"] = "OK"

    gap_summary_payload = {
        "ablation_cohort_reindex_zero_fill": reindex_zero_fill,
        "strict_evidence_or_paper_mode": bool(strict_evidence or paper_mode),
        "expected_frozen_cohort_size": len(base_ids),
        "final_training_universe_size": len(common_ids),
    }
    json_p, md_p, csv_p = write_ablation_cohort_gap_artifacts(
        diagnostics_dir=_diagnostics_dir(),
        run_id=run_id,
        gap_table_rows=gap_table_rows,
        summary=gap_summary_payload,
        missing_ids_long=missing_df if not missing_df.empty else None,
    )
    artifact_paths.append(str(json_p))
    artifact_paths.append(str(md_p))
    if csv_p is not None:
        artifact_paths.append(str(csv_p))

    _print_ablation_cohort_integrity_table(gap_table_rows)

    samples_work = samples_df.copy()
    samples_work["sample_id"] = pd.to_numeric(samples_work["sample_id"], errors="coerce")
    samples_work = samples_work[samples_work["sample_id"].isin(common_ids)].copy()

    previous_cv = bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", False))
    previous_cv_rebalance = bool(getattr(app_config, "ENABLE_CV_REBALANCING", False))
    previous_quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if not ablation_cv_enabled:
        setattr(app_config, "ENABLE_CROSS_VALIDATION", False)
        setattr(app_config, "ENABLE_CV_REBALANCING", False)
    setattr(app_config, "RUNTIME_QUIET_TRAINING", True)
    setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True)

    try:
        for experiment_name, feature_df in experiment_matrices.items():
            try:
                setattr(app_config, "RUNTIME_EXPERIMENT_ID", experiment_name)
                work_df = feature_df.copy()
                if not reindex_zero_fill:
                    if "sample_id" in work_df.columns:
                        work_df["sample_id"] = pd.to_numeric(work_df["sample_id"], errors="coerce")
                        work_df = work_df[work_df["sample_id"].isin(common_ids)].copy()
                    else:
                        idx_series = pd.Series(
                            pd.to_numeric(pd.Index(work_df.index), errors="coerce"),
                            index=work_df.index,
                        )
                        work_df = work_df.loc[idx_series.isin(common_ids)].copy()
                if work_df.empty:
                    du.print_warning(f"[ABLATION] Skipping '{experiment_name}' due to empty filtered feature matrix.")
                    continue
                x_train, y_train = _prepare_training_inputs(work_df, samples_work)
                if x_train is None or y_train is None or x_train.empty:
                    du.print_warning(f"[ABLATION] Skipping '{experiment_name}' due to alignment failure.")
                    continue
                results, _ = pipeline_core.train_models(
                    x_train,
                    y_train,
                    models=selected_models or None,
                    save_model=ablation_save_models,
                )
                rows, family_rows = _collect_experiment_rows(
                    experiment_name,
                    results,
                    run_id=run_id,
                )
                summary_rows.extend(rows)
                per_family_rows.extend(family_rows)
            except Exception as exc:
                du.print_warning(f"[ABLATION] '{experiment_name}' failed: {exc}")
            finally:
                setattr(app_config, "RUNTIME_EXPERIMENT_ID", "")
    finally:
        setattr(app_config, "ENABLE_CROSS_VALIDATION", previous_cv)
        setattr(app_config, "ENABLE_CV_REBALANCING", previous_cv_rebalance)
        setattr(app_config, "RUNTIME_QUIET_TRAINING", previous_quiet)
        setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)

    if not summary_rows:
        return artifact_paths

    summary_df = pd.DataFrame(summary_rows)
    summary_df = _apply_leakage_delta(summary_df)
    per_family_df = pd.DataFrame(per_family_rows)
    out_dir = _diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "ablation_summary.csv"
    per_family_path = out_dir / "ablation_per_family.csv"
    latest_summary = out_dir / "ablation_summary.latest.csv"
    latest_per_family = out_dir / "ablation_per_family.latest.csv"
    summary_df.to_csv(summary_path, index=False)
    summary_df.to_csv(latest_summary, index=False)
    _print_ablation_terminal_summary(summary_df)
    if not per_family_df.empty:
        per_family_df.to_csv(per_family_path, index=False)
        per_family_df.to_csv(latest_per_family, index=False)
        artifact_paths.append(str(per_family_path))
    artifact_paths.extend([str(summary_path)])
    du.print_info(f"[ABLATION] Exported summary: {summary_path}")
    return artifact_paths


def _build_permissions_only_matrix(permission_features_df: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(permission_features_df, pd.DataFrame) or permission_features_df.empty:
        return pd.DataFrame()
    if "sample_id" not in permission_features_df.columns:
        return pd.DataFrame()
    matrix = permission_features_df.drop_duplicates("sample_id").set_index("sample_id").copy()
    for col in matrix.columns:
        matrix[col] = pd.to_numeric(matrix[col], errors="coerce").fillna(0)
    return matrix


def _apply_leakage_delta(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty or "macro_f1_score" not in summary_df.columns:
        return summary_df
    out = summary_df.copy()
    out["leakage_sensitivity_delta"] = None
    baseline = out[out["experiment"] == "vendor_only"][["model", "macro_f1_score"]]
    if baseline.empty:
        return out
    baseline_map = {
        str(row["model"]): float(row["macro_f1_score"])
        for _, row in baseline.iterrows()
        if pd.notna(row["macro_f1_score"])
    }
    for idx, row in out.iterrows():
        model = str(row.get("model", ""))
        macro_f1 = row.get("macro_f1_score")
        if model in baseline_map and pd.notna(macro_f1):
            out.at[idx, "leakage_sensitivity_delta"] = round(float(macro_f1) - baseline_map[model], 6)
    return out


def _print_ablation_terminal_summary(summary_df: pd.DataFrame) -> None:
    """Print compact ablation results suitable for research terminal mode."""
    if summary_df.empty or ml_console.is_minimal():
        return
    frame = summary_df.copy()
    for col in ("macro_f1_score", "accuracy"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["macro_f1_score"])
    if frame.empty:
        return
    frame = frame.sort_values(["model", "macro_f1_score"], ascending=[True, False]).copy()
    frame["delta_vs_vendor_only"] = pd.to_numeric(
        frame.get("leakage_sensitivity_delta", pd.Series([None] * len(frame))),
        errors="coerce",
    )
    display_cols = [col for col in ("experiment", "model", "macro_f1_score", "delta_vs_vendor_only") if col in frame.columns]
    if not display_cols:
        return
    du.print_table(
        frame[display_cols].rename(
            columns={
                "experiment": "Feature Set",
                "model": "Model",
                "macro_f1_score": "MacroF1",
                "delta_vs_vendor_only": "Delta vs VendorOnly",
            }
        ),
        title="Ablation Summary (Compact)",
        show_index=False,
    )
