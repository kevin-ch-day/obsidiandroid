"""Tests for interactive profile preflight flow."""

from __future__ import annotations

import json
from pathlib import Path

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
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {},
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {},
    )
    monkeypatch.setattr(
        profile_preflight,
        "get_cohort_readiness_snapshot",
        lambda: {},
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [],
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


def test_validate_profile_runnable_uses_resolved_default_time_contract(monkeypatch) -> None:
    """Preflight and samples stage must share the implicit global time window."""
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "all_current",
            "type_slug_filter": None,
            "cohort_gates": {},
            "dataset_filters": {"mode": "none"},
        },
    )
    monkeypatch.setattr(
        profile_preflight,
        "resolve_dataset_time_contract",
        lambda **_kwargs: {
            "start_utc": "2020-01-01T00:00:00Z",
            "end_utc": "2026-07-16T00:00:00Z",
            "require_effective_first_seen": True,
        },
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "get_type_cohort_gate_stats",
        lambda **kwargs: calls.append(kwargs) or {"governed_cohort_count": 1},
    )
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "fetch_samples_by_type",
        lambda **_kwargs: pd.DataFrame([{"sample_id": 1}]),
    )

    ok, reason = profile_preflight.validate_profile_runnable("all_current")

    assert ok is True
    assert reason == ""
    assert calls[0]["effective_time_start_utc"] == "2020-01-01T00:00:00Z"
    assert calls[0]["effective_time_end_utc"] == "2026-07-16T00:00:00Z"
    assert calls[0]["require_effective_first_seen"] is True


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


def test_validate_profile_runnable_paper_locked_uses_lock_manifest_without_live_sql(
    monkeypatch,
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    member_path = baseline_dir / "members.csv"
    member_path.write_text("sample_id\n1\n2\n3\n", encoding="utf-8")
    manifest_path = baseline_dir / "cohort_lock_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "lock_version": "v1",
                "profile_id": "malicious_temporal_stability_locked",
                "contract_id": "locked_contract",
                "created_at_utc": "2026-05-31T00:00:00Z",
                "member_list_path": "members.csv",
                "sample_count": 3,
                "family_count": 2,
                "type_count": 2,
                "cohort_hash": "x" * 64,
                "taxonomy_hash": "y" * 64,
                "time_window": {"start_utc": "2020-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    from obsidiandroid.governance.cohort_lock_manifest import compute_cohort_hash_from_member_list

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["cohort_hash"] = compute_cohort_hash_from_member_list(pd.DataFrame({"sample_id": [1, 2, 3]}))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "malicious_temporal_stability_locked",
            "paper_locked": True,
            "paper_lock": {
                "cohort_lock_manifest_file": str(manifest_path),
            },
            "cohort_gates": {},
            "dataset_filters": {"mode": "malicious_only"},
        },
    )
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("live SQL stats should be skipped")),
    )
    monkeypatch.setattr(
        sample_metadata_fetchers,
        "fetch_samples_by_type",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("live SQL fetch should be skipped")),
    )

    ok, reason = profile_preflight.validate_profile_runnable("malicious_temporal_stability_locked")
    assert ok is True
    assert reason == ""


def test_validate_profile_runnable_paper_locked_fails_when_lock_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {
            "profile_id": "malicious_temporal_stability_locked",
            "paper_locked": True,
            "paper_lock": {},
            "cohort_gates": {},
            "dataset_filters": {"mode": "malicious_only"},
        },
    )

    ok, reason = profile_preflight.validate_profile_runnable("malicious_temporal_stability_locked")
    assert ok is False
    assert "missing an immutable cohort lock manifest/member list" in reason


def test_compact_live_gap_note_limits_operator_line_density() -> None:
    headline, detail_lines = profile_preflight._compact_live_gap_lines(
        [
            "Live authority/taxonomy backlog: repair candidates=2, known unresolved families=0, policy-held tokens=67",
            "Taxonomy curation discipline: high-priority conflicts=1/2; dominant action=review_db_type_mapping (2); dominant issue=type_mismatch (2)",
            "Permission Intel observations include 1 sample_id(s) outside the current Android catalog cohort",
        ]
    )
    assert headline.startswith("Live authority/taxonomy backlog:")
    assert len(detail_lines) == 2
    assert detail_lines[0].startswith("Permission Intel observations include")
    assert "Taxonomy curation discipline" not in headline


def test_resolve_and_validate_profile_prints_advisory_readiness_mapping(monkeypatch, capsys) -> None:
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
    selected = profile_preflight.resolve_and_validate_profile()
    out = capsys.readouterr().out

    assert selected == "banker"
    assert "[PROFILE] Best matching readiness bucket: android_banker_with_permission_obs" in out
    assert "does not enforce sample selection" in out
    assert "[PROFILE] Observed readiness for `android_banker_with_permission_obs`:" in out
    assert "samples=790" in out
    assert "families=12" in out


