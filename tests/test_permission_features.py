"""Tests for permission feature extraction fault-handling behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.orchestration import permission_features


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

    monkeypatch.setattr(permission_features.db_engine, "execute_permission_query", _raise)
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

    monkeypatch.setattr(permission_features.db_engine, "execute_permission_query", _raise)
    samples_df = pd.DataFrame({"sample_id": [1]})
    with pytest.raises(RuntimeError) as exc:
        permission_features.build_permission_feature_frame(samples_df)
    assert "[INTEGRITY]" in str(exc.value)


def test_permission_features_prefer_permission_string_norm_when_available(monkeypatch) -> None:
    monkeypatch.setattr(permission_features, "_PERMISSION_OBS_NORM_AVAILABLE", None)
    monkeypatch.setattr(
        permission_features.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )
    captured: dict[str, object] = {}

    def _fake_execute_permission_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return pd.DataFrame(
            {
                "sample_id": [1, 1],
                "permission_string_raw": [
                    "android.permission.READ_SMS",
                    "ANDROID.PERMISSION.read_sms",
                ],
                "permission_string": [
                    "android.permission.read_sms",
                    "android.permission.read_sms",
                ],
                "permission_source": ["AOSP", "AOSP"],
                "protection_level": ["DANGEROUS", "DANGEROUS"],
            }
        )

    monkeypatch.setattr(
        permission_features.db_engine,
        "execute_permission_query",
        _fake_execute_permission_query,
    )
    out = permission_features.build_permission_feature_frame(
        pd.DataFrame({"sample_id": [1]}),
        min_permission_support=1,
    )

    assert "permission_string_norm" in str(captured.get("query", ""))
    assert bool(captured["kwargs"]["as_dataframe"]) is True
    assert "perm__android_permission_read_sms" in out.columns
    assert int(out.loc[out["sample_id"] == 1, "perm__android_permission_read_sms"].iloc[0]) == 1


def test_permission_features_fall_back_when_permission_string_norm_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(permission_features, "_PERMISSION_OBS_NORM_AVAILABLE", None)
    monkeypatch.setattr(
        permission_features.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string"],
    )
    captured: dict[str, object] = {}

    def _fake_execute_permission_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return pd.DataFrame(
            {
                "sample_id": [1, 1],
                "permission_string_raw": [
                    "android.permission.READ_SMS",
                    "ANDROID.PERMISSION.read_sms",
                ],
                "permission_string": [
                    "android.permission.read_sms",
                    "android.permission.read_sms",
                ],
                "permission_source": ["AOSP", "AOSP"],
                "protection_level": ["DANGEROUS", "DANGEROUS"],
            }
        )

    monkeypatch.setattr(
        permission_features.db_engine,
        "execute_permission_query",
        _fake_execute_permission_query,
    )
    out = permission_features.build_permission_feature_frame(
        pd.DataFrame({"sample_id": [1]}),
        min_permission_support=1,
    )

    assert "permission_string_norm" not in str(captured.get("query", ""))
    assert "LOWER(TRIM(ops.permission_string)) AS permission_string" in str(captured.get("query", ""))
    assert bool(captured["kwargs"]["as_dataframe"]) is True
    assert "perm__android_permission_read_sms" in out.columns
    assert int(out.loc[out["sample_id"] == 1, "perm__android_permission_read_sms"].iloc[0]) == 1
