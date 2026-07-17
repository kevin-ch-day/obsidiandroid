"""canonical policy tests for research-validity bundle export behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics.research_validity import bundle as rv_bundle

pytestmark = pytest.mark.contract


def test_canonical_profile_reraises_contract_report_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    manifest_context: dict[str, object] = {}
    artifact_list: list[str] = []

    monkeypatch.setattr(rv_bundle, "finalize_cohort_funnel_dict", lambda _ctx: None)
    monkeypatch.setattr(rv_bundle, "write_cohort_funnel_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_signal_decomposition_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_permission_feature_audit_csv", lambda **_kwargs: None)
    monkeypatch.setattr(rv_bundle, "write_permission_intel_audit_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_validity_figures", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_type_permission_figure_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(rv_bundle, "write_paper_claim_audit_md", lambda **_kwargs: tmp_path / "claim.md")
    monkeypatch.setattr(rv_bundle, "write_hostile_audit_bundle", lambda **_kwargs: [])

    def _raise_contract_reports(**_kwargs) -> tuple[None, None, None]:
        raise RuntimeError("contract reports unavailable")

    monkeypatch.setattr(rv_bundle, "write_headline_vs_ablation_contract_reports", _raise_contract_reports)

    with pytest.raises(RuntimeError, match="contract reports unavailable"):
        rv_bundle.write_research_validity_bundle(
            run_root=tmp_path,
            diagnostics_dir=diagnostics_dir,
            run_id="run_rv_fail",
            manifest_context=manifest_context,
            manifest={"profile_id": "android_malware_major_families"},
            samples_df=pd.DataFrame({"sample_id": [1]}),
            artifact_list=artifact_list,
            paper_mode=False,
        )


def test_canonical_profile_requires_cohort_samples_for_research_validity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    manifest_context: dict[str, object] = {}
    artifact_list: list[str] = []

    with pytest.raises(RuntimeError, match="canonical_profile_research_validity_requires_cohort_samples"):
        rv_bundle.write_research_validity_bundle(
            run_root=tmp_path,
            diagnostics_dir=diagnostics_dir,
            run_id="run_no_cohort",
            manifest_context=manifest_context,
            manifest={"profile_id": "android_malware_all_current", "cohort_size": 10},
            samples_df=None,
            artifact_list=artifact_list,
            paper_mode=False,
        )


def test_non_canonical_profile_records_partial_contract_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    manifest_context: dict[str, object] = {}
    artifact_list: list[str] = []

    monkeypatch.setattr(rv_bundle, "finalize_cohort_funnel_dict", lambda _ctx: None)
    monkeypatch.setattr(rv_bundle, "write_cohort_funnel_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_signal_decomposition_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_permission_feature_audit_csv", lambda **_kwargs: None)
    monkeypatch.setattr(rv_bundle, "write_permission_intel_audit_artifacts", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_validity_figures", lambda **_kwargs: [])
    monkeypatch.setattr(rv_bundle, "write_type_permission_figure_bundle", lambda **_kwargs: None)
    monkeypatch.setattr(rv_bundle, "write_paper_claim_audit_md", lambda **_kwargs: tmp_path / "claim.md")
    monkeypatch.setattr(rv_bundle, "write_hostile_audit_bundle", lambda **_kwargs: [])

    def _raise_contract_reports(**_kwargs) -> tuple[None, None, None]:
        raise RuntimeError("contract reports unavailable")

    monkeypatch.setattr(rv_bundle, "write_headline_vs_ablation_contract_reports", _raise_contract_reports)

    rv_bundle.write_research_validity_bundle(
        run_root=tmp_path,
        diagnostics_dir=diagnostics_dir,
        run_id="run_rv_soft",
        manifest_context=manifest_context,
        manifest={"profile_id": "dev_smoke"},
        samples_df=pd.DataFrame({"sample_id": [1]}),
        artifact_list=artifact_list,
        paper_mode=False,
    )

    partial = manifest_context.get("research_validity_partial_failures")
    assert isinstance(partial, list)
    assert partial and partial[0]["step"] == "contract_and_taxonomy_reports"
