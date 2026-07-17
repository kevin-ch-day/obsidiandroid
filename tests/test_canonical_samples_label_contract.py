"""Samples-stage canonical label contract export policy tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.pipeline import stage_samples

pytestmark = pytest.mark.contract


def _stub_samples_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None)
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_readiness_report", lambda _df, gates=None: None)
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 1, "final_count_estimate": 1},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "alpha",
                    "type_slug": "banker",
                    "permissions": 1,
                    "android_package_name": "pkg",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort", "non_android_lane_rows": 0},
    )
    monkeypatch.setattr(stage_samples.cohort_foundation_export, "export_cohort_foundation_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(stage_samples.android_authority_drift_report, "export_android_authority_drift_reports", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples.cohort_family_feed_risk, "export_family_feed_risk_reports", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples.family_label_taxonomy_audit, "write_family_label_taxonomy_audit", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples.family_label_confidence_audit, "export_family_label_confidence_reports", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_cohort_lock_artifacts", lambda **_kwargs: ("lock.json", "membership.csv"))
    return []


def test_label_contract_export_runs_when_taxonomy_target_surface_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _stub_samples_stage(monkeypatch, tmp_path)
    calls: list[str] = []

    def _taxonomy_fail(**_kwargs) -> list[str]:
        raise RuntimeError("taxonomy target surface unavailable")

    def _label_contract_ok(**_kwargs) -> list[str]:
        calls.append("label_contract")
        diagnostics_dir = Path(_kwargs["diagnostics_dir"])
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        run_id = str(_kwargs["run_id"])
        json_path = diagnostics_dir / f"label_contract_{run_id}.json"
        json_path.write_text("{}", encoding="utf-8")
        return [str(json_path)]

    monkeypatch.setattr(
        stage_samples.taxonomy_target_surface_report,
        "export_taxonomy_target_surface_reports",
        _taxonomy_fail,
    )
    monkeypatch.setattr(stage_samples.label_contract, "export_label_contract", _label_contract_ok)

    out = stage_samples.load_and_prepare_samples(
        profile={"profile_id": "android_malware_major_families", "cohort_gates": {}},
        profile_id="android_malware_major_families",
        type_slug="banker",
        run_id="run_label_contract",
        artifact_list=artifacts,
    )

    assert int(out.shape[0]) == 1
    assert calls == ["label_contract"]


def test_label_contract_export_hard_fails_for_canonical_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = _stub_samples_stage(monkeypatch, tmp_path)

    monkeypatch.setattr(
        stage_samples.taxonomy_target_surface_report,
        "export_taxonomy_target_surface_reports",
        lambda **_kwargs: [],
    )

    def _label_contract_fail(**_kwargs) -> list[str]:
        raise RuntimeError("label contract export blocked")

    monkeypatch.setattr(stage_samples.label_contract, "export_label_contract", _label_contract_fail)

    with pytest.raises(RuntimeError, match="label contract export blocked"):
        stage_samples.load_and_prepare_samples(
            profile={"profile_id": "android_malware_type_taxonomy", "cohort_gates": {}},
            profile_id="android_malware_type_taxonomy",
            type_slug="banker",
            run_id="run_label_contract_fail",
            artifact_list=artifacts,
        )
