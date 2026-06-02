"""Tests for profile loading contract."""

from pathlib import Path

import pytest

import obsidiandroid.cli.profile_manager as profile_manager
from obsidiandroid.cli import profile_selection


def test_profile_list_contains_default_profiles() -> None:
    """Profiles directory should contain baseline profiles."""
    names = [p.stem for p in profile_manager.list_profiles()]
    assert "android_malware_all_current" in names
    assert "android_malware_major_families" in names
    assert "android_malware_expanded_families" in names
    assert "android_malware_type_taxonomy" in names
    assert "banker" in names
    assert "banker_locked" in names
    assert "malicious_temporal_stability_expanded" in names
    assert "malicious_temporal_stability_long_tail" in names
    assert "mixed" in names
    assert "benign_heavy" in names
    assert "dev_smoke" in names
    assert "paper2_primary_locked" not in names
    assert "paper1_banker_locked" not in names
    assert "paper2_primary" not in names
    assert "research_all_malicious" not in names
    assert "all_malicious" not in names


def test_load_profile_required_keys() -> None:
    """Loaded profile must satisfy required key contract."""
    profile = profile_manager.load_profile("banker")
    for key in ("profile_id", "type_slug_filter", "cohort_gates", "model_list"):
        assert key in profile
    assert profile["profile_status"]["lifecycle"] == "final_canonical"
    assert profile["profile_status"]["operator_surface"] == "supported"


def test_all_current_profile_uses_diagnostic_only_support_floor() -> None:
    profile = profile_manager.load_profile("android_malware_all_current")
    gates = profile.get("cohort_gates", {})
    runtime_overrides = profile.get("runtime_overrides", {})

    assert gates.get("support_floor_mode") == "diagnostic_only"
    assert gates.get("min_samples_per_family") is None
    assert runtime_overrides.get("ENABLE_CROSS_VALIDATION") is False
    assert runtime_overrides.get("ENABLE_CV_REBALANCING") is False
    assert runtime_overrides.get("ENABLE_ABLATION_EXPERIMENTS") is False
    assert runtime_overrides.get("ENABLE_DETAILED_PER_CLASS_REPORTS") is False

def test_major_family_profile_resolves_include_families_from_authority() -> None:
    profile = profile_manager.load_profile("android_malware_major_families")
    gates = profile.get("cohort_gates", {})

    assert profile.get("evidence_mode") is False
    assert profile.get("paper_locked") is False
    assert gates.get("support_floor_mode") == "benchmark_eligibility"
    assert gates.get("min_samples_per_family") == 3
    assert gates.get("include_families_from_authority") == "major_families"
    include_families = gates.get("include_families", [])
    assert isinstance(include_families, list)
    assert len(include_families) == 39
    assert "spynote" in include_families
    assert "donot" in include_families


def test_expanded_family_profile_uses_benchmark_eligibility_support_floor() -> None:
    profile = profile_manager.load_profile("android_malware_expanded_families")
    gates = profile.get("cohort_gates", {})

    assert gates.get("support_floor_mode") == "benchmark_eligibility"
    assert gates.get("min_samples_per_family") == 3


def test_major_family_profile_yaml_references_authority_instead_of_copying_family_list() -> None:
    raw_path = profile_manager.PROFILES_DIR / "android_malware_major_families.yaml"
    raw_text = raw_path.read_text(encoding="utf-8")

    assert "include_families_from_authority: major_families" in raw_text
    assert "\n  include_families:\n" not in raw_text


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
        "malicious_temporal_stability_expanded",
        "malicious_temporal_stability_long_tail",
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


def test_dev_smoke_profile_uses_richer_android_feature_feed() -> None:
    """Smoke profile should exercise governed Android breadth, not AV-only narrow slices."""
    profile = profile_manager.load_profile("dev_smoke")
    gates = profile.get("cohort_gates", {})
    feature_flags = profile.get("feature_flags", {})
    runtime_overrides = profile.get("runtime_overrides", {})

    assert gates.get("limit") == 1200
    assert gates.get("family_cap") == 35
    assert gates.get("family_cap_seed") == 1337
    assert gates.get("type_cap") == 160
    assert gates.get("type_cap_seed") == 1337
    assert gates.get("type_cap_by_slug") == {
        "banker": 90,
        "rat": 55,
        "spyware": 55,
        "adware": 40,
        "dropper": 40,
    }
    assert gates.get("min_family_label_confidence_score") == 80
    assert gates.get("exclude_weak_label_kinds") is True
    assert gates.get("exclude_family_label_conflicts") is True
    assert feature_flags.get("enable_sample_metadata_features") is True
    assert feature_flags.get("enable_permission_features") is True
    assert runtime_overrides.get("EXPORT_ALIGNED_TRAINING_CACHE") is False
    assert runtime_overrides.get("ENABLE_SKEPTIC_AUDITS") is False
    assert runtime_overrides.get("ENABLE_RESEARCH_VALIDITY_BUNDLE") is False
    assert runtime_overrides.get("ENABLE_VERBOSE_RUN_ARTIFACTS") is False
    assert runtime_overrides.get("ENABLE_DETAILED_PER_CLASS_REPORTS") is False


