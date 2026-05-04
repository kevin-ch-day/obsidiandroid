# Filename: main.py
# Purpose  : Compatibility shim; implementation in ``obsidiandroid.cli.main``.

"""Malware classification pipeline CLI and stable import surface for tests."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if _SRC_ROOT.is_dir() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from obsidiandroid.cli.main import (  # noqa: F401
    DIAGNOSTICS_DIR,
    PIPELINE_MAIN_LOGGER,
    PARSER_QUALITY_PATH,
    _apply_confusion_matrix_policy,
    _enforce_duplicate_sha_policy,
    _export_model_config_snapshot,
    finalize_run_manifest_stage,
    load_and_prepare_samples,
    main,
    profile_manager,
    run_av_analysis_stage,
    run_pipeline,
    runtime_logging,
)

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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Pipeline aborted by user.")
        sys.exit(130)
