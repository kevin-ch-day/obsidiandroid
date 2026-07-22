"""Runtime reporting and artifact helpers for pipeline orchestration."""

from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common import output_paths
from obsidiandroid.common import run_slots
from obsidiandroid.common.cv_fold_config import (
    coerce_stratified_cv_folds_config,
    safe_int_config_value,
)
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.diagnostics import family_tier_model_evaluation
from obsidiandroid.evaluation import accuracy_band_utils


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def runtime_diagnostics_dir() -> Path:
    """Resolve the active diagnostics directory for the current runtime."""
    runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_diag:
        diagnostics_dir = Path(runtime_diag)
    else:
        diagnostics_dir = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir


def parse_key_value_meta(meta_path: Path) -> dict[str, str]:
    """Parse a key=value metadata text file into a dictionary."""
    if not meta_path.exists():
        return {}
    parsed: dict[str, str] = {}
    try:
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
    except Exception:
        return {}
    return parsed


def collect_dependency_versions() -> dict[str, str]:
    """Collect dependency versions for reproducibility metadata."""
    versions = {
        "python": sys.version.split()[0],
        "pandas": str(getattr(pd, "__version__", "unknown")),
    }
    module_alias = {
        "scikit-learn": "sklearn",
        "scikit-posthocs": "scikit_posthocs",
    }
    for package_name in ("numpy", "scikit-learn", "xgboost", "scikit-posthocs"):
        try:
            module_name = module_alias.get(package_name, package_name.replace("-", "_"))
            module = importlib.import_module(module_name)
            versions[package_name] = str(getattr(module, "__version__", "installed"))
        except Exception:
            continue
    return versions


def export_aligned_training_cache(
    aligned_feature_df: pd.DataFrame,
    aligned_labels_df: pd.DataFrame,
    artifact_list: list[str],
) -> None:
    """Persist aligned training inputs for fast retraining workflows."""
    if not bool(getattr(app_config, "EXPORT_ALIGNED_TRAINING_CACHE", True)):
        return
    try:
        feature_path = Path(
            str(
                getattr(
                    app_config,
                    "ALIGNED_FEATURE_CACHE_FILE",
                    "output/diagnostics/aligned_features.latest.csv.gz",
                )
            )
        )
        label_path = Path(
            str(
                getattr(
                    app_config,
                    "ALIGNED_LABEL_CACHE_FILE",
                    "output/diagnostics/aligned_labels.latest.csv",
                )
            )
        )
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        labels_to_write = aligned_labels_df.copy()
        if "sample_id" not in labels_to_write.columns:
            labels_to_write["sample_id"] = labels_to_write.index

        aligned_feature_df.to_csv(feature_path, index=True)
        labels_to_write.to_csv(label_path, index=False)
        artifact_list.extend([str(feature_path), str(label_path)])
        try:
            rid = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "")
            if rid and oh.run_diagnostics_should_omit_latest_duplicate():
                ptr_feat = oh.write_global_latest_pointer(
                    filename="aligned_features.latest.pointer.json",
                    payload={
                        "run_id": rid,
                        "canonical_relative_path": str(feature_path.resolve()),
                        "canonical_label_relative_path": str(label_path.resolve()),
                    },
                )
                artifact_list.append(str(ptr_feat))
        except Exception:
            pass
        du.print_info(
            "[CACHE] Aligned training cache:"
            f"features={du.format_console_path(feature_path)} | "
            f"labels={du.format_console_path(label_path)}"
        )
    except Exception as exc:
        du.print_warning(f"[CACHE] Failed to export aligned training cache: {exc}")