def test_dev_fast_profile_is_broad_but_taxonomy_clean() -> None:
    """Fast dev profile should use a broader, cleaner governed Android slice than smoke."""
    profile = profile_manager.load_profile("dev_fast")
    gates = profile.get("cohort_gates", {})
    feature_flags = profile.get("feature_flags", {})
    runtime_overrides = profile.get("runtime_overrides", {})

    assert gates.get("limit") == 1600
    assert gates.get("family_cap") == 80
    assert gates.get("family_cap_seed") == 1337
    assert gates.get("type_cap") == 220
    assert gates.get("type_cap_seed") == 1337
    assert gates.get("type_cap_by_slug") == {
        "banker": 140,
        "rat": 90,
        "spyware": 90,
        "adware": 70,
        "dropper": 70,
    }
    assert gates.get("min_family_label_confidence_score") == 80
    assert gates.get("exclude_weak_label_kinds") is True
    assert gates.get("exclude_family_label_conflicts") is True
    assert feature_flags.get("enable_sample_metadata_features") is True
    assert feature_flags.get("enable_permission_features") is True
    assert runtime_overrides.get("EXPORT_ALIGNED_TRAINING_CACHE") is False
    assert runtime_overrides.get("ENABLE_SKEPTIC_AUDITS") is False
    assert runtime_overrides.get("ENABLE_RESEARCH_VALIDITY_BUNDLE") is False
    assert runtime_overrides.get("ENABLE_VERBOSE_RUN_ARTIFACTS") is False
    assert runtime_overrides.get("ENABLE_DETAILED_PER_CLASS_REPORTS") is False


def test_profile_sorting_prefers_locked_and_core_profiles() -> None:
    """Sort key should rank locked baselines before misc entries."""
    ordered = sorted(
        [
            "android_malware_all_current",
            "android_malware_major_families",
            "android_malware_expanded_families",
            "android_malware_type_taxonomy",
            "spyware",
            "malicious_temporal_stability_locked",
            "banker_locked",
            "malicious_temporal_stability_expanded",
            "malicious_temporal_family300",
            "malicious_temporal_stability_long_tail",
            "dev_smoke",
            "dev_fast",
            "malicious_temporal_stability",
            "banker",
        ],
        key=profile_selection.profile_sort_key,
    )
    assert ordered[0] == "android_malware_all_current"
    assert ordered[1] == "android_malware_major_families"
    assert ordered[2] == "android_malware_expanded_families"
    assert ordered[3] == "android_malware_type_taxonomy"
    assert ordered[4] == "malicious_temporal_stability_locked"
    assert ordered[5] == "banker_locked"
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
                "profile_status:",
                "  status_label: Final canonical",
                "type_slug_filter: banker",
                "cohort_gates:",
                "  min_malicious_detections: 10",
                "  family_cap: 300",
                "  type_cap: 120",
                "  exclude_weak_label_kinds: true",
                "  exclude_family_label_conflicts: true",
                "  exclude_unknown_type_slug: true",
                "model_list:",
                "  - logistic_regression",
            ]
        ),
        encoding="utf-8",
    )
    summary = profile_selection.summarize_profile(profile_path)
    assert "Final canonical:" in summary
    assert "type=banker" in summary
    assert "min_detect=10" in summary
    assert "family_cap=300" in summary
    assert "type_cap=120" in summary
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
                "  expected_sample_count: 1187",
                "  expected_family_count: 35",
                "  expected_type_count: 3",
                "  sample_id_lock_file: artifacts/baselines/20260526T021235Z__8b6966/malicious_temporal_stability_locked_sample_ids.csv",
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
    locked_summary = profile_selection.summarize_profile(locked)
    legacy_summary = profile_selection.summarize_profile(legacy)
    assert "lock=membership-locked" in locked_summary
    assert "publication=unlocked" in legacy_summary


