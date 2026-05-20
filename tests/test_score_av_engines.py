"""Tests for AV engine scoring export behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.pipeline import score_av_engines


def test_run_av_engine_scoring_writes_run_scoped_engine_lifecycle_without_local_latest(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(score_av_engines, "export_matrix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        score_av_engines,
        "fetch_engine_metadata",
        lambda *args, **kwargs: {"engine_a": {"is_trusted_vendor": 1, "is_engine_active": 1}},
    )
    monkeypatch.setattr(
        score_av_engines.phase_score_engines,
        "score_av_engines_from_matrix",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "Engine Name": "engine_a",
                    "ML Weight Score": 42.0,
                    "Included": True,
                    "Exclusion Reason": "included",
                    "Detection Tier": "Tier 1 (High)",
                    "Coverage %": 100.0,
                    "Detection %": 50.0,
                }
            ]
        ),
    )

    matrix_df = pd.DataFrame({"sample_id": [1, 2], "engine_a": [1, 0]})
    matrix_df.attrs["engine_scan_counts"] = {"engine_a": 2}

    result = score_av_engines.run_av_engine_scoring(
        matrix_df,
        config={"run_id": "rid", "profile_context": "dev_fast"},
        verbose=False,
    )

    assert not result.empty
    run_scoped = diagnostics_dir / "engine_lifecycle_rid.csv"
    assert run_scoped.is_file()
    assert not (diagnostics_dir / "engine_lifecycle.latest.csv").exists()
    assert (output_root / "diagnostics" / "engine_lifecycle.latest.csv").is_file()
    assert isinstance(result.attrs.get("engine_lifecycle"), pd.DataFrame)


def test_lifecycle_path_uses_global_named_target_when_runtime_dir_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    diagnostics_root = output_root / "diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    assert score_av_engines._lifecycle_path() == diagnostics_root / "engine_lifecycle_rid.csv"  # pylint: disable=protected-access
