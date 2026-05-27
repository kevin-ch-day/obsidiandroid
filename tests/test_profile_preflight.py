"""Tests for interactive profile preflight flow."""

from __future__ import annotations

import pandas as pd

import obsidiandroid.database.db_sample_metadata_fetchers as sample_metadata_fetchers

from obsidiandroid.cli.menu import profile_preflight


def test_resolve_and_validate_profile_reprompts_until_valid(monkeypatch) -> None:
    """Invalid profile should re-prompt until a valid profile is selected."""
    choices = iter(["mixed", "banker"])

    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: next(choices),
    )

    def _validate(profile_id: str) -> tuple[bool, str]:
        if profile_id == "mixed":
            return False, "[PROFILE] mixed failed preflight"
        return True, ""

    monkeypatch.setattr(profile_preflight, "validate_profile_runnable", _validate)
    selected = profile_preflight.resolve_and_validate_profile()
    assert selected == "banker"


def test_resolve_and_validate_profile_cancel(monkeypatch) -> None:
    """Cancel on profile selection should return None."""
    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: None,
    )
    assert profile_preflight.resolve_and_validate_profile() is None


def test_validate_profile_runnable_uses_sql_gate_stats_and_lightweight_probe_for_malicious_only(monkeypatch) -> None:
    """Malicious-only preflight should use the real SQL gate surface before probing."""
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "malicious_temporal_stability",
            "type_slug_filter": None,
            "evidence_mode": True,
            "cohort_gates": {
                "exclude_unknown_type_slug": True,
                "exclude_families": ["Devixor", " Gigabud "],
                "family_cap": 60,
                "family_cap_seed": 1337,
                "type_cap": 300,
                "type_cap_seed": 1337,
                "type_cap_by_slug": {"banker": 90, "rat": 55},
                "exclude_weak_label_kinds": True,
                "exclude_family_label_conflicts": True,
                "time_window_start_utc": "2020-01-01T00:00:00Z",
                "time_window_end_utc": "2026-01-01T00:00:00Z",
            },
            "dataset_filters": {"mode": "none"},
        },
    )
    stats_calls: list[dict[str, object]] = []
    fetch_calls: list[dict[str, object]] = []

    def _fake_stats(**kwargs):
        stats_calls.append(kwargs)
        return {"governed_cohort_count": 3}

    def _fake_fetch(**kwargs):
        fetch_calls.append(kwargs)
        return pd.DataFrame([{"sample_id": 1}])

    monkeypatch.setattr(
        sample_metadata_fetchers,
        "get_type_cohort_gate_stats",
        _fake_stats,
    )
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "fetch_samples_by_type",
        _fake_fetch,
    )

    ok, reason = profile_preflight.validate_profile_runnable("malicious_temporal_stability")
    assert ok is True
    assert reason == ""
    assert len(stats_calls) == 1
    assert stats_calls[0]["exclude_unknown_type_slug"] is True
    assert stats_calls[0]["exclude_family_canonical"] == ("devixor", "gigabud")
    assert stats_calls[0]["effective_time_start_utc"] == "2020-01-01T00:00:00Z"
    assert stats_calls[0]["effective_time_end_utc"] == "2026-01-01T00:00:00Z"
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["limit"] == 1
    assert fetch_calls[0]["family_cap"] == 60
    assert fetch_calls[0]["family_cap_seed"] == 1337
    assert fetch_calls[0]["type_cap"] == 300
    assert fetch_calls[0]["type_cap_seed"] == 1337
    assert fetch_calls[0]["type_cap_by_slug"] == {"banker": 90, "rat": 55}
    assert fetch_calls[0]["exclude_weak_label_kinds"] is True
    assert fetch_calls[0]["exclude_family_label_conflicts"] is True
    assert fetch_calls[0]["as_dataframe"] is True
    assert fetch_calls[0]["exclude_unknown_type_slug"] is True
    assert fetch_calls[0]["exclude_family_canonical"] == ("devixor", "gigabud")


def test_validate_profile_runnable_fails_fast_when_sql_governed_count_is_zero(monkeypatch) -> None:
    """Preflight should fail before materialization when the governed SQL cohort is empty."""
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "malicious_temporal_stability",
            "type_slug_filter": None,
            "evidence_mode": True,
            "cohort_gates": {},
            "dataset_filters": {"mode": "malicious_only"},
        },
    )
    fetch_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        sample_metadata_fetchers,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"governed_cohort_count": 0},
    )
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "fetch_samples_by_type",
        lambda **kwargs: fetch_calls.append(kwargs) or pd.DataFrame([{"sample_id": 1}]),
    )

    ok, reason = profile_preflight.validate_profile_runnable("malicious_temporal_stability")
    assert ok is False
    assert "selected an empty cohort" in reason
    assert fetch_calls == []