def test_resolve_and_validate_profile_reports_ambiguous_inventory_advisory(monkeypatch, capsys) -> None:
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
    selected = profile_preflight.resolve_and_validate_profile()
    out = capsys.readouterr().out

    assert selected == "banker"
    assert "1 mapped, 1 ambiguous" in out


def test_resolve_and_validate_profile_surfaces_live_gap_notes(monkeypatch, capsys) -> None:
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
                "policy_held_family_count": 11,
                "family_type_conflict_count": 5,
                "high_priority_conflict_count": 4,
                "family_type_conflict_action_counts": {
                    "review_db_type_mapping": 2,
                    "replace_unknown_db_type": 2,
                    "add_db_family_mapping": 1,
                },
                "family_type_conflict_issue_counts": {
                    "type_mismatch": 2,
                    "type_unknown": 2,
                    "db_family_missing": 1,
                },
            },
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [{"profile_id": "malicious_temporal_stability_locked", "status": "mapped"}],
    )
    selected = profile_preflight.resolve_and_validate_profile()
    out = capsys.readouterr().out

    assert selected == "malicious_temporal_stability_locked"
    assert "does not enforce sample selection" in out
    assert "current-corpus profiles" in out
    assert "repair candidates=7, known unresolved families=3, policy-held tokens=11" in out
    assert "high-priority conflicts=4/5; dominant action=review_db_type_mapping (2); dominant issue=type_unknown (2)" in out
    assert "may not change cohort membership until the lock is refreshed" in out
    assert "Observed readiness for `android_high_or_strong_vt_with_permission_obs` is unavailable" not in out


def test_resolve_and_validate_profile_uses_compact_profile_block(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        profile_preflight,
        "resolve_profile_for_run",
        lambda prefer_quick=False, **kwargs: "android_malware_major_families",
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "status": "mapped",
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": (
                "Declared readiness bucket in profile contract: android_high_or_strong_vt_with_permission_obs. "
                "Advisory only; this does not enforce sample selection. "
                "Permission-observation wording is advisory here; bucket mapping does not verify or enforce PI observation materialization for the selected run."
            ),
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "load_profile",
        lambda _profile_id: {"paper_locked": False},
    )
    monkeypatch.setattr(
        profile_preflight,
        "get_cohort_readiness_snapshot",
        lambda: {
            "buckets": {
                "android_high_or_strong_vt_with_permission_obs": {"sample_count": 3285, "family_count": 220}
            },
            "taxonomy_signals": {
                "repair_candidate_count": 0,
                "known_unresolved_family_count": 0,
                "policy_held_family_count": 67,
            },
            "warnings": [
                "Permission Intel observations include 1 sample_id(s) outside the current Android catalog cohort."
            ],
        },
    )
    monkeypatch.setattr(
        profile_preflight.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [{"profile_id": "android_malware_major_families", "status": "mapped"}],
    )
    monkeypatch.setattr(profile_preflight, "validate_profile_runnable", lambda _profile_id: (True, ""))

    selected = profile_preflight.resolve_and_validate_profile()
    out = capsys.readouterr().out

    assert selected == "android_malware_major_families"
    assert "[INFO]" not in out
    assert "[NOTE]" not in out
    assert "[PROFILE] Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs" in out
    assert "[PROFILE] Declared readiness bucket in profile contract: android_high_or_strong_vt_with_permission_obs." in out
    assert "Advisory only; sample selection is not enforced." in out
    assert "[PROFILE] Observed readiness for `android_high_or_strong_vt_with_permission_obs`:" in out
    assert "samples=3285" in out
    assert "families=220" in out
    assert "[PROFILE] Live authority/taxonomy backlog: repair candidates=0, known unresolved families=0, policy-held tokens=67." in out
    assert "Permission Intel observations include 1 sample_id(s) outside the current Android catalog cohort." in out
    assert "[PROFILE] Preflight: verifying cohort against the database (quick check)..." in out


def test_compact_profile_detail_hardens_locked_cohort_wording() -> None:
    detail = (
        "Declared readiness bucket in profile contract: android_high_or_strong_vt_with_permission_obs. "
        "Android malicious evidence-style profile intent is best compared against the Android cohort with permission observations and high/strong VT confidence. "
        "Advisory only; this does not enforce sample selection. "
        "Permission-observation wording is advisory here; bucket mapping does not verify or enforce PI observation materialization for the selected run. "
        "This profile is paper-locked; snapshot membership can prevent new DB curation or authority expansions from changing the cohort until the lock is refreshed."
    )

    compact = profile_preflight._compact_profile_detail(detail, paper_locked=True)  # pylint: disable=protected-access

    assert "Advisory only; sample selection is not enforced." in compact
    assert "Permission-observation wording is not verified/enforced for this run." in compact
    assert "Locked benchmark cohort; new DB curation will not change membership until the lock is refreshed." in compact