def enforce_duplicate_sha_policy(
    aligned_labels_df: pd.DataFrame,
    run_id: str,
    artifact_list: list[str],
    manifest_context: dict[str, Any],
) -> None:
    """Export duplicate-SHA diagnostics and enforce paper-mode policy."""
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    diagnostics_dir = runtime_diagnostics_dir()

    labels = aligned_labels_df.copy()
    if "sample_id" not in labels.columns:
        labels["sample_id"] = labels.index
    labels["sample_id"] = pd.to_numeric(labels["sample_id"], errors="coerce")
    labels = labels.dropna(subset=["sample_id"]).copy()
    labels["sample_id"] = labels["sample_id"].astype(int)

    if "sha256" not in labels.columns:
        labels["sha256"] = ""
    labels["sha256"] = labels["sha256"].fillna("").astype(str).str.strip().str.lower()

    invalid_sha_mask = ~labels["sha256"].map(lambda value: bool(_SHA256_RE.fullmatch(value)))
    invalid_sha_count = int(invalid_sha_mask.sum())

    deduped = labels.drop_duplicates(subset=["sample_id", "sha256"]).copy()
    join_inflation_rows = int(len(labels) - len(deduped))

    duplicate_groups = (
        deduped.groupby("sha256", dropna=False)
        .agg(
            count_samples=("sample_id", "nunique"),
            sample_ids=("sample_id", lambda series: ",".join(map(str, sorted(set(series.tolist()))))),
            family_ids=("family_id", lambda series: ",".join(map(str, sorted(set(series.dropna().tolist()))))),
            family_names=(
                "family_canonical",
                lambda series: ",".join(sorted(set(map(str, series.dropna().tolist())))),
            ),
        )
        .reset_index()
    )
    duplicate_groups["is_invalid_sha"] = ~duplicate_groups["sha256"].map(
        lambda value: bool(_SHA256_RE.fullmatch(str(value)))
    )
    duplicate_groups = duplicate_groups[
        (duplicate_groups["count_samples"] > 1) | duplicate_groups["is_invalid_sha"]
    ].copy()
    duplicate_groups = duplicate_groups.sort_values(
        by=["count_samples", "sha256"],
        ascending=[False, True],
    ).reset_index(drop=True)

    duplicate_count = int((duplicate_groups["count_samples"] > 1).sum())
    report_path = diagnostics_dir / f"duplicate_sha256_report_{run_id}.csv"
    mirror_paths: list[Path] = []
    verbose = bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))
    should_write_report = paper_mode or duplicate_count > 0 or invalid_sha_count > 0 or verbose
    if should_write_report:
        csv_text = duplicate_groups.to_csv(index=False)
        mirror_paths = oh.mirror_csv_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=report_path.name,
            csv_text=csv_text,
            global_latest_name="duplicate_sha256_report.latest.csv",
        )
        report_path = mirror_paths[0]
        artifact_list.extend(str(p) for p in mirror_paths)
    else:
        report_path.unlink(missing_ok=True)

    summary = {
        "report_path": str(report_path),
        "join_inflation_rows_removed": join_inflation_rows,
        "invalid_sha_count": invalid_sha_count,
        "duplicate_sha_groups": duplicate_count,
        "paper_mode_hard_fail": paper_mode,
    }
    manifest_context["duplicate_sha"] = summary
    setattr(app_config, "RUNTIME_DUPLICATE_SHA_METADATA", dict(summary))

    if paper_mode and invalid_sha_count > 0:
        raise RuntimeError(
            f"[PAPER] Invalid sha256 values detected: {invalid_sha_count}. "
            f"See {report_path}."
        )
    if paper_mode and duplicate_count > 0:
        raise RuntimeError(
            f"[PAPER] Duplicate sha256 groups detected: {duplicate_count}. "
            f"See {report_path}."
        )
    if duplicate_count > 0:
        du.print_warning(
            f"[DUPLICATE] Duplicate SHA groups detected: {duplicate_count} (non-paper warning)."
        )
    else:
        du.print_info("[DUPLICATE] No duplicate SHA groups detected in aligned cohort.")


