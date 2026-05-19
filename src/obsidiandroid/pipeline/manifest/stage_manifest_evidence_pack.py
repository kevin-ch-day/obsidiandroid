"""Evidence-bundle assembly and cohort export helpers for the manifest stage."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config

from obsidiandroid.common.cohort_contracts import resolve_contract_cohort_lock_status
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.pipeline.manifest.confusion_matrix_paths import find_primary_confusion_matrix

EVIDENCE_BUNDLE_DIRNAME = "evidence_bundle"
LEGACY_EVIDENCE_BUNDLE_DIRNAME = "paper2_pack"


def _bundle_dirs(run_root: Path) -> tuple[Path, Path]:
    bundle_dir = run_root / EVIDENCE_BUNDLE_DIRNAME
    legacy_dir = run_root / LEGACY_EVIDENCE_BUNDLE_DIRNAME
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return bundle_dir, legacy_dir


def _mirror_legacy_bundle_file(*, source_path: Path, legacy_dir: Path) -> None:
    legacy_path = legacy_dir / source_path.name
    if source_path.resolve() == legacy_path.resolve():
        return
    legacy_dir.mkdir(parents=True, exist_ok=True)
    if legacy_path.exists():
        legacy_path.unlink()
    try:
        os.link(source_path, legacy_path)
    except OSError:
        legacy_path.write_bytes(source_path.read_bytes())


def build_paper2_pack(
    *,
    run_root: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    ranking_path: Path | None,
) -> dict[str, str]:
    """Build run-scoped evidence-bundle files with legacy bundle mirroring."""
    pack_dir, legacy_pack_dir = _bundle_dirs(run_root)
    artifacts_written: dict[str, str] = {}

    sample_count = int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0
    family_counts: dict[str, int] = {}
    max_family_share = 0.0
    if isinstance(samples_df, pd.DataFrame) and "family_canonical" in samples_df.columns:
        counts = (
            samples_df["family_canonical"].fillna("unknown").astype(str).value_counts()
        )
        family_counts = {str(k): int(v) for k, v in counts.to_dict().items()}
        if sample_count > 0 and not counts.empty:
            max_family_share = float(counts.iloc[0] / sample_count)
    dataset_characterization = {
        "run_id": run_id,
        "sample_count": sample_count,
        "family_count": len(family_counts),
        "family_distribution": family_counts,
        "max_family_share": round(max_family_share, 6),
        "unknown_excluded_count": int(manifest_context.get("unknown_excluded_count", 0) or 0),
        "time_window": {
            "start_utc": ((manifest_context.get("profile_params", {}) or {}).get("cohort_gates", {}) or {}).get("time_window_start_utc"),
            "end_utc": ((manifest_context.get("profile_params", {}) or {}).get("cohort_gates", {}) or {}).get("time_window_end_utc"),
        },
        "dataset_hash": manifest.get("dataset_hash", ""),
    }
    dataset_path = pack_dir / "dataset_characterization.json"
    dataset_path.write_text(json.dumps(dataset_characterization, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=dataset_path, legacy_dir=legacy_pack_dir)
    artifacts_written["dataset_characterization.json"] = str(dataset_path)

    if ranking_path is not None and ranking_path.exists():
        artifacts_written["engine_ranking_tiers.csv"] = str(ranking_path)

    consensus_df, consensus_stats = build_consensus_distribution(samples_df=samples_df, manifest=manifest)
    consensus_csv = pack_dir / "consensus_distribution.csv"
    consensus_df.to_csv(consensus_csv, index=False, lineterminator="\n", float_format="%.6f")
    _mirror_legacy_bundle_file(source_path=consensus_csv, legacy_dir=legacy_pack_dir)
    artifacts_written["consensus_distribution.csv"] = str(consensus_csv)
    consensus_stats_path = pack_dir / "consensus_stats.json"
    consensus_stats_path.write_text(json.dumps(consensus_stats, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=consensus_stats_path, legacy_dir=legacy_pack_dir)
    artifacts_written["consensus_stats.json"] = str(consensus_stats_path)
    consensus_png = pack_dir / "consensus_distribution.png"
    render_consensus_distribution_png(consensus_df=consensus_df, output_path=consensus_png)
    _mirror_legacy_bundle_file(source_path=consensus_png, legacy_dir=legacy_pack_dir)
    artifacts_written["consensus_distribution.png"] = str(consensus_png)

    metrics_payload = {
        "run_id": run_id,
        "model_summary": manifest_context.get("model_summary", {}),
    }
    metrics_path = pack_dir / "model_metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=metrics_path, legacy_dir=legacy_pack_dir)
    artifacts_written["model_metrics.json"] = str(metrics_path)

    conf_src = find_primary_confusion_matrix(
        run_root=run_root,
        top_model=str((manifest_context.get("model_summary") or {}).get("top_model", "")),
        evidence_mode=coalesce_manifest_publication_mode(manifest),
    )
    if conf_src is not None and conf_src.exists():
        conf_dst = pack_dir / "confusion_matrix_primary.png"
        conf_dst.write_bytes(conf_src.read_bytes())
        _mirror_legacy_bundle_file(source_path=conf_dst, legacy_dir=legacy_pack_dir)
        artifacts_written["confusion_matrix_primary.png"] = str(conf_dst)

    manifest_src = run_root / "run_manifest.json"
    if not manifest_src.exists():
        manifest_src = run_manifest.resolve_manifest_path()
    if manifest_src.exists():
        manifest_dst = pack_dir / "manifest.json"
        manifest_dst.write_bytes(manifest_src.read_bytes())
        _mirror_legacy_bundle_file(source_path=manifest_dst, legacy_dir=legacy_pack_dir)
        artifacts_written["manifest.json"] = str(manifest_dst)

    compliance_path = pack_dir / "evidence_compliance_summary.json"
    compliance_payload = {
        "run_id": run_id,
        "evidence_mode": coalesce_manifest_publication_mode(manifest),
        "non_standard_features": bool(manifest.get("non_standard_features", False)),
        "fallback_used": bool(manifest.get("vendor_fallback_used", False)),
        "requested_top_k": int(manifest.get("k_requested", 0) or 0),
        "effective_top_k": int(manifest.get("effective_top_k", 0) or 0),
    }
    compliance_path.write_text(json.dumps(compliance_payload, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=compliance_path, legacy_dir=legacy_pack_dir)
    artifacts_written["evidence_compliance_summary.json"] = str(compliance_path)
    return artifacts_written


def build_consensus_distribution(
    *,
    samples_df: pd.DataFrame | None,
    manifest: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build consensus distribution table and summary stats."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        empty = pd.DataFrame(columns=["bucket", "raw_count", "percent"])
        stats = {"sample_count": 0}
        return empty, stats
    mal = pd.to_numeric(samples_df.get("vt_malicious_count", 0), errors="coerce").fillna(0.0)
    susp = pd.to_numeric(samples_df.get("vt_suspicious_count", 0), errors="coerce").fillna(0.0)
    denom = max(int(manifest.get("engine_count_observed", 0) or 0), 1)
    ratio = ((mal + susp) / float(denom)).clip(lower=0.0, upper=1.0)
    bins = pd.cut(
        ratio,
        bins=[-0.001, 0.1, 0.25, 0.5, 0.75, 1.0],
        labels=["0-0.10", "0.10-0.25", "0.25-0.50", "0.50-0.75", "0.75-1.00"],
        include_lowest=True,
    )
    table = (
        bins.value_counts(sort=False)
        .rename_axis("bucket")
        .reset_index(name="raw_count")
    )
    table["percent"] = (table["raw_count"] / max(len(ratio), 1)).round(6)
    stats = {
        "sample_count": int(len(ratio)),
        "min": round(float(ratio.min()), 6),
        "max": round(float(ratio.max()), 6),
        "mean": round(float(ratio.mean()), 6),
        "median": round(float(ratio.median()), 6),
        "std": round(float(ratio.std(ddof=0)), 6),
        "q1": round(float(ratio.quantile(0.25)), 6),
        "q3": round(float(ratio.quantile(0.75)), 6),
    }
    return table, stats


def render_consensus_distribution_png(*, consensus_df: pd.DataFrame, output_path: Path) -> None:
    """Render consensus distribution bar chart."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(7.16, 3.4))
    ax.bar(consensus_df["bucket"].astype(str), pd.to_numeric(consensus_df["percent"], errors="coerce").fillna(0.0))
    ax.set_ylabel("Percent")
    ax.set_xlabel("Consensus Score Bucket")
    ax.set_title("Consensus Distribution")
    ax.set_ylim(0, 1.0)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def export_trained_family_registry(
    *,
    samples_df: pd.DataFrame | None,
    run_id: str,
    diagnostics_dir: Path,
) -> tuple[Path | None, int]:
    """Export family inclusion table after min-support filtering policy."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return None, 0
    if "family_canonical" not in samples_df.columns:
        return None, 0
    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    frame = samples_df.copy()
    frame["family_canonical"] = frame["family_canonical"].fillna("").astype(str).str.strip()
    frame["type_slug"] = frame.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    frame = frame[frame["family_canonical"] != ""].copy()
    if frame.empty:
        return None, 0
    grouped = (
        frame.groupby(["family_canonical", "type_slug"], as_index=False)
        .size()
        .rename(columns={"size": "sample_count"})
        .sort_values(
            by=["sample_count", "family_canonical", "type_slug"],
            ascending=[False, True, True],
            kind="mergesort",
        )
    )
    dedup = grouped.drop_duplicates(subset=["family_canonical"], keep="first").copy()
    dedup["included_in_training"] = (
        pd.to_numeric(dedup["sample_count"], errors="coerce").fillna(0).astype(int) >= max(min_support, 1)
    ).astype(int)
    dedup = dedup.sort_values(
        by=["sample_count", "family_canonical"],
        ascending=[False, True],
        kind="mergesort",
    )
    out_df = dedup[["family_canonical", "type_slug", "sample_count", "included_in_training"]].copy()
    out_df.insert(0, "run_id", str(run_id))
    run_path = diagnostics_dir / f"trained_family_registry_{run_id}.csv"
    latest_path = diagnostics_dir / "trained_family_registry.latest.csv"
    csv_text = out_df.to_csv(index=False)
    run_path.write_text(csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=run_path.name,
        csv_text=csv_text,
        global_latest_name=latest_path.name,
    )
    included = int(out_df["included_in_training"].sum())
    return run_path, included


def export_confusion_matrix_provenance(
    *,
    run_root: Path,
    run_id: str,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
    trained_family_count: int,
    evidence_mode: bool,
) -> Path | None:
    """Export explicit confusion matrix provenance for paper traceability."""
    model_name = "random_forest"
    conf_path = find_primary_confusion_matrix(
        run_root=run_root,
        top_model=model_name,
        evidence_mode=True if evidence_mode else False,
    )
    if conf_path is None or not conf_path.exists():
        return None

    test_samples = 0
    model_meta_path = run_root / "models" / model_name / f"{model_name}_classifier_model_metadata.json"
    if model_meta_path.exists():
        try:
            payload = json.loads(model_meta_path.read_text(encoding="utf-8"))
            evaluation = payload.get("evaluation", {}) if isinstance(payload, dict) else {}
            test_samples = int(evaluation.get("samples_tested", 0) or 0)
        except Exception:
            test_samples = 0

    headline_split = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    split_h = ""
    if isinstance(headline_split, dict):
        split_h = str(headline_split.get("split_hash", "") or "")
    feat_h = str(getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or "")
    provenance_df = pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "model_name": model_name,
                "eval_source": "test_set",
                "test_sample_count": int(test_samples),
                "trained_family_count": int(trained_family_count),
                "confusion_matrix_path": str(conf_path.resolve()),
                "split_hash": split_h,
                "feature_column_hash": feat_h,
            }
        ]
    )
    run_path = diagnostics_dir / f"confusion_matrix_provenance_{run_id}.csv"
    latest_path = diagnostics_dir / "confusion_matrix_provenance.latest.csv"
    csv_text = provenance_df.to_csv(index=False)
    run_path.write_text(csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=run_path.name,
        csv_text=csv_text,
        global_latest_name=latest_path.name,
    )
    return run_path


def build_cohort_limitation_summary(samples_df: pd.DataFrame | None) -> dict[str, Any]:
    """Build compact cohort limitation summary for methods/discussion sections."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return {
            "total_samples": 0,
            "total_cohort_families": 0,
            "training_families": 0,
            "represented_types": 0,
            "top_family_share": 0.0,
            "banker_share": 0.0,
        }
    sample_count = int(len(samples_df))
    family_series = samples_df.get("family_canonical", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    family_counts = family_series[family_series != ""].value_counts()
    type_series = samples_df.get("type_slug", pd.Series(dtype=str)).fillna("").astype(str).str.strip().str.lower()
    type_counts = type_series[type_series != ""].value_counts()
    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    training_families = int((family_counts >= max(min_support, 1)).sum()) if not family_counts.empty else 0
    top_family_share = float((family_counts.iloc[0] / sample_count) if sample_count > 0 and not family_counts.empty else 0.0)
    banker_share = float((type_counts.get("banker", 0) / sample_count) if sample_count > 0 else 0.0)
    return {
        "total_samples": sample_count,
        "total_cohort_families": int(family_counts.shape[0]),
        "training_families": training_families,
        "represented_types": int(type_counts.shape[0]),
        "top_family_share": round(top_family_share, 6),
        "banker_share": round(banker_share, 6),
    }


def write_evidence_readiness(
    *,
    run_root: Path,
    status: str,
    failed_checks: list[str],
    manifest: dict[str, Any],
    integrity_reason: str,
) -> Path:
    """Write machine-readable evidence readiness verdict."""
    pack_dir, legacy_pack_dir = _bundle_dirs(run_root)
    cohort_contract = manifest.get("cohort_contract") or manifest.get("paper_cohort_contract") or {}
    cohort_lock_status = resolve_contract_cohort_lock_status(cohort_contract)
    checks = {
        "strict_profile": coalesce_manifest_publication_mode(manifest),
        "integrity_pass": not bool(integrity_reason),
        "fallback_used": bool(manifest.get("vendor_fallback_used", False)),
        "non_standard_features": bool(manifest.get("non_standard_features", False)),
        "mandatory_artifacts_present": "mandatory_artifacts_present" not in failed_checks,
        "deterministic_split_hash_present": bool((manifest.get("split") or {}).get("split_hash")),
        "dataset_hash_present": bool(manifest.get("dataset_hash")),
        "engine_list_hash_present": bool(manifest.get("engine_list_hash")),
        "engine_ranking_hash_present": bool(manifest.get("engine_ranking_hash")),
        "manifest_complete": bool(manifest.get("run_id")),
    }
    payload = {
        "status": str(status),
        "evidence_readiness": str(status),
        "publication_ready_status": str(status),
        "cohort_lock_status": cohort_lock_status,
        "checks": checks,
        "failed_checks": sorted(set(failed_checks)),
        "integrity_reason": integrity_reason,
    }
    out_path = pack_dir / "evidence_readiness.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=out_path, legacy_dir=legacy_pack_dir)
    return out_path


def write_evidence_compliance_stub(
    *,
    run_root: Path,
    run_id: str,
    evidence_mode: bool,
    reason: str,
) -> Path:
    """Write minimal compliance stub for early-stop runs."""
    pack_dir, legacy_pack_dir = _bundle_dirs(run_root)
    out_path = pack_dir / "evidence_compliance_summary.json"
    payload = {
        "run_id": str(run_id),
        "evidence_mode": bool(evidence_mode),
        "status": "not_ready",
        "evidence_readiness": "not_ready",
        "publication_ready_status": "not_ready",
        "cohort_lock_status": "unknown",
        "reason": str(reason or ""),
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _mirror_legacy_bundle_file(source_path=out_path, legacy_dir=legacy_pack_dir)
    return out_path
