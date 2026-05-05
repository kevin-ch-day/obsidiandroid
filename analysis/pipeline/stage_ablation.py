"""Ablation experiment helpers for leakage sensitivity evaluation."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
import shutil

import pandas as pd
from pandas.api.types import is_numeric_dtype

from analysis.matrix.av_binary_matrix_builder import METADATA_COLS as AV_METADATA_COLS
from config import app_config
from ml_classification.ml_utils import distribution_reporter
from ml_classification.training import pipeline_core
from ml_classification.vectorization import feature_vector_builder
from utils import display_utils as du
from utils import ml_console
from utils.runtime_paths import resolve_diagnostics_dir

from analysis.diagnostics.ablation_cohort_diagnostics import write_ablation_cohort_gap_artifacts
from obsidiandroid.common import output_hygiene as oh


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
    cohort_sample_ids: list[int] | None = None,
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
        cohort_sample_ids=cohort_sample_ids,
    )


def _vendor_semantic_subset(encoded_df: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Drop vendor field groups from an encoded vendor-only matrix (columns are low_snake_case_*)."""
    if not isinstance(encoded_df, pd.DataFrame) or encoded_df.empty:
        return encoded_df if isinstance(encoded_df, pd.DataFrame) else pd.DataFrame()
    if variant == "no_parsed_family":
        drop_parsed, drop_threat, drop_malware_type = True, False, False
    elif variant == "no_family_no_type":
        drop_parsed, drop_threat, drop_malware_type = True, True, True
    else:
        return encoded_df.copy()
    keep: list[str | int] = []
    for col in encoded_df.columns:
        low = str(col).lower()
        if drop_parsed and "parsed_family" in low:
            continue
        if drop_threat and "threat_class" in low:
            continue
        if drop_malware_type and "malware_type" in low:
            continue
        keep.append(col)
    if not keep:
        return pd.DataFrame()
    out = encoded_df[keep].copy()
    for key, val in getattr(encoded_df, "attrs", {}).items():
        out.attrs[key] = val
    return out