def print_run_context_line(
    *,
    run_id: str,
    profile_id: str,
    stage: str,
    stop_after: str,
    selected_models: Optional[Sequence[str]],
) -> None:
    """Print a concise execution context line for stage-level traceability."""
    paper_mode = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    experiment_id = str(getattr(app_config, "RUNTIME_EXPERIMENT_ID", "") or "")
    model_text = ",".join(selected_models) if selected_models else "profile_default"
    if ml_console.is_debug():
        du.print_info(
            "[CTX] "
            f"run_id={run_id} profile={profile_id} stage={stage} "
            f"paper_mode={'on' if paper_mode else 'off'} stop_after={stop_after} "
            f"models={model_text} experiment={experiment_id or 'n/a'}"
        )
        return

    milestone_stages = {"samples", "feature_matrix", "training", "label_resolution"}
    if str(stage).strip() not in milestone_stages:
        return

    compact = f"[CTX] stage={stage} | models={model_text}"
    if paper_mode:
        compact += " | paper=on"
    if str(stop_after).strip() and str(stop_after).strip().lower() != "full":
        compact += f" | stop_after={stop_after}"
    if experiment_id:
        compact += f" | experiment={experiment_id}"
    du.print_info(compact)


def format_population_pipeline_summary_line(manifest_context: dict[str, Any]) -> str:
    """Return a one-line population chain for strict primary-path reporting.

    Uses manifest cohort/fusion/alignment counts plus post–low-support training pool
    and train/test split sizes when available. Distinct supervised family labels after
    min-family-support filtering come from ``RUNTIME_TRAINING_LABEL_CLASS_COUNT`` when set.
    """
    gov = manifest_context.get("cohort_prepared_row_count")
    fused = manifest_context.get("fused_feature_rows")
    aligned = manifest_context.get("aligned_supervised_rows")
    postls = manifest_context.get("post_low_support_training_rows")
    tr = manifest_context.get("train_sample_count")
    te = manifest_context.get("test_sample_count")
    cls_n = getattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", None)
    if gov is None or fused is None or aligned is None or postls is None:
        return ""
    parts = [
        f"governed_cohort_n={int(gov)}",
        f"fused_feature_matrix_n={int(fused)}",
        f"aligned_supervised_n={int(aligned)}",
        f"post_family_support_trainable_n={int(postls)}",
    ]
    if tr is not None and str(tr) != "":
        parts.append(f"train_n={int(tr)}")
    if te is not None and str(te) != "":
        parts.append(f"test_n={int(te)}")
    if cls_n is not None and str(cls_n) != "":
        support_mode = str(getattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "") or "").strip().lower()
        if support_mode == "diagnostic_only":
            parts.append(f"actual_modeled_family_classes={int(cls_n)}")
        else:
            parts.append(f"distinct_family_labels_after_support={int(cls_n)}")
    return " | ".join(parts)


def extract_model_summary(model_results: dict[str, Any]) -> dict[str, Any]:
    """Extract a compact model leaderboard summary for run reporting."""
    rank_metric = str(
        getattr(app_config, "MODEL_RANK_PRIMARY_METRIC", "macro_f1_score") or "macro_f1_score"
    ).strip().lower()
    if rank_metric == "f1_score":
        primary_metric_key = "weighted_f1"
    elif rank_metric == "accuracy":
        primary_metric_key = "accuracy"
    else:
        rank_metric = "macro_f1_score"
        primary_metric_key = "macro_f1"

    rows: list[dict[str, Any]] = []
    for model_name, payload in model_results.items():
        if not isinstance(payload, dict):
            continue
        evaluation = payload.get("evaluation", {})
        if not isinstance(evaluation, dict):
            continue
        macro = evaluation.get("macro_f1_score")
        weighted = evaluation.get("f1_score")
        acc = evaluation.get("accuracy")
        if macro is None:
            continue
        rows.append(
            {
                "model": str(model_name),
                "macro_f1": float(macro),
                "weighted_f1": float(weighted) if weighted is not None else None,
                "accuracy": float(acc) if acc is not None else None,
            }
        )
    if not rows:
        return {}
    for row in rows:
        primary_score = row.get(primary_metric_key)
        row["primary_metric_name"] = rank_metric
        row["primary_metric_value"] = primary_score
        row["primary_metric_tier"] = (
            accuracy_band_utils.evaluate_accuracy_band(float(primary_score))
            if primary_score is not None
            else None
        )
        row["weighted_f1_tier"] = (
            accuracy_band_utils.evaluate_accuracy_band(float(row["weighted_f1"]))
            if row.get("weighted_f1") is not None
            else None
        )
        row["accuracy_tier"] = (
            accuracy_band_utils.evaluate_accuracy_band(float(row["accuracy"]))
            if row.get("accuracy") is not None
            else None
        )
    rows = sorted(
        rows,
        key=lambda item: float(item.get(primary_metric_key) or float("-inf")),
        reverse=True,
    )
    top_model = rows[0]["model"]
    family_tier_rows = family_tier_model_evaluation.build_family_tier_model_evaluation_rows(model_results)
    top_model_family_tier_rows = [
        row for row in family_tier_rows if str(row.get("model", "") or "") == str(top_model)
    ]
    return {
        "top_model": top_model,
        "top_macro_f1": rows[0]["macro_f1"],
        "top_model_primary_metric_name": rank_metric,
        "top_model_primary_metric_value": rows[0].get("primary_metric_value"),
        "top_model_primary_metric_tier": rows[0].get("primary_metric_tier"),
        "top_model_weighted_f1_tier": rows[0].get("weighted_f1_tier"),
        "top_model_accuracy_tier": rows[0].get("accuracy_tier"),
        "model_rows": rows,
        "family_tier_model_rows": family_tier_rows,
        "top_model_family_tier_rows": top_model_family_tier_rows,
    }


