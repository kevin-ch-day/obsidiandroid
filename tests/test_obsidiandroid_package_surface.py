"""Lightweight checks for new ``obsidiandroid.*`` package surfaces (no slow integration)."""

from __future__ import annotations

import pytest


def test_pipeline_facade_matches_runner_public_surface() -> None:
    """``obsidiandroid.pipeline`` should re-export the same objects as ``runner``."""
    from analysis.pipeline import runner as runner_mod
    import obsidiandroid.pipeline as facade

    assert facade.run_pipeline is runner_mod.run_pipeline
    assert facade.DIAGNOSTICS_DIR == runner_mod.DIAGNOSTICS_DIR
    assert facade.PIPELINE_MAIN_LOGGER is runner_mod.PIPELINE_MAIN_LOGGER
    assert facade.PARSER_QUALITY_PATH == runner_mod.PARSER_QUALITY_PATH


def test_common_repo_paths_ensure_is_idempotent() -> None:
    """Repeated calls must not duplicate the checkout ``src`` entry."""
    import sys
    from pathlib import Path

    from obsidiandroid.common import repo_paths

    here = Path(repo_paths.__file__).resolve()
    if len(here.parents) < 3 or here.parents[2].name != "src":
        pytest.skip("repo_paths not loaded from a checkout tree under src/")
    src = str(here.parents[2])
    repo_paths.ensure_repo_src_on_sys_path()
    repo_paths.ensure_repo_src_on_sys_path()
    assert sys.path.count(src) == 1