def _build_binary_detection_only_matrix(binary_matrix: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(binary_matrix, pd.DataFrame) or binary_matrix.empty:
        return pd.DataFrame()
    if "sample_id" not in binary_matrix.columns:
        return pd.DataFrame()
    eng_cols = [c for c in binary_matrix.columns if c not in AV_METADATA_COLS and c != "sample_id"]
    if not eng_cols:
        return pd.DataFrame()
    out = binary_matrix[["sample_id"] + eng_cols].copy()
    for col in eng_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out.set_index("sample_id")


def _build_consensus_scores_only_matrix(enriched_matrix: pd.DataFrame | None) -> pd.DataFrame:
    """Non-engine numeric aggregates from the enriched AV scan matrix (scores / densities)."""
    if not isinstance(enriched_matrix, pd.DataFrame) or enriched_matrix.empty:
        return pd.DataFrame()
    if "sample_id" not in enriched_matrix.columns:
        return pd.DataFrame()
    skip = set(AV_METADATA_COLS) | {"sample_id"}
    numeric_cols: list[str] = []
    for col in enriched_matrix.columns:
        if col in skip:
            continue
        series = enriched_matrix[col]
        if not is_numeric_dtype(series):
            continue
        nu = pd.to_numeric(series, errors="coerce").dropna()
        if nu.empty:
            continue
        uniq = sorted({float(x) for x in nu.unique().tolist()})
        # Drop per-engine binaries (typically {0.0, 1.0}).
        if len(uniq) <= 3 and uniq and max(uniq) <= 1.0 and min(uniq) >= 0.0:
            continue
        numeric_cols.append(col)
    if not numeric_cols:
        return pd.DataFrame()
    work = enriched_matrix[["sample_id"] + numeric_cols].copy()
    return work.drop_duplicates("sample_id").set_index("sample_id")


def _build_permissions_band_matrix(
    permission_features_df: pd.DataFrame | None, *, subset: str
) -> pd.DataFrame:
    base = _build_permissions_only_matrix(permission_features_df)
    if base.empty:
        return base
    raw_onehot_exclude = {
        "perm__dangerous_count",
        "perm__normal_count",
        "perm__oem_count",
        "perm__total_count",
    }
    if subset == "raw":
        keep = [
            c
            for c in base.columns
            if str(c).startswith("perm__")
            and not str(c).startswith("perm_grp__")
            and str(c) not in raw_onehot_exclude
        ]
    elif subset == "grouped":
        keep = [c for c in base.columns if str(c).startswith("perm_grp__")] + [
            c for c in base.columns if c in raw_onehot_exclude
        ]
    else:
        keep = list(base.columns)
    if not keep:
        return pd.DataFrame(index=base.index)
    subset_df = base[keep].copy()
    subset_df.attrs.update(base.attrs)
    return subset_df


def _build_experiment_matrix_dict(
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    pipeline_results: dict[str, Any] | None,
    cohort_sample_ids: list[int] | None,
) -> dict[str, Any]:
    """Return mapping of experiment names to built feature matrices (pre-reindex)."""
    full_vendor_fields = ["Parsed Family", "Threat Class", "Malware Type"]
    pipelines = pipeline_results if isinstance(pipeline_results, dict) else {}
    cids = cohort_sample_ids

    builders: dict[str, Any] = {}

    builders["vendor_full"] = lambda: _build_vendor_matrix(
        weights_df, parsed_data, full_vendor_fields, extra_features_df=None, cohort_sample_ids=cids
    )
    builders["vendor_no_parsed_family"] = lambda: _build_vendor_matrix(
        weights_df,
        parsed_data,
        ["Threat Class", "Malware Type"],
        extra_features_df=None,
        cohort_sample_ids=cids,
    )

    def _vendor_no_ft() -> pd.DataFrame:
        raw_mat = builders["vendor_full"]()
        if not isinstance(raw_mat, pd.DataFrame) or raw_mat.empty:
            return pd.DataFrame()
        trimmed = _vendor_semantic_subset(raw_mat, variant="no_family_no_type")
        return trimmed

    builders["vendor_no_family_no_type"] = _vendor_no_ft

    builders["vendor_detection_binary_only"] = lambda: _build_binary_detection_only_matrix(
        pipelines.get("binary_matrix")
    )
    builders["vendor_consensus_scores_only"] = lambda: _build_consensus_scores_only_matrix(
        pipelines.get("enriched_matrix")
    )

    builders["permissions_raw"] = lambda: _build_permissions_band_matrix(
        permission_features_df,
        subset="raw",
    )
    builders["permissions_grouped"] = lambda: _build_permissions_band_matrix(
        permission_features_df,
        subset="grouped",
    )

    def _grp_plus_vnf() -> pd.DataFrame:
        gmat = _build_permissions_band_matrix(permission_features_df, subset="grouped")
        if not isinstance(gmat, pd.DataFrame) or gmat.empty:
            return _build_vendor_matrix(
                weights_df,
                parsed_data,
                ["Threat Class", "Malware Type"],
                cohort_sample_ids=cids,
            )
        g_df = gmat.reset_index()
        if "sample_id" not in g_df.columns and gmat.index.name == "sample_id":
            g_df = gmat.rename_axis("sample_id").reset_index()
        return _build_vendor_matrix(
            weights_df,
            parsed_data,
            ["Threat Class", "Malware Type"],
            extra_features_df=g_df,
            cohort_sample_ids=cids,
        )

    builders["permissions_grouped_plus_vendor_no_family"] = _grp_plus_vnf

    builders["full_fused"] = lambda: _build_vendor_matrix(
        weights_df,
        parsed_data,
        full_vendor_fields,
        extra_features_df=permission_features_df,
        cohort_sample_ids=cids,
    )

    return builders


ABLATION_EXPERIMENT_ORDER: tuple[str, ...] = (
    "vendor_full",
    "vendor_no_parsed_family",
    "vendor_no_family_no_type",
    "vendor_detection_binary_only",
    "vendor_consensus_scores_only",
    "permissions_raw",
    "permissions_grouped",
    "permissions_grouped_plus_vendor_no_family",
    "full_fused",
)


def _prepare_training_inputs(
    feature_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    *,
    forced_label_column: str | None = None,
) -> tuple[pd.DataFrame | None, pd.Series | None]:
    aligned_features, labels_df = pipeline_core.align_data(
        feature_df,
        samples_df,
        forced_label_column=forced_label_column,
    )
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
    *,
    label_target: str | None = None,
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
    exp_slug = f"{experiment}__lt_{label_target}" if label_target else experiment
    dst = out_dir / f"confusion_matrix_{run_id}__{exp_slug}__{model_name}.png"
    try:
        shutil.copyfile(src, dst)
        return str(dst)
    except Exception:
        return source_path


def _collect_experiment_rows(
    experiment: str,
    results: dict[str, dict],
    run_id: str,
    *,
    label_target: str = "family_canonical_default",
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
                "label_target": label_target,
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
                    label_target=None if label_target == "family_canonical_default" else label_target,
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
                        "label_target": label_target,
                        "model": model_name,
                        "family": str(family),
                        "precision": metrics.get("precision"),
                        "recall": metrics.get("recall"),
                        "f1_score": metrics.get("f1-score"),
                        "support": metrics.get("support"),
                    }
                )
    return summary_rows, per_family_rows