def test_quick_profile_label_prefers_operator_facing_descriptions() -> None:
    """Quick profile menu should lead with human labels instead of raw profile ids."""
    assert profile_manager.profile_selection.quick_profile_label(
        "android_malware_all_current"
    ) == "Research: all current Android malware"
    assert profile_manager.profile_selection.quick_profile_label(
        "android_malware_major_families"
    ) == "Research: major-family classification"
    assert profile_manager.profile_selection.quick_profile_label(
        "android_malware_expanded_families"
    ) == "Research: expanded family classification"
    assert profile_manager.profile_selection.quick_profile_label(
        "android_malware_type_taxonomy"
    ) == "Research: type-level taxonomy"
    assert profile_manager.profile_selection.quick_profile_label(
        "malicious_temporal_stability_locked"
    ) == "Reproducibility: locked 2026 paper benchmark"
    assert profile_manager.profile_selection.quick_profile_label(
        "malicious_temporal_consensus10"
    ) == "Sensitivity: consensus threshold"
    assert profile_manager.profile_selection.quick_profile_label(
        "dev_smoke"
    ) == "Smoke: sanity check"
    assert profile_manager.profile_selection.quick_profile_label(
        "definitely_unknown_profile"
    ) == "definitely_unknown_profile"


def test_removed_legacy_profile_ids_fail_to_load() -> None:
    """Removed legacy/deprecated profile ids should fail instead of aliasing silently."""
    for profile_id in (
        "paper2_primary",
        "paper2_primary_locked",
        "paper1_banker_locked",
        "paper2_sensitivity_consensus10",
        "paper2_sensitivity_family300",
        "research_all_malicious",
        "all_malicious",
    ):
        with pytest.raises(FileNotFoundError):
            profile_manager.load_profile(profile_id)


def test_infer_cohort_readiness_signal_maps_banker_profiles() -> None:
    signal = profile_manager.infer_cohort_readiness_signal("banker_locked")
    assert signal["bucket"] == "android_banker_with_permission_obs"
    assert "Best matching readiness bucket" in str(signal["summary"])


def test_infer_cohort_readiness_signal_maps_temporal_and_current_all_malicious_profiles() -> None:
    temporal = profile_manager.infer_cohort_readiness_signal("malicious_temporal_stability_locked")
    current = profile_manager.infer_cohort_readiness_signal("malicious_temporal_stability")
    expanded = profile_manager.infer_cohort_readiness_signal("malicious_temporal_stability_expanded")
    long_tail = profile_manager.infer_cohort_readiness_signal("malicious_temporal_stability_long_tail")
    assert temporal["bucket"] == "android_high_or_strong_vt_with_permission_obs"
    assert "high/strong VT confidence" in str(temporal["detail"])
    assert "does not verify or enforce PI observation materialization" in str(temporal["detail"])
    assert "paper-locked" in str(temporal["detail"])
    assert current["bucket"] == "android_high_or_strong_vt_with_permission_obs"
    assert "high/strong VT confidence" in str(current["detail"])
    assert expanded["bucket"] == "android_high_or_strong_vt_with_permission_obs"
    assert long_tail["bucket"] == "android_high_or_strong_vt_with_permission_obs"


def test_infer_cohort_readiness_signal_returns_unmapped_advisory_for_unknown_profile() -> None:
    signal = profile_manager.infer_cohort_readiness_signal("definitely_unknown_profile")
    assert signal["bucket"] is None
    assert str(signal["summary"]) == "No readiness bucket mapped for this profile; review cohort filters manually."


def test_infer_cohort_readiness_signal_maps_broad_android_profiles_to_android_platform() -> None:
    mixed = profile_manager.infer_cohort_readiness_signal("mixed")
    benign_heavy = profile_manager.infer_cohort_readiness_signal("benign_heavy")
    assert mixed["bucket"] == "android_platform"
    assert benign_heavy["bucket"] == "android_platform"


def test_infer_cohort_readiness_signal_prefers_declared_bucket_contract() -> None:
    signal = profile_manager.infer_cohort_readiness_signal(
        {
            "profile_id": "custom_profile",
            "cohort_readiness_bucket": "android_platform",
            "type_slug_filter": "banker",
            "evidence_mode": True,
            "cohort_gates": {"min_samples_per_family": 3},
            "dataset_filters": {"mode": "malicious_only"},
        }
    )

    assert signal["bucket"] == "android_platform"
    assert "Declared readiness bucket in profile contract" in str(signal["detail"])


