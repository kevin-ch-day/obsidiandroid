"""Tests for ablation registry field selection policy."""

import pandas as pd

from obsidiandroid.pipeline.ablation import registry


def test_resolve_vendor_include_fields_stays_full_under_evidence_controls(monkeypatch) -> None:
    """Ablation registry keeps the risky lexical surface available for leakage comparison."""

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)
    assert registry._resolve_vendor_include_fields() == [
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    assert registry._resolve_vendor_include_fields() == [
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)
    assert registry._resolve_vendor_include_fields() == [
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]


def test_build_experiment_matrix_dict_keeps_vendor_experiments_semantically_distinct_in_evidence_mode(
    monkeypatch,
) -> None:
    """vendor_full/full_fused should not collapse onto vendor_no_parsed_family in evidence mode."""
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)

    captured: list[tuple[list[str], bool]] = []

    def _fake_build_vendor_matrix(
        _weights_df,
        _parsed_data,
        include_fields,
        extra_features_df=None,
        cohort_sample_ids=None,
    ):
        del cohort_sample_ids
        captured.append((list(include_fields), extra_features_df is not None))
        return pd.DataFrame({"f1": [1.0]}, index=[1])

    monkeypatch.setattr(registry, "build_vendor_matrix", _fake_build_vendor_matrix)

    builders = registry.build_experiment_matrix_dict(
        weights_df=pd.DataFrame(),
        parsed_data={},
        permission_features_df=pd.DataFrame({"sample_id": [1], "perm_grp__sms_telephony_count": [1]}),
        pipeline_results=None,
        cohort_sample_ids=[1],
        permissions_band_builder=lambda _df, _subset: pd.DataFrame({"perm_grp__sms_telephony_count": [1]}, index=[1]),
    )

    builders["vendor_full"]()
    builders["vendor_no_parsed_family"]()
    builders["full_fused"]()

    assert captured[0] == (["Parsed Family", "Threat Class", "Malware Type"], False)
    assert captured[1] == (["Threat Class", "Malware Type"], False)
    assert captured[2] == (["Parsed Family", "Threat Class", "Malware Type"], True)
