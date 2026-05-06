# Filename: main.py
# Purpose  : Thin CLI entry — ``run_pipeline`` lives in ``obsidiandroid.pipeline.runner``.

"""Malware classification pipeline CLI and stable import surface for tests."""

from __future__ import annotations

import sys

from obsidiandroid.orchestration.runtime_reporting import (
    apply_confusion_matrix_policy as _apply_confusion_matrix_policy,
    enforce_duplicate_sha_policy as _enforce_duplicate_sha_policy,
    export_model_config_snapshot as _export_model_config_snapshot,
)
from obsidiandroid.pipeline import (
    DIAGNOSTICS_DIR,
    PIPELINE_MAIN_LOGGER,
    PARSER_QUALITY_PATH,
    stage_av_vendor,
    stage_manifest,
    stage_samples,
    run_pipeline,
)
import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.observability.logging import runtime as runtime_logging

__all__ = [
    "DIAGNOSTICS_DIR",
    "PIPELINE_MAIN_LOGGER",
    "PARSER_QUALITY_PATH",
    "run_pipeline",
    "main",
    "_apply_confusion_matrix_policy",
    "_enforce_duplicate_sha_policy",
    "_export_model_config_snapshot",
    "finalize_run_manifest_stage",
    "load_and_prepare_samples",
    "profile_manager",
    "run_av_analysis_stage",
    "runtime_logging",
]

run_av_analysis_stage = stage_av_vendor.run_av_analysis_stage
finalize_run_manifest_stage = stage_manifest.finalize_run_manifest_stage
load_and_prepare_samples = stage_samples.load_and_prepare_samples


def main() -> int:
    """Execute the full malware classification workflow."""
    allow_override = "--allow-evidence-override" in sys.argv[1:]
    allow_global = "--allow-global-artifacts" in sys.argv[1:]
    return run_pipeline(
        allow_evidence_override=allow_override,
        allow_global_artifacts=allow_global,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Pipeline aborted by user.")
        sys.exit(130)