def count_evaluated_models(
    model_results: dict[str, Any] | None,
    model_summary: dict[str, Any] | None = None,
) -> int:
    """Count fitted/evaluated classifiers, not auxiliary evaluation rows.

    Run summaries must represent the number of classifier estimators actually
    evaluated.  Some downstream summaries contain per-model rows for several
    evaluation scopes (for example, overall, major, minor, and unresolved),
    which must never be counted as additional trained models.
    """
    rows = model_summary.get("model_rows") if isinstance(model_summary, dict) else None
    if isinstance(rows, list):
        names = {
            str(row.get("model", "")).strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("model", "")).strip()
        }
        if names:
            return len(names)

    if not isinstance(model_results, dict):
        return 0
    return sum(
        1
        for payload in model_results.values()
        if isinstance(payload, dict)
        and isinstance(payload.get("evaluation"), dict)
        and payload["evaluation"].get("macro_f1_score") is not None
    )


def apply_confusion_matrix_policy(run_id: str, top_model: str | None) -> None:
    """Apply confusion-matrix retention policy for run-scoped outputs."""
    mode = str(getattr(app_config, "CONFUSION_MATRIX_MODE", "all")).strip().lower()

    run_cm_dir = output_paths.resolve_runtime_run_directory(str(run_id)) / "conf_matrices"
    if not run_cm_dir.exists():
        return

    files = sorted(p for p in run_cm_dir.rglob("*.png") if p.is_file())
    if not files:
        return
    if mode == "all":
        du.print_info("[CONFUSION] Export summary")
        print("  Policy: all")
        print(f"  Retained: {len(files)} matrix file(s)")
        print("  Removed: 0 matrix file(s)")
        print("  Location: conf_matrices/")
        try:
            from obsidiandroid.reporting import confusion_matrix_layout as cm_layout

            cm_layout.write_confusion_matrix_catalog(run_cm_dir, run_id=run_id)
        except Exception:
            pass
        return
    if not top_model:
        du.print_warning("[CONFUSION] Top model unknown; skipping confusion-matrix pruning.")
        return

    ablation_tokens = {
        "vendor_only",
        "vendor_full",
        "vendor_no_parsed_family",
        "permissions_only",
        "permissions_raw",
        "full_fused",
        "vendor_permissions_fused",
    }
    primary_candidate: Path | None = None
    ablation_candidate: Path | None = None

    for path in files:
        name = path.name
        stem_ok = (
            name.endswith(f"__{top_model}.png")
            or name.endswith(f"_{top_model}.png")
            or name == f"{top_model}.png"
        )
        if not stem_ok:
            continue
        path_s = str(path).replace("\\", "/").lower()
        matched_ablation = next((token for token in ablation_tokens if token in path_s), None)
        if matched_ablation is None and primary_candidate is None:
            primary_candidate = path
        if matched_ablation in {"vendor_permissions_fused", "full_fused"} and ablation_candidate is None:
            ablation_candidate = path

    fallback_primary = run_cm_dir / f"confusion_matrix_{top_model}.png"
    if primary_candidate is None and fallback_primary.exists():
        primary_candidate = fallback_primary

    keep: set[Path] = set()
    if primary_candidate is not None:
        keep.add(primary_candidate)
    if mode == "primary_plus_ablation" and ablation_candidate is not None:
        keep.add(ablation_candidate)
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        rf_candidate = run_cm_dir / "confusion_matrix_random_forest.png"
        if rf_candidate.exists():
            keep.add(rf_candidate)

    if not keep:
        du.print_warning("[CONFUSION] No primary confusion matrix resolved for pruning policy.")
        try:
            from obsidiandroid.reporting import confusion_matrix_layout as cm_layout

            cm_layout.write_confusion_matrix_catalog(run_cm_dir, run_id=run_id)
        except Exception:
            pass
        return

    rf_stable = run_cm_dir / "confusion_matrix_random_forest.png"
    if rf_stable.exists():
        keep.add(rf_stable)
    rf_stable_display = run_cm_dir / "confusion_matrix_random_forest_display.png"
    if rf_stable_display.exists():
        keep.add(rf_stable_display)
    headline_rf = run_cm_dir / "headline" / "random_forest.png"
    if headline_rf.exists():
        keep.add(headline_rf)
    headline_rf_display = run_cm_dir / "headline" / "random_forest_display.png"
    if headline_rf_display.exists():
        keep.add(headline_rf_display)

    removed = 0
    for path in files:
        if path in keep:
            continue
        try:
            path.unlink()
            removed += 1
        except Exception:
            continue

    try:
        primary_alias = run_cm_dir / "confusion_matrix_primary.png"
        if primary_candidate is not None:
            shutil.copyfile(primary_candidate, primary_alias)
            latest_root = Path(app_config.DEFAULT_OUTPUT_DIR) / "latest"
            latest_root.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(primary_candidate, latest_root / "confusion_matrix_primary.png")
            display_candidate = primary_candidate.with_name(
                f"{primary_candidate.stem}_display{primary_candidate.suffix}"
            )
            if display_candidate.exists():
                primary_display_alias = run_cm_dir / "confusion_matrix_primary_display.png"
                shutil.copyfile(display_candidate, primary_display_alias)
                shutil.copyfile(display_candidate, latest_root / "confusion_matrix_primary_display.png")
    except Exception:
        pass

    try:
        from obsidiandroid.reporting import confusion_matrix_layout as cm_layout

        cm_layout.write_confusion_matrix_catalog(run_cm_dir, run_id=run_id)
    except Exception:
        pass

    du.print_info("[CONFUSION] Export summary")
    print(f"  Policy: {mode}")
    print(f"  Retained: {len(keep)} matrix file(s)")
    print(f"  Removed: {removed} matrix file(s)")
    print(f"  Promoted model: {top_model}")
    print("  Location: conf_matrices/")


