"""Tests for engine metadata overlay export (no matrix row append)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.pipeline import attach_engine_metadata as am
from config import app_config


def test_attach_engine_metadata_writes_overlay_without_extra_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "t_overlay", raising=False)

    def _fake_fetch(verbose: bool = True) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "engine_name": ["eng_a"],
                "detection_strategy": ["heuristic"],
                "is_trusted_vendor": [1],
                "is_engine_active": [1],
                "total_scanned": [10],
                "malicious_count": [1],
                "suspicious_count": [0],
                "benign_count": [9],
                "undetected_count": [0],
                "unknown_count": [0],
                "family_name_hits": [0],
                "coverage_pct": [0.5],
                "malicious_pct": [0.1],
                "suspicious_pct": [0.0],
                "threat_signal_score": [0.2],
            }
        )

    monkeypatch.setattr(am, "fetch_engine_metadata", _fake_fetch)
    matrix = pd.DataFrame({"sample_id": [1, 2], "eng_a": [0, 1]})
    out = am.attach_engine_metadata(matrix, verbose=False)
    assert len(out) == len(matrix)
    overlay = tmp_path / "engine_metadata_overlay_t_overlay.csv"
    assert overlay.exists()
    assert getattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "") == str(overlay)
