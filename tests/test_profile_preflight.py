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


def test_validate_profile_runnable_uses_lightweight_probe_for_malicious_only(monkeypatch) -> None:
    """Malicious-only preflight should use fast probe query with limit=1."""
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "all_malicious",
            "type_slug_filter": None,
            "cohort_gates": {},
            "dataset_filters": {"mode": "none"},
        },
    )
    calls: list[dict[str, object]] = []

    def _fake_fetch(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([{"sample_id": 1}])

    monkeypatch.setattr(
        sample_metadata_fetchers,
        "fetch_samples_by_type",
        _fake_fetch,
    )

    ok, reason = profile_preflight.validate_profile_runnable("all_malicious")
    assert ok is True
    assert reason == ""
    assert len(calls) == 1
    assert calls[0]["limit"] == 1
    assert calls[0]["as_dataframe"] is True


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
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda: [{"profile_id": "banker", "status": "mapped"}],
    )
    messages: list[str] = []
    notes: list[str] = []
    monkeypatch.setattr(profile_preflight.du, "print_info", lambda msg: messages.append(str(msg)))
    monkeypatch.setattr(profile_preflight.du, "print_note", lambda msg: notes.append(str(msg)))

    selected = profile_preflight.resolve_and_validate_profile()

    assert selected == "banker"
    assert any("Best matching readiness bucket: android_banker_with_permission_obs" in msg for msg in messages)
    assert any("does not enforce sample selection" in msg for msg in notes)


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
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda: [
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