def _ablation_label_target_stats(
    samples_label_basis: pd.DataFrame,
    label_targets: list[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    """Per ablation label target: class cardinality and support spread (training universe)."""
    out: list[dict[str, Any]] = []
    for slug, forced_col in label_targets:
        col = forced_col
        if slug == "family_canonical_default":
            col = "family_canonical"
        if not col or col not in samples_label_basis.columns:
            continue
        ser = samples_label_basis[col].dropna()
        if ser.empty:
            continue
        vc = ser.astype(str).str.strip().value_counts()
        out.append(
            {
                "label_target": slug,
                "column": col,
                "class_count": int(vc.shape[0]),
                "min_class_support": int(vc.min()),
                "max_class_support": int(vc.max()),
            }
        )
    return out


def run_ablation_experiments(
    samples_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    permission_features_df: pd.DataFrame | None,
    model_list: list[str] | None,
    run_id: str,
    pipeline_results: dict[str, Any] | None = None,
    manifest_context: dict[str, Any] | None = None,
) -> list[str]:
    """Run methodology ablations and export summary artifacts."""
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

    builders = _build_experiment_matrix_dict(
        weights_df,
        parsed_data,
        permission_features_df,
        pipeline_results,
        cohort_sample_ids=frozen_sorted,
    )
    experiments = [
        (name, builders[name])
        for name in ABLATION_EXPERIMENT_ORDER
        if name in builders and callable(builders[name])
    ]
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
        "train_test_split_cache_scoping": (
            "Per-run train/test splits are cached under a key that hashes the feature index, "
            "encoded label vector, test_size, random_state, and split policy — different ablation "
            "label targets therefore do not reuse each other's y assignments."
        ),
        "experiment_matrix_row_counts": [
            {"feature_set": row.get("feature_set"), "raw_matrix_ids": row.get("raw_matrix_ids")}
            for row in gap_table_rows
        ],
    }
    if isinstance(manifest_context, dict):
        manifest_context["_ablation_cohort_gap_summary"] = gap_summary_payload
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
    samples_label_basis = samples_work.copy()
    if {"family_canonical", "type_slug"} <= set(samples_label_basis.columns):
        samples_label_basis["family_within_type"] = (
            samples_label_basis["type_slug"].fillna("unknown").astype(str).str.strip()
            + "::"
            + samples_label_basis["family_canonical"].fillna("unknown").astype(str).str.strip()
        )

    label_targets: list[tuple[str, str | None]] = [("family_canonical_default", None)]
    if bool(getattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", True)):
        label_targets.append(("family_id", "family_id"))
        if "type_slug" in samples_label_basis.columns:
            label_targets.append(("type_slug", "type_slug"))
        if "family_within_type" in samples_label_basis.columns:
            label_targets.append(("family_within_type", "family_within_type"))

    label_stats_snapshot = _ablation_label_target_stats(samples_label_basis, label_targets)
    if isinstance(manifest_context, dict):
        manifest_context["_ablation_label_target_stats"] = label_stats_snapshot

    previous_cv = bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", False))
    previous_cv_rebalance = bool(getattr(app_config, "ENABLE_CV_REBALANCING", False))
    previous_quiet = bool(getattr(app_config, "RUNTIME_QUIET_TRAINING", False))
    if not ablation_cv_enabled:
        setattr(app_config, "ENABLE_CROSS_VALIDATION", False)
        setattr(app_config, "ENABLE_CV_REBALANCING", False)
    setattr(app_config, "RUNTIME_QUIET_TRAINING", True)
    setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True)
    setattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", [])

    schema_audit_snapshot: list[dict[str, Any]] = []
    try:
        for experiment_name, feature_df in experiment_matrices.items():
            for label_slug, forced_col in label_targets:
                combo_id = f"{experiment_name}__lt_{label_slug}"
                try:
                    setattr(app_config, "RUNTIME_EXPERIMENT_ID", combo_id)
                    work_df = feature_df.copy()
                    if not reindex_zero_fill:
                        if "sample_id" in work_df.columns:
                            work_df["sample_id"] = pd.to_numeric(
                                work_df["sample_id"], errors="coerce"
                            )
                            work_df = work_df[work_df["sample_id"].isin(common_ids)].copy()
                        else:
                            idx_series = pd.Series(
                                pd.to_numeric(pd.Index(work_df.index), errors="coerce"),
                                index=work_df.index,
                            )
                            work_df = work_df.loc[idx_series.isin(common_ids)].copy()
                    if work_df.empty:
                        du.print_warning(
                            f"[ABLATION] Skipping '{experiment_name}'/'{label_slug}' "
                            "due to empty filtered feature matrix."
                        )
                        continue
                    x_train, y_train = _prepare_training_inputs(
                        work_df,
                        samples_label_basis,
                        forced_label_column=forced_col,
                    )
                    if x_train is None or y_train is None or x_train.empty:
                        du.print_warning(
                            f"[ABLATION] Skipping '{experiment_name}'/'{label_slug}' due to alignment failure."
                        )
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
                        label_target=label_slug,
                    )
                    summary_rows.extend(rows)
                    per_family_rows.extend(family_rows)
                except Exception as exc:
                    du.print_warning(f"[ABLATION] '{experiment_name}'/'{label_slug}' failed: {exc}")
                finally:
                    setattr(app_config, "RUNTIME_EXPERIMENT_ID", "")
    finally:
        raw_audit = getattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", None)
        if isinstance(raw_audit, list):
            schema_audit_snapshot = list(raw_audit)
        setattr(app_config, "ENABLE_CROSS_VALIDATION", previous_cv)
        setattr(app_config, "ENABLE_CV_REBALANCING", previous_cv_rebalance)
        setattr(app_config, "RUNTIME_QUIET_TRAINING", previous_quiet)
        setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)
        setattr(app_config, "RUNTIME_ABLATION_SCHEMA_AUDIT_ROWS", [])

    audit_cols = [
        "feature_set",
        "model",
        "fit_column_count",
        "predict_column_count",
        "missing_at_predict_count",
        "extra_at_predict_count",
        "status",
    ]
    audit_df = (
        pd.DataFrame(schema_audit_snapshot)
        if schema_audit_snapshot
        else pd.DataFrame(columns=audit_cols)
    )
    if not audit_df.empty:
        audit_df = audit_df.reindex(columns=audit_cols)
    audit_path = _diagnostics_dir() / "ablation_feature_schema_audit.csv"
    audit_df.to_csv(audit_path, index=False)
    artifact_paths.append(str(audit_path))
    du.print_info(f"[ABLATION] Feature schema audit: {audit_path}")

    if not summary_rows:
        return artifact_paths

    summary_df = pd.DataFrame(summary_rows)
    summary_df = _apply_leakage_delta(summary_df)
    per_family_df = pd.DataFrame(per_family_rows)
    out_dir = _diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ablation_run = str(getattr(app_config, "RUNTIME_RUN_ID", run_id) or run_id)
    sum_csv = summary_df.to_csv(index=False)
    summary_mirror = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=f"ablation_summary_{ablation_run}.csv",
        csv_text=sum_csv,
        global_latest_name="ablation_summary.latest.csv",
    )
    summary_path = summary_mirror[0]
    _print_ablation_terminal_summary(summary_df)
    if not per_family_df.empty:
        pf_csv = per_family_df.to_csv(index=False)
        pf_mirror = oh.mirror_csv_text_run_then_global(
            diagnostics_dir=out_dir,
            run_filename=f"ablation_per_family_{ablation_run}.csv",
            csv_text=pf_csv,
            global_latest_name="ablation_per_family.latest.csv",
        )
        artifact_paths.append(str(pf_mirror[0]))
    artifact_paths.extend([str(summary_path)])
    du.print_info(f"[ABLATION] Exported summary: {summary_path}")
    if isinstance(manifest_context, dict):
        from analysis.observability import api as obs_api

        obs_api.record_ablation_summary(
            manifest_context,
            frozen_cohort_ids=len(base_ids),
            training_universe_ids=len(common_ids),
            experiments_built=len(experiment_matrices),
            label_target_stats=label_stats_snapshot,
            summary_csv_path=str(summary_path),
        )
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
    out["vendor_leakage_delta_vs_vendor_full"] = None
    if "label_target" not in out.columns:
        baseline = out[out["experiment"] == "vendor_full"][["model", "macro_f1_score"]]
        if baseline.empty:
            baseline = out[out["experiment"] == "vendor_only"][["model", "macro_f1_score"]]
        if not baseline.empty:
            baseline_map = {
                str(row["model"]): float(row["macro_f1_score"])
                for _, row in baseline.iterrows()
                if pd.notna(row["macro_f1_score"])
            }
            for idx, row in out.iterrows():
                model = str(row.get("model", ""))
                macro_f1 = row.get("macro_f1_score")
                if model in baseline_map and pd.notna(macro_f1):
                    delta = round(float(macro_f1) - baseline_map[model], 6)
                    out.at[idx, "leakage_sensitivity_delta"] = delta
                    out.at[idx, "vendor_leakage_delta_vs_vendor_full"] = delta
        return out

    for lt_label in sorted(out["label_target"].dropna().unique()):
        lt_frame = out[out["label_target"] == lt_label]
        baseline = lt_frame[lt_frame["experiment"] == "vendor_full"][["model", "macro_f1_score"]]
        if baseline.empty:
            continue
        baseline_map = {
            str(row["model"]): float(row["macro_f1_score"])
            for _, row in baseline.iterrows()
            if pd.notna(row["macro_f1_score"])
        }
        for idx, row in out.iterrows():
            if row.get("label_target") != lt_label:
                continue
            model = str(row.get("model", ""))
            macro_f1 = row.get("macro_f1_score")
            if model in baseline_map and pd.notna(macro_f1):
                delta = round(float(macro_f1) - baseline_map[model], 6)
                out.at[idx, "leakage_sensitivity_delta"] = delta
                out.at[idx, "vendor_leakage_delta_vs_vendor_full"] = delta
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
        frame.get(
            "vendor_leakage_delta_vs_vendor_full",
            frame.get("leakage_sensitivity_delta", pd.Series([None] * len(frame))),
        ),
        errors="coerce",
    )
    display_cols = [
        col
        for col in (
            "experiment",
            "label_target",
            "model",
            "macro_f1_score",
            "delta_vs_vendor_only",
        )
        if col in frame.columns
    ]
    if not display_cols:
        return
    du.print_table(
        frame[display_cols].rename(
            columns={
                "experiment": "Feature Set",
                "model": "Model",
                "macro_f1_score": "MacroF1",
                "delta_vs_vendor_only": "Delta vs VendorFull",
            }
        ),
        title="Ablation Summary (Compact)",
        show_index=False,
    )
