from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.hostile_audit import permission_signal_quality as psq
from obsidiandroid.diagnostics.research_validity.permission_signal_seed import SIGNAL_CATALOG_ROWS
from obsidiandroid.diagnostics.research_validity.permission_signal_seed import SIGNAL_MAPPING_ROWS
from scripts.diagnostics import generate_permission_pattern_interpretation as gppi


def _catalog_row(signal_key: str) -> dict[str, object]:
    return next(row for row in SIGNAL_CATALOG_ROWS if row["signal_key"] == signal_key)


def _mapping_row(signal_key: str, perm_name: str) -> dict[str, object]:
    return next(
        row
        for row in SIGNAL_MAPPING_ROWS
        if row["signal_key"] == signal_key and row["perm_name"] == perm_name
    )


def test_scaffolding_lanes_are_model_yes_behavioral_no() -> None:
    row = _catalog_row("app_defined_scaffolding")
    assert row["include_in_model_features"] is True
    assert row["include_in_behavioral_claims"] is False
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("app_defined_scaffolding", "app_defined_dynamic_receiver_guard")
    assert mapping["mapping_basis"] == "remediation_lane"
    assert mapping["include_in_model_features"] is True
    assert mapping["include_in_behavioral_claims"] is False


def test_aosp_dangerous_permissions_can_be_behavioral_yes() -> None:
    row = _catalog_row("sms")
    assert row["include_in_behavioral_claims"] is True
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("sms", "android.permission.read_sms")
    assert mapping["mapping_basis"] == "exact_permission"
    assert mapping["include_in_behavioral_claims"] is True
    assert mapping["candidate_behavior_area"] == "messaging_access"
    assert mapping["mitre_candidate_tactic"] == "collection"


def test_needs_source_validation_stays_behavioral_no() -> None:
    row = _catalog_row("aosp_hidden_privileged")
    assert row["include_in_model_features"] is True
    assert row["include_in_behavioral_claims"] is False
    assert row["mitre_candidate_only"] is True

    mapping = _mapping_row("aosp_hidden_privileged", "needs_source_validation")
    assert mapping["mapping_basis"] == "remediation_lane"
    assert mapping["include_in_model_features"] is False
    assert mapping["include_in_behavioral_claims"] is False


def test_mitre_fields_remain_candidate_only() -> None:
    assert all(bool(row["mitre_candidate_only"]) for row in SIGNAL_CATALOG_ROWS)
    assert all("technique" not in str(row.get("candidate_behavior_area", "")).lower() for row in SIGNAL_MAPPING_ROWS)


def test_write_permission_signal_quality_rebuilds_permission_frame_silently(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_permission_rows(_sample_ids):
        return pd.DataFrame(columns=["sample_id", "permission_string"])

    def fake_build_permission_enrichment_frame(samples_df, feature_flags, **kwargs):
        captured["log_frame_built"] = kwargs.get("log_frame_built")
        return pd.DataFrame(
            {
                "sample_id": samples_df["sample_id"].tolist(),
                "perm__android_permission_internet": [1.0] * len(samples_df),
                "perm__total_count": [1] * len(samples_df),
            }
        )

    monkeypatch.setattr(psq, "_fetch_permission_rows", fake_fetch_permission_rows)
    monkeypatch.setattr(psq, "build_permission_enrichment_frame", fake_build_permission_enrichment_frame)

    csv_path, md_path = psq.write_permission_signal_quality(
        diagnostics_dir=tmp_path,
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["FamA", "FamB"],
            }
        ),
    )

    assert captured["log_frame_built"] is False
    assert csv_path and csv_path.is_file()
    assert md_path and md_path.is_file()


def test_generate_permission_pattern_interpretation_resolves_archived_run_id(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    run_id = "20260303T000000Z__abc123"
    run_root = repo_root / "output" / "runs" / "_archived" / "kept" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        '{"run_id":"20260303T000000Z__abc123","run_root":"%s","created_at_utc":"2026-03-03T00:00:00+00:00"}'
        % str(run_root),
        encoding="utf-8",
    )

    got = gppi._resolve_run_root(  # pylint: disable=protected-access
        repo_root=repo_root,
        run_id=run_id,
    )

    assert got == run_root.resolve()


def test_generate_permission_pattern_interpretation_latest_prefers_manifest_backed_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    run_id = "20260303T000000Z__abc123"
    run_root = repo_root / "output" / "runs" / "_archived" / "kept" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        '{"run_id":"20260303T000000Z__abc123","run_root":"%s","created_at_utc":"2026-03-03T00:00:00+00:00"}'
        % str(run_root),
        encoding="utf-8",
    )
    monkeypatch.setattr(gppi.rl, "read_latest_run_id", lambda: run_id)

    got = gppi._resolve_run_root(  # pylint: disable=protected-access
        repo_root=repo_root,
        latest=True,
    )

    assert got == run_root.resolve()
