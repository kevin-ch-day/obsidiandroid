"""Tests for permission feature extraction fault-handling behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from analysis.orchestration import permission_features


def test_permission_fetch_sets_degraded_flag_on_db_error(monkeypatch) -> None:
    """DB fetch failures should set degraded flag and return baseline frame."""
    monkeypatch.setattr(permission_features.app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)
    monkeypatch.setattr(
        permission_features.app_config,
        "PERMISSION_ENRICHMENT_STRICT_IN_EVIDENCE",
        False,
        raising=False,
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(permission_features.db_engine, "execute_query", _raise)
    samples_df = pd.DataFrame({"sample_id": [1, 2]})
    out = permission_features.build_permission_feature_frame(samples_df)

    assert list(out.columns) == ["sample_id"]
    assert bool(permission_features.app_config.RUNTIME_PERMISSION_ENRICHMENT_DEGRADED) is True


def test_permission_fetch_strict_evidence_raises_integrity(monkeypatch) -> None:
    """Strict evidence mode should hard-fail when permission enrichment query fails."""
    monkeypatch.setattr(permission_features.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(
        permission_features.app_config,
        "PERMISSION_ENRICHMENT_STRICT_IN_EVIDENCE",
        True,
        raising=False,
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(permission_features.db_engine, "execute_query", _raise)
    samples_df = pd.DataFrame({"sample_id": [1]})
    with pytest.raises(RuntimeError) as exc:
        permission_features.build_permission_feature_frame(samples_df)
    assert "[INTEGRITY]" in str(exc.value)
