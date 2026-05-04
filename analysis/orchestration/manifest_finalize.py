"""Run-manifest finalization helpers for orchestration layer."""

from __future__ import annotations

from typing import Any

import pandas as pd

import obsidiandroid.governance.run_manifest as run_manifest
from utils.hash_utils import hash_payload


def finalize_run_manifest(
    manifest_context: dict[str, Any],
    profile: dict[str, Any],
    samples_df: pd.DataFrame | None,
    pipeline_results: dict[str, Any] | None,
    vendor_eval_df: pd.DataFrame | None,
    artifact_list: list[str],
) -> dict[str, Any]:
    """Build and persist run manifest payload.

    Args:
        manifest_context: Runtime context (run id, config hash, timestamp).
        profile: Active profile payload.
        samples_df: Final cohort dataframe.
        pipeline_results: Pipeline result dictionary.
        vendor_eval_df: Vendor evaluation summary dataframe.
        artifact_list: Generated artifacts for this run.

    Returns:
        Materialized manifest payload.
    """
    engine_lifecycle = None
    if isinstance(pipeline_results, dict):
        engine_lifecycle = pipeline_results.get("engine_lifecycle")
    included_engines = 0
    excluded_engines = 0
    engine_names: list[str] = []
    if isinstance(engine_lifecycle, pd.DataFrame) and not engine_lifecycle.empty:
        included_engines = int(engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool).sum())
        excluded_engines = int((~engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool)).sum())
        engine_names = sorted(
            engine_lifecycle["engine_name_canonical"].dropna().astype(str).unique().tolist()
        )

    parser_list: list[str] = []
    if isinstance(vendor_eval_df, pd.DataFrame) and "Vendor" in vendor_eval_df.columns:
        parser_list = sorted(vendor_eval_df["Vendor"].dropna().astype(str).unique().tolist())

    manifest = {
        "run_id": manifest_context.get("run_id"),
        "timestamp_utc": manifest_context.get("timestamp_utc"),
        "git_commit": run_manifest.get_git_commit(),
        "config_hash": manifest_context.get("config_hash"),
        "profile_params": profile,
        "engine_list_hash": hash_payload(engine_names),
        "parser_list_hash": hash_payload(parser_list),
        "taxonomy_version": run_manifest.compute_taxonomy_version_hash(),
        "cohort_size": int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0,
        "included_engine_count": included_engines,
        "excluded_engine_count": excluded_engines,
        "artifact_list": sorted(set(artifact_list)),
        "manifest_schema_version": run_manifest.MANIFEST_SCHEMA_VERSION,
    }
    run_manifest.write_run_manifest(manifest)
    return manifest