def export_model_config_snapshot(
    *,
    run_id: str,
    model_results: dict[str, Any],
    artifact_list: list[str],
    manifest_context: dict[str, Any],
) -> str | None:
    """Export model configuration snapshot for run-level reproducibility."""
    diagnostics_dir = runtime_diagnostics_dir()
    snapshot: dict[str, Any] = {
        "run_id": run_id,
        "random_seed": safe_int_config_value(getattr(app_config, "RANDOM_STATE", 42), default=42),
        "cv": {
            "enabled": bool(getattr(app_config, "ENABLE_CROSS_VALIDATION", False)),
            "folds": coerce_stratified_cv_folds_config(getattr(app_config, "CV_FOLDS", 5)),
            "repeats": max(
                1,
                safe_int_config_value(getattr(app_config, "CV_REPEATS", 1), default=1),
            ),
            "stratified": True,
        },
        "models": {},
    }
    for model_name, payload in model_results.items():
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        evaluation = payload.get("evaluation", {})
        if not isinstance(evaluation, dict):
            evaluation = {}
        snapshot["models"][str(model_name)] = {
            "params": metadata.get("params", {}),
            "cv_score_mean": payload.get("cv_score_mean"),
            "macro_f1": evaluation.get("macro_f1_score"),
            "accuracy": evaluation.get("accuracy"),
            "train_time_sec": evaluation.get("train_time"),
        }
    if not snapshot["models"]:
        return None

    model_contract = {
        "random_seed": snapshot["random_seed"],
        "cv": snapshot["cv"],
        "models": {
            model_name: {
                "params": payload.get("params", {}),
            }
            for model_name, payload in sorted(snapshot["models"].items(), key=lambda item: item[0])
        },
    }
    model_contract_hash = hash_payload(model_contract)
    snapshot["model_contract"] = model_contract
    snapshot["model_contract_hash"] = model_contract_hash
    snapshot["model_contract_hash_basis"] = "config_only_no_run_id_no_metrics"

    out_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    payload = json.dumps(snapshot, indent=2, sort_keys=True)
    written_paths = oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=out_path.name,
        payload=snapshot,
        global_latest_name="model_config_snapshot.latest.json",
    )
    artifact_list.extend(str(path) for path in written_paths)
    manifest_context["model_config_snapshot_path"] = str(out_path)
    manifest_context["model_config_hash"] = model_contract_hash
    manifest_context["model_config_hash_basis"] = "config_only_no_run_id_no_metrics"
    return str(out_path)


