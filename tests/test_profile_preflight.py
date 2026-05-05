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
