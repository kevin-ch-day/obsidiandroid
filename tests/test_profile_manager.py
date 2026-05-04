"""Tests for profile loading contract."""

from pathlib import Path

import obsidiandroid.cli.profile_manager as profile_manager


def test_profile_list_contains_default_profiles() -> None:
    """Profiles directory should contain baseline profiles."""
    names = [p.stem for p in profile_manager.list_profiles()]
    assert "banker" in names
    assert "mixed" in names
    assert "benign_heavy" in names
    assert "dev_smoke" in names


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


def test_paper2_evidence_profiles_exclude_dominant_families() -> None:
    """Paper #2 evidence profiles should exclude dominant families for balanced cross-type analysis."""
    expected = {"devixor", "gigabud"}
    for profile_id in (
        "paper2_primary",
        "paper2_sensitivity_consensus10",
        "paper2_sensitivity_family300",
    ):
        profile = profile_manager.load_profile(profile_id)
        excluded = {
            str(family).strip().lower()
            for family in profile.get("cohort_gates", {}).get("exclude_families", [])
            if str(family).strip()
        }
        assert expected.issubset(excluded)


def test_profile_sorting_prefers_paper2_and_core_profiles() -> None:
    """Sort key should rank paper2 evidence/core profiles before misc entries."""
    ordered = sorted(
        [
            "spyware",
            "paper2_sensitivity_family300",
            "dev_smoke",
            "dev_fast",
            "paper2_primary",
            "banker",
        ],
        key=profile_manager._profile_sort_key,  # pylint: disable=protected-access
    )
    assert ordered[0] == "paper2_primary"
    assert ordered[1] == "paper2_sensitivity_family300"
    assert ordered[2] == "banker"
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