def setup_runtime_context(
    run_id: str,
    *,
    run_slot: str,
    strict_run_scoped: bool = True,
    archive_run: bool = False,
    keep_last_failed_runs: int = 0,
    keep_last_completed_runs: int = 3,
) -> dict[str, Path | str]:
    """Initialize runtime output paths and route diagnostics for a run."""
    del strict_run_scoped
    layout = output_paths.ensure_output_layout()
    output_root_base = layout["output_root"]
    prepared = run_slots.prepare_run_root(
        runs_root=layout["runs_root"],
        run_slot=run_slot,
        run_instance_id=run_id,
        archive_run=archive_run,
        keep_last_failed_runs=keep_last_failed_runs,
        keep_last_completed_runs=keep_last_completed_runs,
    )
    runtime_run_root = Path(prepared["run_root"])
    runtime_diagnostics = Path(prepared["diagnostics_dir"])

    setattr(app_config, "RUNTIME_RUN_ROOT", str(runtime_run_root))
    setattr(app_config, "RUNTIME_RUN_SLOT", str(run_slot))
    setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root_base))
    setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(runtime_diagnostics))
    rid = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "unknown")
    setattr(app_config, "ANALYSIS_SNAPSHOT_FILE", str(runtime_diagnostics / f"analysis_snapshot_{rid}.csv"))
    setattr(app_config, "ANALYSIS_SNAPSHOT_META_FILE", str(runtime_diagnostics / f"analysis_snapshot_{rid}.meta.txt"))
    setattr(
        app_config,
        "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
        str(runtime_diagnostics / f"analysis_snapshot_label_conflicts_{rid}.csv"),
    )
    setattr(app_config, "PAPER_COHORT_SAMPLE_IDS_FILE", str(runtime_diagnostics / "paper_cohort_sample_ids.csv"))
    setattr(app_config, "DATASET_TIME_CONTRACT_FILE", str(runtime_diagnostics / f"dataset_time_contract_{rid}.json"))
    setattr(app_config, "ALIGNED_FEATURE_CACHE_FILE", str(runtime_diagnostics / f"aligned_features_{rid}.csv.gz"))
    setattr(app_config, "ALIGNED_LABEL_CACHE_FILE", str(runtime_diagnostics / f"aligned_labels_{rid}.csv"))
    previous_archive = prepared.get("previous_slot_archive")
    return {
        "output_root_base": output_root_base,
        "runtime_run_root": runtime_run_root,
        "runtime_diagnostics_dir": runtime_diagnostics,
        "run_slot": str(run_slot),
        "cleanup_action": str(prepared["cleanup_action"]),
        "previous_slot_archive": str(previous_archive) if previous_archive else "",
    }


