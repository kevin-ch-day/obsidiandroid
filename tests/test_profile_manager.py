"""Tests for profile loading contract."""

from pathlib import Path

import obsidiandroid.cli.profile_manager as profile_manager


def test_profile_list_contains_default_profiles() -> None:
    """Profiles directory should contain baseline profiles."""
    names = [p.stem for p in profile_manager.list_profiles()]
    assert "banker" in names
    assert "banker_locked" in names
    assert "mixed" in names
    assert "benign_heavy" in names
    assert "dev_smoke" in names
    assert "paper2_primary_locked" not in names
    assert "paper1_banker_locked" not in names


def test_load_profile_required_keys() -> None:
    """Loaded profile must satisfy required key contract."""
    profile = profile_manager.load_profile("banker")
    for key in ("profile_id", "type_slug_filter", "cohort_gates", "model_list"):
        assert key in profile


def test_load_profile_resolves_bundled_profiles_outside_repo_cwd(
    monkeypatch, tmp_path: Path
) -> None:
    """Built-in profiles should resolve independently of the process cwd."""
    monkeypatch.chdir(tmp_path)
    profile = profile_manager.load_profile("banker")
    assert profile["profile_id"] == "banker"
    assert profile["__profile_path"].endswith("profiles/banker.yaml")


def test_temporal_evidence_profiles_exclude_dominant_families() -> None:
    """Temporal evidence profiles should exclude dominant families for balanced cross-type analysis."""
    expected = {"devixor", "gigabud"}
    for profile_id in (
        "malicious_temporal_stability",
        "malicious_temporal_consensus10",
        "malicious_temporal_family300",
    ):
        profile = profile_manager.load_profile(profile_id)
        excluded = {
            str(family).strip().lower()
            for family in profile.get("cohort_gates", {}).get("exclude_families", [])
            if str(family).strip()
        }
        assert expected.issubset(excluded)


def test_profile_sorting_prefers_locked_and_core_profiles() -> None:
    """Sort key should rank locked publication-ready profiles before misc entries."""
    ordered = sorted(
        [
            "spyware",
            "malicious_temporal_stability_locked",
            "banker_locked",
            "malicious_temporal_family300",
            "dev_smoke",
            "dev_fast",
            "malicious_temporal_stability",
            "banker",
        ],
        key=profile_manager._profile_sort_key,  # pylint: disable=protected-access
    )
    assert ordered[0] == "malicious_temporal_stability_locked"
    assert ordered[1] == "banker_locked"
    assert ordered[2] == "malicious_temporal_stability"
    assert ordered[3] == "malicious_temporal_family300"
    assert ordered[4] == "banker"
    assert ordered[-2] == "dev_fast"
    assert ordered[-1] == "dev_smoke"


def test_profile_summary_includes_key_gates(tmp_path: Path) -> None:
    """Profile summary should expose high-value selection fields."""
    profile_path = tmp_path / "sample.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: sample",
                "description: Example profile",
                "type_slug_filter: banker",
                "cohort_gates:",
                "  min_malicious_detections: 10",
                "  family_cap: 300",
                "  exclude_unknown_type_slug: true",
                "model_list:",
                "  - logistic_regression",
            ]
        ),
        encoding="utf-8",
    )
    summary = profile_manager._summarize_profile(profile_path)  # pylint: disable=protected-access
    assert "type=banker" in summary
    assert "min_detect=10" in summary
    assert "family_cap=300" in summary
    assert "exclude_unknown=True" in summary


def test_profile_summary_exposes_locked_status(tmp_path: Path) -> None:
    """Profile summary should label locked vs legacy publication profiles explicitly."""
    locked = tmp_path / "locked.yaml"
    locked.write_text(
        "\n".join(
            [
                "profile_id: malicious_temporal_stability_locked",
                "description: Locked profile",
                "paper_locked: true",
                "type_slug_filter: all",
                "cohort_gates: {}",
                "model_list:",
                "  - random_forest",
                "paper_lock:",
                "  contract_id: malicious_temporal_stability_locked_contract",
                "  expected_sample_count: 1226",
                "  expected_family_count: 39",
                "  expected_type_count: 6",
                "  sample_id_lock_file: artifacts/baselines/20260504T044304Z__8c64e6/malicious_temporal_stability_locked_sample_ids.csv",
            ]
        ),
        encoding="utf-8",
    )
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text(
        "\n".join(
            [
                "profile_id: malicious_temporal_stability",
                "description: Legacy profile",
                "evidence_mode: true",
                "type_slug_filter: all",
                "cohort_gates:",
                "  time_window_start_utc: '2020-01-01T00:00:00Z'",
                "  time_window_end_utc: '2026-01-01T00:00:00Z'",
                "model_list:",
                "  - random_forest",
            ]
        ),
        encoding="utf-8",
    )
    locked_summary = profile_manager._summarize_profile(locked)  # pylint: disable=protected-access
    legacy_summary = profile_manager._summarize_profile(legacy)  # pylint: disable=protected-access
    assert "lock=membership-locked" in locked_summary
    assert "publication=unlocked" in legacy_summary


def test_quick_profile_label_prefers_operator_facing_descriptions() -> None:
    """Quick profile menu should lead with human labels instead of raw profile ids."""
    assert profile_manager.profile_selection.quick_profile_label(
        "malicious_temporal_stability_locked"
    ) == "Publication-ready: locked all-malicious baseline"
    assert profile_manager.profile_selection.quick_profile_label(
        "research_all_malicious"
    ) == "Exploratory: all-malicious research cohort"
    assert profile_manager.profile_selection.quick_profile_label(
        "dev_smoke"
    ) == "Smoke: ultra-fast sanity check"


