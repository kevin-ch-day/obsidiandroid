"""V3 policy tests for hostile-audit bundle export behavior."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics.hostile_audit import bundle as hostile_bundle

pytestmark = pytest.mark.contract


def test_canonical_profile_reraises_when_hostile_steps_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    artifact_list: list[str] = []

    def _cohort_fail(**_kwargs):
        raise RuntimeError("cohort population failed")

    monkeypatch.setattr(hostile_bundle, "write_cohort_population_audit", _cohort_fail)
    monkeypatch.setattr(hostile_bundle, "write_baseline_comparison", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_target_validity_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_vendor_label_leakage_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_permission_signal_quality", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_temporal_validity_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_figure_validity_audit", lambda **_kwargs: None)
    monkeypatch.setattr(hostile_bundle, "write_taxonomy_label_quality_audit", lambda **_kwargs: None)
    monkeypatch.setattr(hostile_bundle, "write_recommended_findings", lambda **_kwargs: None)

    with pytest.raises(RuntimeError, match="hostile_audit_partial_errors"):
        hostile_bundle.write_hostile_audit_bundle(
            run_root=tmp_path,
            diagnostics_dir=diagnostics_dir,
            run_id="run_hostile",
            manifest_context={},
            manifest={"profile_id": "android_malware_type_taxonomy"},
            samples_df=pd.DataFrame({"sample_id": [1]}),
            artifact_list=artifact_list,
        )


def test_non_canonical_profile_records_hostile_partial_errors_without_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    manifest_context: dict[str, object] = {}
    artifact_list: list[str] = []

    def _cohort_fail(**_kwargs):
        raise RuntimeError("cohort population failed")

    monkeypatch.setattr(hostile_bundle, "write_cohort_population_audit", _cohort_fail)
    monkeypatch.setattr(hostile_bundle, "write_baseline_comparison", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_target_validity_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_vendor_label_leakage_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_permission_signal_quality", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_temporal_validity_audit", lambda **_kwargs: (None, None))
    monkeypatch.setattr(hostile_bundle, "write_figure_validity_audit", lambda **_kwargs: None)
    monkeypatch.setattr(hostile_bundle, "write_taxonomy_label_quality_audit", lambda **_kwargs: None)
    monkeypatch.setattr(hostile_bundle, "write_recommended_findings", lambda **_kwargs: None)

    hostile_bundle.write_hostile_audit_bundle(
        run_root=tmp_path,
        diagnostics_dir=diagnostics_dir,
        run_id="run_hostile_soft",
        manifest_context=manifest_context,
        manifest={"profile_id": "dev_smoke"},
        samples_df=pd.DataFrame({"sample_id": [1]}),
        artifact_list=artifact_list,
    )

    partial_log = diagnostics_dir / "hostile_audit_partial_errors.txt"
    assert partial_log.is_file()
    assert partial_log.stat().st_size > 0
    assert manifest_context.get("hostile_audit_partial_error_count", 0) >= 1