def build_run_summary_payload(
    *,
    run_id: str,
    profile_id: str,
    samples_df: pd.DataFrame | None,
    model_results: dict[str, Any] | None,
    top_model: str | None,
    manifest_context: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact run summary payload for diagnostics and terminal output."""
    sample_count = int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0
    missing_pkg_count = 0
    if isinstance(samples_df, pd.DataFrame) and "android_package_name" in samples_df.columns:
        missing_pkg_count = int(
            (samples_df["android_package_name"].fillna("").astype(str).str.strip() == "").sum()
        )
    missing_pkg_rate = (missing_pkg_count / sample_count) if sample_count else 0.0

    macro_f1 = None
    unknown_count = 0
    unknown_rate = 0.0
    family_count = 0
    top_family_share = 0.0
    if isinstance(samples_df, pd.DataFrame):
        family_col = "family_canonical" if "family_canonical" in samples_df.columns else None
        if family_col:
            counts = samples_df[family_col].fillna("unknown").astype(str).value_counts()
            family_count = int(counts.shape[0])
            if not counts.empty:
                top_family_share = float(counts.iloc[0] / max(sample_count, 1))

    if isinstance(model_results, dict) and top_model and top_model in model_results:
        eval_block = model_results.get(top_model, {}).get("evaluation", {})
        if isinstance(eval_block, dict):
            try:
                macro_f1 = float(eval_block.get("macro_f1_score"))
            except Exception:
                macro_f1 = None
        prediction_meta = model_results.get(top_model, {}).get("prediction_metadata", {})
        if isinstance(prediction_meta, dict):
            decoded = [
                str((meta or {}).get("decoded_label", "")).strip().lower()
                for _, meta in prediction_meta.items()
                if isinstance(meta, dict)
            ]
            unknown_count = sum(1 for label in decoded if label in {"unknown", "other"})
            unknown_rate = (unknown_count / len(decoded)) if decoded else 0.0

    fallback_used = bool(getattr(app_config, "RUNTIME_VENDOR_FALLBACK_USED", False))
    fallback_added = safe_int_config_value(
        getattr(app_config, "RUNTIME_VENDOR_FALLBACK_ADDED_COUNT", 0), default=0
    )
    k_requested = safe_int_config_value(getattr(app_config, "RUNTIME_K_REQUESTED", 0), default=0)
    effective_top_k = safe_int_config_value(
        getattr(app_config, "RUNTIME_EFFECTIVE_TOP_K", k_requested), default=k_requested
    )
    included_engine_count = safe_int_config_value(
        manifest_context.get(
            "included_engine_count", getattr(app_config, "RUNTIME_INCLUDED_ENGINE_COUNT", 0)
        ),
        default=0,
    )
    engine_count_observed = int(manifest_context.get("engine_count_observed", 0) or 0)
    engine_count_canonical = int(manifest_context.get("engine_count_canonical", 0) or 0)
    engine_count_near_miss = safe_int_config_value(
        getattr(app_config, "RUNTIME_ENGINE_COUNT_NEAR_MISS", 0), default=0
    )
    engine_exclusion_reason_counts = dict(
        manifest_context.get("engine_exclusion_reason_counts", {}) or {}
    )
    av_binary_feature_scope = str(
        manifest_context.get(
            "av_binary_feature_engine_scope",
            getattr(app_config, "RUNTIME_AV_BINARY_FEATURE_ENGINE_SCOPE", "all_observed"),
        )
        or "all_observed"
    )
    av_binary_feature_engine_columns = safe_int_config_value(
        manifest_context.get(
            "av_binary_feature_engine_columns",
            getattr(app_config, "RUNTIME_AV_BINARY_FEATURE_ENGINE_COUNT", 0),
        ),
        default=0,
    )
    av_binary_feature_engine_columns_observed = safe_int_config_value(
        manifest_context.get("av_binary_feature_engine_columns_observed", 0),
        default=0,
    )
    non_standard_features = bool(getattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", False))

    return {
        "run_id": run_id,
        "profile_id": profile_id,
        "engine_count_observed": engine_count_observed,
        "engine_count_canonical": engine_count_canonical,
        "engine_count_included_after_gating": included_engine_count,
        "engine_count_near_miss": engine_count_near_miss,
        "engine_exclusion_reason_counts": engine_exclusion_reason_counts,
        "av_binary_feature_engine_scope": av_binary_feature_scope,
        "av_binary_feature_engine_columns": av_binary_feature_engine_columns,
        "av_binary_feature_engine_columns_observed": av_binary_feature_engine_columns_observed,
        "engine_count_requested_top_k": k_requested,
        "effective_top_k": effective_top_k,
        "fallback_used": fallback_used,
        "fallback_added_count": fallback_added,
        "included_engine_count": included_engine_count,
        "k_requested": k_requested,
        "non_standard_features": non_standard_features,
        "unknown_rate": round(unknown_rate, 6),
        "unknown_count": int(unknown_count),
        "missing_package_count": int(missing_pkg_count),
        "missing_package_rate": round(missing_pkg_rate, 6),
        "macro_f1": (round(float(macro_f1), 6) if macro_f1 is not None else None),
        "n_families": int(family_count),
        "top_family_share": round(float(top_family_share), 6),
    }


def export_and_print_run_summary(
    *,
    payload: dict[str, Any],
    artifact_list: list[str],
    echo_terminal: bool = True,
) -> None:
    """Persist run health JSON; optionally echo the legacy engine-first panel to the terminal."""
    diagnostics_dir = runtime_diagnostics_dir()
    run_id = str(payload.get("run_id", "unknown"))
    out_path = diagnostics_dir / f"run_health_summary_{run_id}.json"
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    out_path.write_text(encoded, encoding="utf-8")
    paths_out = [str(out_path)]
    if oh.run_diagnostics_should_omit_latest_duplicate() and oh.path_is_under_output_runs(diagnostics_dir):
        global_latest = oh.write_global_latest_text(filename="run_health_summary.latest.json", text=encoded)
        paths_out.append(str(global_latest))
    else:
        latest_path = diagnostics_dir / "run_health_summary.latest.json"
        latest_path.write_text(encoded, encoding="utf-8")
        paths_out.append(str(latest_path))
    artifact_list.extend(paths_out)

    if echo_terminal:
        du.print_section("Run Health Summary")
        du.print_stat("Cohort Engines Observed", payload.get("engine_count_observed"))
        du.print_stat("Cohort Engines Canonical", payload.get("engine_count_canonical"))
        du.print_stat("Post-Score Engines Included", payload.get("engine_count_included_after_gating"))
        du.print_stat(
            "AV Binary Feature Scope",
            (
                f"{payload.get('av_binary_feature_engine_scope')} "
                f"({payload.get('av_binary_feature_engine_columns')}/"
                f"{payload.get('av_binary_feature_engine_columns_observed')} columns)"
            ),
        )
        if payload.get("engine_count_near_miss") is not None:
            du.print_stat("Excluded Near-Miss Engines", payload.get("engine_count_near_miss"))
        exclusion_counts = payload.get("engine_exclusion_reason_counts", {}) or {}
        if exclusion_counts:
            preview = ", ".join(
                f"{str(reason)}={int(count)}"
                for reason, count in list(exclusion_counts.items())[:3]
            )
            du.print_stat("Top Exclusion Reasons", preview)
        du.print_stat("Requested Parser Top-K", payload.get("engine_count_requested_top_k"))
        du.print_stat("Effective Top-K", payload.get("effective_top_k"))
        du.print_stat("Fallback Used", payload.get("fallback_used"))
        du.print_stat("Fallback Added Count", payload.get("fallback_added_count"))
        du.print_stat("Non-Standard Features", payload.get("non_standard_features"))
        du.print_stat("Unknown Rate", f"{float(payload.get('unknown_rate', 0.0)):.2%}")
        du.print_stat("Missing Package Rate", f"{float(payload.get('missing_package_rate', 0.0)):.2%}")
        du.print_stat("Macro F1", payload.get("macro_f1"))
        du.print_stat("Family Count", payload.get("n_families"))
        du.print_stat("Top Family Share", f"{float(payload.get('top_family_share', 0.0)):.2%}")
