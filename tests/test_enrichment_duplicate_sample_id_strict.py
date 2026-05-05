"""Fail-closed duplicate sample_id handling in evidence/paper enrichment."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_feature_enrichment as sfe
from config import app_config


def test_duplicate_sample_id_raises_in_evidence_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "r_dup", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_DUPLICATE_SAMPLE_ID_ENRICHMENT_FUSE", False, raising=False)
    enriched = pd.DataFrame({"sample_id": [1, 1], "malicious_ratio": [0.1, 0.2]})
    samples = pd.DataFrame({"sample_id": [1, 2], "permissions": [3, 4]})
    with pytest.raises(ValueError, match="Duplicate sample_id"):
        sfe.merge_sample_metadata_features(
            enriched,
            samples,
            {"enable_sample_metadata_features": True},
            None,
        )


def test_duplicate_sample_id_allowed_with_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "r_ok", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_DUPLICATE_SAMPLE_ID_ENRICHMENT_FUSE", True, raising=False)
    enriched = pd.DataFrame({"sample_id": [1, 1], "malicious_ratio": [0.1, 0.2]})
    samples = pd.DataFrame({"sample_id": [1, 2], "permissions": [3, 4]})
    out = sfe.merge_sample_metadata_features(
        enriched,
        samples,
        {"enable_sample_metadata_features": True},
        None,
    )
    assert out is not None
    assert not out["sample_id"].duplicated().any()