def test_legacy_profile_aliases_resolve_to_generic_names() -> None:
    """Deprecated paper-number profile ids should resolve to generic canonical profiles."""
    assert profile_manager.load_profile("paper2_primary")["profile_id"] == "malicious_temporal_stability"
    assert profile_manager.load_profile("paper2_primary_locked")["profile_id"] == "malicious_temporal_stability_locked"
    assert profile_manager.load_profile("paper1_banker_locked")["profile_id"] == "banker_locked"


def test_infer_cohort_readiness_signal_maps_banker_profiles() -> None:
    signal = profile_manager.infer_cohort_readiness_signal("banker_locked")
    assert signal["bucket"] == "android_banker_with_permission_obs"
    assert "Best matching readiness bucket" in str(signal["summary"])


def test_infer_cohort_readiness_signal_maps_temporal_and_all_malicious_profiles() -> None:
    temporal = profile_manager.infer_cohort_readiness_signal("malicious_temporal_stability_locked")
    exploratory = profile_manager.infer_cohort_readiness_signal("all_malicious")
    assert temporal["bucket"] == "android_high_or_strong_vt_with_permission_obs"
    assert "high/strong VT confidence" in str(temporal["detail"])
    assert exploratory["bucket"] == "android_with_permission_obs"
    assert "permission observations." in str(exploratory["detail"])


def test_infer_cohort_readiness_signal_maps_hidden_paper2_profiles_by_intent() -> None:
    primary = profile_manager.infer_cohort_readiness_signal("paper2_primary")
    sensitivity = profile_manager.infer_cohort_readiness_signal("paper2_sensitivity_consensus10")
    assert primary["bucket"] == "android_high_or_strong_vt_with_permission_obs"
    assert sensitivity["bucket"] == "android_high_or_strong_vt_with_permission_obs"


def test_infer_cohort_readiness_signal_returns_unmapped_advisory_for_unknown_profile() -> None:
    signal = profile_manager.infer_cohort_readiness_signal("definitely_unknown_profile")
    assert signal["bucket"] is None
    assert str(signal["summary"]) == "No readiness bucket mapped for this profile; review cohort filters manually."


def test_infer_cohort_readiness_signal_maps_broad_android_profiles_to_android_platform() -> None:
    mixed = profile_manager.infer_cohort_readiness_signal("mixed")
    benign_heavy = profile_manager.infer_cohort_readiness_signal("benign_heavy")
    assert mixed["bucket"] == "android_platform"
    assert benign_heavy["bucket"] == "android_platform"


def test_inventory_cohort_readiness_mappings_covers_all_profile_files() -> None:
    inventory = profile_manager.inventory_cohort_readiness_mappings()
    profile_paths = sorted(p for p in profile_manager.PROFILES_DIR.glob("*.yaml"))
    assert len(inventory) == len(profile_paths)
    assert all(row["status"] in {"mapped", "ambiguous"} for row in inventory)
    assert all("summary" in row for row in inventory)
    assert all("detail" in row for row in inventory)


def test_inventory_cohort_readiness_mappings_current_catalog_has_no_ambiguous_entries() -> None:
    inventory = profile_manager.inventory_cohort_readiness_mappings()
    ambiguous = [row["profile_id"] for row in inventory if row["status"] != "mapped"]
    assert ambiguous == []


def test_load_profile_rejects_unknown_model_key(tmp_path: Path, monkeypatch) -> None:
    """Profile loader should fail fast on unsupported model ids."""
    profile_path = tmp_path / "invalid_model.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: invalid_model",
                "type_slug_filter: banker",
                "cohort_gates: {}",
                "model_list:",
                "  - definitely_not_a_model",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_manager, "PROFILES_DIR", tmp_path)
    try:
        profile_manager.load_profile("invalid_model")
        assert False, "Expected ValueError for unsupported model id"
    except ValueError as exc:
        assert "unsupported model_list entries" in str(exc)


def test_load_profile_rejects_unknown_cohort_gate_key(tmp_path: Path, monkeypatch) -> None:
    """Profile loader should fail fast on unsupported cohort_gates keys."""
    profile_path = tmp_path / "invalid_gate.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: invalid_gate",
                "type_slug_filter: banker",
                "cohort_gates:",
                "  unexpected_gate: true",
                "model_list:",
                "  - logistic_regression",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_manager, "PROFILES_DIR", tmp_path)
    try:
        profile_manager.load_profile("invalid_gate")
        assert False, "Expected ValueError for unsupported cohort gate key"
    except ValueError as exc:
        assert "unsupported cohort_gates keys" in str(exc)


def test_load_profile_rejects_evidence_mode_without_explicit_temporal_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    """Evidence-mode profiles must declare explicit start and end time bounds."""
    profile_path = tmp_path / "evidence_missing_bounds.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile_id: evidence_missing_bounds",
                "evidence_mode: true",
                "type_slug_filter: all",
                "cohort_gates:",
                "  min_samples_per_family: 20",
                "model_list:",
                "  - random_forest",
                "  - xgboost",
                "  - logistic_regression",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_manager, "PROFILES_DIR", tmp_path)
    try:
        profile_manager.load_profile("evidence_missing_bounds")
        assert False, "Expected ValueError for missing explicit evidence-mode temporal bounds"
    except ValueError as exc:
        assert "Evidence-mode profile requires explicit time_window_start_utc and time_window_end_utc" in str(exc)