def test_resolve_and_validate_profile_prints_advisory_readiness_mapping(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: "banker",
    )
    monkeypatch.setattr(profile_preflight, "validate_profile_runnable", lambda _profile_id: (True, ""))
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "status": "mapped",
            "bucket": "android_banker_with_permission_obs",
            "summary": "Best matching readiness bucket: android_banker_with_permission_obs",
            "detail": "Readiness mapping is advisory only; it does not enforce sample selection.",
            "ambiguity_reason": None,
        },
    )
    monkeypatch.setattr(
        profile_preflight,
        "get_cohort_readiness_snapshot",
        lambda: {
            "buckets": {
                "android_banker_with_permission_obs": {"sample_count": 790, "family_count": 12}
            }
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [{"profile_id": "banker", "status": "mapped"}],
    )
    messages: list[str] = []
    notes: list[str] = []
    monkeypatch.setattr(profile_preflight.du, "print_info", lambda msg: messages.append(str(msg)))
    monkeypatch.setattr(profile_preflight.du, "print_note", lambda msg: notes.append(str(msg)))

    selected = profile_preflight.resolve_and_validate_profile()

    assert selected == "banker"
    assert any("Best matching readiness bucket: android_banker_with_permission_obs" in msg for msg in messages)
    assert any("does not enforce sample selection" in msg for msg in notes)
    assert any("Observed readiness for `android_banker_with_permission_obs`: samples=790, families=12" in msg for msg in notes)


def test_resolve_and_validate_profile_reports_ambiguous_inventory_advisory(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: "banker",
    )
    monkeypatch.setattr(profile_preflight, "validate_profile_runnable", lambda _profile_id: (True, ""))
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "status": "mapped",
            "bucket": "android_banker_with_permission_obs",
            "summary": "Best matching readiness bucket: android_banker_with_permission_obs",
            "detail": "Readiness mapping is advisory only; it does not enforce sample selection.",
            "ambiguity_reason": None,
        },
    )
    monkeypatch.setattr(
        profile_preflight,
        "get_cohort_readiness_snapshot",
        lambda: {
            "buckets": {
                "android_banker_with_permission_obs": {"sample_count": 790, "family_count": 12}
            }
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [
            {"profile_id": "banker", "status": "mapped"},
            {"profile_id": "future_profile", "status": "ambiguous"},
        ],
    )
    notes: list[str] = []
    monkeypatch.setattr(profile_preflight.du, "print_info", lambda _msg: None)
    monkeypatch.setattr(profile_preflight.du, "print_note", lambda msg: notes.append(str(msg)))

    selected = profile_preflight.resolve_and_validate_profile()

    assert selected == "banker"
    assert any("1 mapped, 1 ambiguous" in msg for msg in notes)


def test_resolve_and_validate_profile_surfaces_live_gap_notes(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: "malicious_temporal_stability_locked",
    )
    monkeypatch.setattr(profile_preflight, "validate_profile_runnable", lambda _profile_id: (True, ""))
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "status": "mapped",
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": "Readiness mapping is advisory only; it does not enforce sample selection.",
            "ambiguity_reason": None,
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {"paper_locked": True},
    )
    monkeypatch.setattr(
        profile_preflight,
        "get_cohort_readiness_snapshot",
        lambda: {
            "permission_obs_available": False,
            "warnings": ["Permission Intel unavailable: android_permission_obs_sample not reachable."],
            "buckets": {
                "android_high_or_strong_vt_with_permission_obs": {
                    "sample_count": None,
                    "family_count": None,
                }
            },
            "taxonomy_signals": {
                "repair_candidate_count": 7,
                "known_unresolved_family_count": 3,
            },
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [{"profile_id": "malicious_temporal_stability_locked", "status": "mapped"}],
    )
    notes: list[str] = []
    monkeypatch.setattr(profile_preflight.du, "print_info", lambda _msg: None)
    monkeypatch.setattr(profile_preflight.du, "print_note", lambda msg: notes.append(str(msg)))

    selected = profile_preflight.resolve_and_validate_profile()

    assert selected == "malicious_temporal_stability_locked"
    assert any("does not verify a matching PI-observed cohort" in msg for msg in notes)
    assert any("repair candidates=7, known unresolved families=3" in msg for msg in notes)
    assert any("may not change cohort membership until the lock is refreshed" in msg for msg in notes)
