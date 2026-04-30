"""Tests for duplicate SHA governance policy enforcement."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import main
from config import app_config


def _labels_frame(shas: list[str]) -> pd.DataFrame:
    """Build a minimal aligned labels frame."""
    return pd.DataFrame(
        {
            "sample_id": list(range(1, len(shas) + 1)),
            "sha256": shas,
            "family_id": [10] * len(shas),
            "family_canonical": ["family_a"] * len(shas),
        }
    )


def test_duplicate_sha_policy_warns_in_non_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Duplicate SHAs should not fail in non-paper mode."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    sha = "a" * 64
    labels_df = _labels_frame([sha, sha])
    artifacts: list[str] = []
    manifest_context: dict[str, object] = {}

    main._enforce_duplicate_sha_policy(
        aligned_labels_df=labels_df,
        run_id="run123",
        artifact_list=artifacts,
        manifest_context=manifest_context,
    )

    assert "duplicate_sha" in manifest_context
    summary = manifest_context["duplicate_sha"]
    assert isinstance(summary, dict)
    assert summary.get("duplicate_sha_groups") == 1
    assert summary.get("paper_mode_hard_fail") is False
    assert any("duplicate_sha256_report_run123.csv" in path for path in artifacts)


def test_duplicate_sha_policy_hard_fails_in_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Duplicate SHAs should fail-closed in paper mode."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    sha = "b" * 64
    labels_df = _labels_frame([sha, sha])

    with pytest.raises(RuntimeError, match=r"Duplicate sha256 groups detected"):
        main._enforce_duplicate_sha_policy(
            aligned_labels_df=labels_df,
            run_id="run456",
            artifact_list=[],
            manifest_context={},
        )


def test_duplicate_sha_policy_hard_fails_on_invalid_sha_in_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid SHA values should fail-closed in paper mode."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    labels_df = _labels_frame(["not-a-sha", "c" * 64])

    with pytest.raises(RuntimeError, match=r"Invalid sha256 values detected"):
        main._enforce_duplicate_sha_policy(
            aligned_labels_df=labels_df,
            run_id="run789",
            artifact_list=[],
            manifest_context={},
        )