def test_select_profile_interactive_quick_uses_six_intent_menu(monkeypatch) -> None:
    """Quick path should expose only the six benchmark/dev intents."""
    captured: dict[str, list[str]] = {}

    def _fake_display_menu(options, *_, **kwargs):
        title = str(kwargs.get("title", ""))
        captured[title] = list(options)
        return 0

    monkeypatch.setattr(profile_manager.profile_selection.mu, "display_menu", _fake_display_menu)

    selected = profile_manager.select_profile_interactive_quick()

    assert selected is None
    assert captured["Execution profile"] == [
        "Current Android malware — all samples",
        "Major-family Android malware classification",
        "Expanded Android malware — major + minor families",
        "Type-level / coarse taxonomy classification",
        "Robustness and perturbation suite",
        "Development / smoke checks",
    ]
    assert "More profiles (full catalog)" not in captured["Execution profile"]


def test_select_profile_interactive_quick_resolves_robustness_submenu(monkeypatch) -> None:
    """Robustness intent should expose exactly two sensitivity profiles."""
    choices = iter([5, 2])
    seen: dict[str, list[str]] = {}

    def _fake_display_menu(options, *_, **kwargs):
        seen[str(kwargs.get("title", ""))] = list(options)
        return next(choices)

    monkeypatch.setattr(profile_manager.profile_selection.mu, "display_menu", _fake_display_menu)

    selected = profile_manager.select_profile_interactive_quick()

    assert selected == "malicious_temporal_family300"
    assert seen["Execution profile"] == [
        "Current Android malware — all samples",
        "Major-family Android malware classification",
        "Expanded Android malware — major + minor families",
        "Type-level / coarse taxonomy classification",
        "Robustness and perturbation suite",
        "Development / smoke checks",
    ]
    assert seen["Robustness / perturbations"] == [
        "Sensitivity: consensus threshold",
        "Sensitivity: family dominance cap",
    ]


def test_type_taxonomy_profile_declares_type_slug_training_target() -> None:
    profile = profile_manager.load_profile("android_malware_type_taxonomy")
    assert profile["training_label_field"] == "type_slug"


def test_select_profile_interactive_quick_resolves_development_submenu(monkeypatch) -> None:
    """Development intent should expose exactly fast iteration and smoke."""
    choices = iter([6, 1])
    seen: dict[str, list[str]] = {}

    def _fake_display_menu(options, *_, **kwargs):
        seen[str(kwargs.get("title", ""))] = list(options)
        return next(choices)

    monkeypatch.setattr(profile_manager.profile_selection.mu, "display_menu", _fake_display_menu)

    selected = profile_manager.select_profile_interactive_quick()

    assert selected == "dev_fast"
    assert seen["Development / smoke checks"] == [
        "Development: fast iteration",
        "Smoke: sanity check",
    ]


def test_inventory_cohort_readiness_mappings_covers_all_profile_files() -> None:
    inventory = profile_manager.inventory_cohort_readiness_mappings()
    profile_paths = sorted(p for p in profile_manager.PROFILES_DIR.glob("*.yaml"))
    assert len(inventory) == len(profile_paths)
    assert all(row["status"] in {"mapped", "ambiguous"} for row in inventory)
    assert all("summary" in row for row in inventory)
    assert all("detail" in row for row in inventory)
    assert all("lifecycle" in row for row in inventory)
    assert all("operator_surface" in row for row in inventory)
    assert all("support_tier" in row for row in inventory)


def test_inventory_cohort_readiness_mappings_current_catalog_has_no_ambiguous_entries() -> None:
    inventory = profile_manager.inventory_cohort_readiness_mappings()
    ambiguous = [row["profile_id"] for row in inventory if row["status"] != "mapped"]
    assert ambiguous == []


def test_profile_status_metadata_classifies_supported_profiles() -> None:
    final_profile = profile_manager.load_profile("malicious_temporal_stability_locked")
    dev_profile = profile_manager.load_profile("dev_fast")

    assert final_profile["profile_status"]["lifecycle"] == "final_canonical"
    assert final_profile["profile_status"]["operator_surface"] == "supported"

    assert dev_profile["profile_status"]["lifecycle"] == "dev_only"
    assert dev_profile["profile_status"]["operator_surface"] == "supported_dev"


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
