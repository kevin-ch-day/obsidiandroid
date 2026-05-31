"""Tests for startup menu maintenance helpers."""

from __future__ import annotations

from pathlib import Path
import json

from config import app_config

import obsidiandroid.cli.startup_menu as startup_menu
from obsidiandroid.cli.ui import menu


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload))


def _make_run_dirs(out_root: Path, run_id: str) -> tuple[Path, Path]:
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return run_root, diagnostics_dir


def _capture_table_rows(monkeypatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _fake_print_table(rows, *_, **__):
        captured["rows"] = rows

    monkeypatch.setattr(startup_menu.du, "print_table", _fake_print_table)
    return captured


def _capture_stat_rows(monkeypatch) -> list[tuple[str, object]]:
    captured: list[tuple[str, object]] = []
    monkeypatch.setattr(
        startup_menu.du,
        "print_stat",
        lambda label, value, *args, **kwargs: captured.append((str(label), value)),
    )
    return captured


def _write_latest_run_manifest(out_root: Path, payload: object) -> None:
    _write_json(out_root / "diagnostics" / "run_manifest.latest.json", payload)


def test_main_menu_clear_screen_option(monkeypatch) -> None:
    """Main menu clear option should call clear_screen and continue loop."""
    choices = iter([8, 0])
    clear_calls = {"count": 0}

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu.du, "clear_console", lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1))

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert clear_calls["count"] == 1


def test_display_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert menu.display_menu(["First", "Second"], title="T", default_choice=2) == 2


def test_display_menu_blank_without_default_reprompts(monkeypatch) -> None:
    """Main menu: empty line shows hint then accepts numeric choice."""
    replies = iter(["", "2"])

    def _fake_input(_prompt: str = "") -> str:
        return next(replies)

    monkeypatch.setattr("builtins.input", _fake_input)
    assert menu.display_menu(["First", "Second"], title="T") == 2


def test_display_menu_blank_returns_back_when_exit_label_back(monkeypatch) -> None:
    """Submenus with Back: blank Enter returns 0 without extra prompts."""
    monkeypatch.setattr("builtins.input", lambda _p="": "")
    assert menu.display_menu(["Only"], title="T", exit_label="Back") == 0


def test_display_rich_menu_blank_input_selects_default(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    opts = {"A": "one", "B": "two"}
    assert menu.display_rich_menu(opts, title="T", default_choice=2) == 2


def test_main_menu_uses_concise_title_and_primary_workflow_order(monkeypatch) -> None:
    """Top-level menu should stay concise and ordered around the main workflow."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert captured["title"] == "Main menu"
    assert captured["labels"] == [
        "Run Analysis",
        "Review Latest Run",
        "Run Status and History",
        "Research Reports",
        "Reproducibility & research validity",
        "Data Diagnostics",
        "Tools and Maintenance",
        "Clear Screen",
    ]


def test_run_analysis_menu_uses_operator_facing_actions(monkeypatch) -> None:
    """Run analysis submenu should list pipeline modes in operator order."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    result = startup_menu._launch_pipeline_actions_menu()  # pylint: disable=protected-access

    assert result == 0
    assert captured["title"] == "Pipeline run mode"
    assert captured["labels"] == [
        "Full pipeline",
        "Fast development",
        "Smoke test",
        "Single model only",
        "Stop after a stage",
        "Vendor extraction only",
        "Retrain from cached alignment",
    ]


def test_single_model_mode_uses_quick_intent_profile_selector(monkeypatch) -> None:
    """Single-model runs should use the same intent-first quick selector as full pipeline."""
    choices = iter([4, 1])
    captured: list[bool] = []

    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(
        startup_menu,
        "resolve_and_validate_profile",
        lambda **kwargs: captured.append(bool(kwargs.get("prefer_quick"))) or "banker",
    )
    monkeypatch.setattr(startup_menu, "_build_model_menu", lambda: {"Logistic Regression": "logistic_regression"})
    monkeypatch.setattr(startup_menu, "_run_single_model", lambda model_key, profile_id: 0)

    result = startup_menu._launch_pipeline_actions_menu()  # pylint: disable=protected-access

    assert result == 0
    assert captured == [True]


def test_stop_after_stage_uses_quick_intent_profile_selector(monkeypatch) -> None:
    """Stage-stop runs should use the same intent-first quick selector as full pipeline."""
    choices = iter([5])
    captured: list[bool] = []

    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(
        startup_menu,
        "resolve_and_validate_profile",
        lambda **kwargs: captured.append(bool(kwargs.get("prefer_quick"))) or "banker",
    )
    monkeypatch.setattr(startup_menu, "_run_to_stage", lambda profile_id: 0)

    result = startup_menu._launch_pipeline_actions_menu()  # pylint: disable=protected-access

    assert result == 0
    assert captured == [True]


def test_vendor_only_uses_quick_intent_profile_selector(monkeypatch) -> None:
    """Vendor-only runs should use the same intent-first quick selector as full pipeline."""
    choices = iter([6])
    captured: list[bool] = []

    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(
        startup_menu,
        "resolve_and_validate_profile",
        lambda **kwargs: captured.append(bool(kwargs.get("prefer_quick"))) or "banker",
    )
    monkeypatch.setattr(startup_menu, "_run_vendor_only", lambda profile_id: 0)

    result = startup_menu._launch_pipeline_actions_menu()  # pylint: disable=protected-access

    assert result == 0
    assert captured == [True]


def test_tools_menu_lists_operational_actions_only(monkeypatch) -> None:
    """Tools & maintenance should list operational items (no parser/health duplicates)."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)
    monkeypatch.setattr(startup_menu.diagnostics_banners, "print_tools_maintenance_banner", lambda **_: None)

    startup_menu._launch_operations_menu()  # pylint: disable=protected-access

    assert captured["title"] == "Tools and maintenance"
    assert captured["labels"] == [
        "Smart Output Cleanup",
        "Show Disk Usage Summary",
        "Reuse Existing Results",
        "Cache / latest pointer (guidance)",
        "Repair / migration helpers (info)",
        "Developer utilities",
    ]


def test_data_diagnostics_menu_uses_compact_view_first_order(monkeypatch) -> None:
    """Data diagnostics should surface view actions before generate actions."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["subtitle"] = str(kwargs.get("subtitle", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(startup_menu.diagnostics_banners, "print_compact_diagnostics_overview", lambda **_: None)
    monkeypatch.setattr(startup_menu, "_read_latest_run_id", lambda: "r1")
    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_data_diagnostics_menu()  # pylint: disable=protected-access

    assert captured["title"] == "Data diagnostics"
    assert "View summaries first" in captured["subtitle"]
    assert captured["labels"] == [
        "Open run science index",
        "Pipeline profile tuning (resolved manifest)",
        "Profile readiness mapping inventory",
        "Refresh backlog triage exports",
        "Taxonomy & Support Tuning",
        "Taxonomy Consistency Review",
        "Family/Type Authority Coverage",
        "Android Missing-Resolution Triage",
        "VT False-Positive Review Triage",
        "Parser & Vendor Coverage",
        "Permission Intelligence Coverage",
        "Feature Matrix / Modality Coverage",
        "Cohort / Family Label Audit",
    ]


def test_profile_readiness_mapping_inventory_report_uses_inventory_helper(monkeypatch) -> None:
    tables: list[dict[str, object]] = []
    stats: list[tuple[str, object]] = []
    notes: list[str] = []
    subheaders: list[str] = []

    monkeypatch.setattr(
        startup_menu._diagnostics_menu.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda **_kwargs: [
            {
                "profile_id": "banker",
                "bucket": "android_banker_with_permission_obs",
                "status": "mapped",
                "summary": "Best matching readiness bucket: android_banker_with_permission_obs",
            },
            {
                "profile_id": "malicious_temporal_stability",
                "bucket": "android_high_or_strong_vt_with_permission_obs",
                "status": "mapped",
                "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            },
        ],
    )
    monkeypatch.setattr(
        startup_menu._diagnostics_menu,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {
                "android_banker_with_permission_obs": {"sample_count": 790, "family_count": 12},
                "android_high_or_strong_vt_with_permission_obs": {"sample_count": 3280, "family_count": 208},
            },
            "taxonomy_signals": {
                "banker_label_bucket_samples": 790,
                "banker_type_bucket_samples": 1295,
                "banker_type_minus_label_samples": 505,
                "missing_primary_label_samples": 2248,
                "unresolved_family_samples": 289,
                "unresolved_family_count": 25,
                "known_unresolved_family_samples": 17,
                "known_unresolved_family_count": 4,
                "policy_held_family_samples": 42,
                "policy_held_family_count": 11,
                "top_policy_held_families": [
                    {
                        "family": "badpack",
                        "sample_count": 8,
                        "high_strong_sample_count": 8,
                        "token_kind": "packer_evasion_token",
                    },
                    {
                        "family": "spybanker",
                        "sample_count": 4,
                        "high_strong_sample_count": 4,
                        "token_kind": "generic_family_token",
                    },
                ],
                "family_type_conflict_count": 3,
                "family_type_conflict_issue_counts": {
                    "type_mismatch": 1,
                    "db_family_missing": 1,
                    "label_sparse": 1,
                },
                "family_type_conflict_priority_counts": {
                    "high": 2,
                    "low": 1,
                },
                "family_type_conflict_action_counts": {
                    "review_db_type_mapping": 1,
                    "add_db_family_mapping": 1,
                    "monitor_label_backfill": 1,
                },
                "high_priority_conflict_count": 2,
                "repair_candidate_count": 2,
                "top_unresolved_families": [
                    {"family": "unknown", "sample_count": 289, "high_strong_sample_count": 279, "known_locally": False},
                    {"family": "blankbot", "sample_count": 9, "high_strong_sample_count": 9, "known_locally": True},
                ],
                "top_family_type_conflicts": [
                    {
                        "family": "devixor",
                        "priority": "high",
                        "suggested_action": "review_db_type_mapping",
                        "db_type_slug": "dropper",
                        "issue": "type_mismatch",
                        "operator_model_candidate": "rat",
                        "fraud_posture_candidate": "banking_targeted+odf_capable",
                        "permission_signal_summary": "sms+telephony+overlay",
                        "sample_count": 725,
                        "high_strong_sample_count": 725,
                        "dominant_label_semantic": "banker",
                        "dominant_label_samples": 725,
                        "unlabeled_samples": 0,
                        "known_locally": True,
                    },
                    {
                        "family": "blankbot",
                        "priority": "high",
                        "suggested_action": "add_db_family_mapping",
                        "db_type_slug": "<unmapped>",
                        "issue": "db_family_missing",
                        "operator_model_candidate": "unclear",
                        "fraud_posture_candidate": "unclear",
                        "permission_signal_summary": "overlay",
                        "sample_count": 9,
                        "high_strong_sample_count": 9,
                        "dominant_label_semantic": "trojan_untyped",
                        "dominant_label_samples": 9,
                        "unlabeled_samples": 0,
                        "known_locally": True,
                    },
                ],
                "top_repair_candidates": [
                    {
                        "family": "devixor",
                        "priority": "high",
                        "suggested_action": "review_db_type_mapping",
                        "db_type_slug": "dropper",
                        "issue": "type_mismatch",
                        "operator_model_candidate": "rat",
                        "fraud_posture_candidate": "banking_targeted+odf_capable",
                        "permission_signal_summary": "sms+telephony+overlay",
                        "sample_count": 725,
                        "high_strong_sample_count": 725,
                    },
                    {
                        "family": "blankbot",
                        "priority": "high",
                        "suggested_action": "add_db_family_mapping",
                        "db_type_slug": "<unmapped>",
                        "issue": "db_family_missing",
                        "operator_model_candidate": "unclear",
                        "fraud_posture_candidate": "unclear",
                        "permission_signal_summary": "overlay",
                        "sample_count": 9,
                        "high_strong_sample_count": 9,
                    },
                ],
            },
        },
    )
    monkeypatch.setattr(
        startup_menu._diagnostics_menu.du,
        "print_table",
        lambda rows, **kwargs: tables.append({"rows": list(rows), "kwargs": dict(kwargs)}),
    )
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_stat", lambda label, value: stats.append((str(label), value)))
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_subheader", lambda message: subheaders.append(str(message)))
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_note", lambda message: notes.append(str(message)))

    result = startup_menu._diagnostics_menu.show_profile_readiness_mapping_inventory()

    assert result == 0
    assert len(tables) == 8
    bucket_table, profile_table, taxonomy_table, unresolved_table, policy_table, conflict_table, discipline_table, repair_table = tables
    assert bucket_table["kwargs"]["title"] == "Readiness bucket summary"
    assert bucket_table["kwargs"]["columns"] == ["bucket", "samples", "families", "meaning"]
    assert {
        str(row["bucket"])
        for row in bucket_table["rows"]
    } == {
        "all_catalog",
        "android_platform",
        "android_with_permission_obs",
        "android_high_or_strong_vt_with_permission_obs",
        "android_labeled_primary_with_permission_obs",
        "android_banker_with_permission_obs",
        "android_family_ready_min3_permission_obs",
    }
    banker_bucket = next(row for row in bucket_table["rows"] if str(row["bucket"]) == "android_banker_with_permission_obs")
    all_mal_bucket = next(row for row in bucket_table["rows"] if str(row["bucket"]) == "android_high_or_strong_vt_with_permission_obs")
    assert banker_bucket["samples"] == 790
    assert banker_bucket["families"] == 12
    assert str(banker_bucket["meaning"]) == "Android banker-labeled samples with PI observations"
    assert all_mal_bucket["samples"] == 3280
    assert all_mal_bucket["families"] == 208
    assert [str(row["profile_id"]) for row in profile_table["rows"]] == ["banker", "malicious_temporal_stability"]
    assert profile_table["kwargs"]["title"] == "Supported profile readiness inventory"
    assert profile_table["kwargs"]["columns"] == ["profile_id", "bucket", "samples", "families", "status", "reason"]
    assert profile_table["rows"][0]["samples"] == 790
    assert profile_table["rows"][0]["families"] == 12
    assert profile_table["rows"][1]["samples"] == 3280
    assert profile_table["rows"][1]["families"] == 208
    assert taxonomy_table["kwargs"]["title"] == "Taxonomy drift summary"
    assert taxonomy_table["kwargs"]["columns"] == ["signal", "samples", "meaning"]
    assert {str(row["signal"]) for row in taxonomy_table["rows"]} == {
        "banker_label_bucket",
        "banker_type_bucket",
        "missing_primary_labels",
        "unresolved_family_samples",
        "known_unresolved_family_samples",
        "policy_held_family_samples",
    }
    assert unresolved_table["kwargs"]["title"] == "Top true unresolved family backlog"
    assert unresolved_table["kwargs"]["columns"] == ["family", "samples", "high_strong", "known_locally"]
    assert unresolved_table["rows"] == [
        {"family": "unknown", "samples": 289, "high_strong": 279, "known_locally": "no"},
        {"family": "blankbot", "samples": 9, "high_strong": 9, "known_locally": "yes"},
    ]
    assert conflict_table["kwargs"]["title"] == "Family/type conflict backlog"
    assert conflict_table["kwargs"]["columns"] == ["family", "priority", "action", "db_type", "issue", "operator_model", "fraud_posture", "perm_signal", "samples", "high_strong", "label_signal"]
    assert conflict_table["rows"] == [
        {
            "family": "devixor",
            "priority": "high",
            "action": "review_db_type_mapping",
            "db_type": "dropper",
            "issue": "type_mismatch",
            "operator_model": "rat",
            "fraud_posture": "banking_targeted+odf_capable",
            "perm_signal": "sms+telephony+overlay",
            "samples": 725,
            "high_strong": 725,
            "label_signal": "banker (725)",
        },
        {
            "family": "blankbot",
            "priority": "high",
            "action": "add_db_family_mapping",
            "db_type": "<unmapped>",
            "issue": "db_family_missing",
            "operator_model": "unclear",
            "fraud_posture": "unclear",
            "perm_signal": "overlay",
            "samples": 9,
            "high_strong": 9,
            "label_signal": "trojan_untyped (9)",
        },
    ]
    assert discipline_table["kwargs"]["title"] == "Taxonomy curation discipline"
    assert discipline_table["kwargs"]["columns"] == ["focus", "families", "meaning"]
    assert discipline_table["rows"] == [
        {
            "focus": "add_db_family_mapping",
            "families": 1,
            "meaning": "Suggested curation action for family/type conflict cleanup",
        },
        {
            "focus": "monitor_label_backfill",
            "families": 1,
            "meaning": "Suggested curation action for family/type conflict cleanup",
        },
        {
            "focus": "review_db_type_mapping",
            "families": 1,
            "meaning": "Suggested curation action for family/type conflict cleanup",
        },
    ]
    assert repair_table["kwargs"]["title"] == "Taxonomy repair candidates"
    assert repair_table["kwargs"]["columns"] == ["family", "priority", "action", "issue", "db_type", "samples", "high_strong", "perm_signal"]
    assert repair_table["rows"] == [
        {
            "family": "devixor",
            "priority": "high",
            "action": "review_db_type_mapping",
            "issue": "type_mismatch",
            "db_type": "dropper",
            "samples": 725,
            "high_strong": 725,
            "perm_signal": "sms+telephony+overlay",
        },
        {
            "family": "blankbot",
            "priority": "high",
            "action": "add_db_family_mapping",
            "issue": "db_family_missing",
            "db_type": "<unmapped>",
            "samples": 9,
            "high_strong": 9,
            "perm_signal": "overlay",
        },
    ]
    assert ("Supported operator profiles", 2) in stats
    assert ("Ambiguous / unmapped", 0) in stats
    assert ("True unresolved family slugs", 25) in stats
    assert ("Known unresolved families", 4) in stats
    assert ("Policy-held family tokens", 11) in stats
    assert ("True family/type conflict candidates", 3) in stats
    assert ("High-priority taxonomy conflicts", 2) in stats
    assert ("Taxonomy repair candidates", 2) in stats
    assert "Supported profile intent guide" in subheaders
    assert any("Supported banker profiles -> android_banker_with_permission_obs" in note for note in notes)
    assert any("Supported all-malicious and sensitivity profiles -> android_high_or_strong_vt_with_permission_obs" in note for note in notes)
    assert any("Supported dev profiles are included for local/operator checks" in note for note in notes)
    assert any("Only supported profiles are shown in this readiness inventory view." in note for note in notes)
    assert any("the supported operator architecture is the canonical final profile set" in note for note in notes)
    assert any("Banker type scope currently exceeds the banker label bucket by 505 sample(s)." in note for note in notes)
    assert any("Top true unresolved resolved-family slugs: unknown (289), blankbot (9)" in note for note in notes)
    assert any("Top policy-held token noise: badpack (8, packer_evasion_token), spybanker (4, generic_family_token)" in note for note in notes)
    assert any("Some unresolved family samples already map to known local taxonomy names" in note for note in notes)
    assert any("Top true family/type conflict candidates: devixor [type_mismatch], blankbot [db_family_missing]" in note for note in notes)
    assert any("Operator-model hypotheses: devixor → rat, blankbot → unclear" in note for note in notes)
    assert any("Suggested next actions: devixor → review_db_type_mapping, blankbot → add_db_family_mapping" in note for note in notes)
    assert any("Taxonomy curation discipline: high-priority conflicts=2/3; dominant action=review_db_type_mapping (1); dominant issue=type_mismatch (1)." in note for note in notes)
    assert any("Top taxonomy repair queue: devixor (725), blankbot (9)" in note for note in notes)
    assert any("Advisory only; does not enforce sample selection." in note for note in notes)
    assert not any(
        any(token in note.lower() for token in ("pass", "fail", "invalid", "blocked", "required"))
        for note in notes
    )


def test_profile_readiness_mapping_inventory_report_can_surface_ambiguous_count(monkeypatch) -> None:
    notes: list[str] = []

    monkeypatch.setattr(
        startup_menu._diagnostics_menu.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda: [
            {
                "profile_id": "future_profile",
                "bucket": None,
                "status": "ambiguous",
                "summary": "No readiness bucket mapped for this profile; review cohort filters manually.",
            }
        ],
    )
    monkeypatch.setattr(
        startup_menu._diagnostics_menu,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "degraded",
            "warnings": ["Permission Intel unavailable: android_permission_obs_sample not reachable on the Permission Intel connection."],
            "buckets": {},
        },
    )
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_stat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_note", lambda message: notes.append(str(message)))

    result = startup_menu._diagnostics_menu.show_profile_readiness_mapping_inventory()

    assert result == 0
    assert any("Permission Intel unavailable" in note for note in notes)
    assert any("Unmapped profile; review cohort filters manually." in note for note in notes)
    assert any("Ambiguous profile intent; no readiness bucket selected." in note for note in notes)


def test_profile_readiness_mapping_inventory_report_handles_unavailable_bucket_counts(monkeypatch) -> None:
    tables: list[dict[str, object]] = []
    notes: list[str] = []

    monkeypatch.setattr(
        startup_menu._diagnostics_menu.profile_manager,
        "inventory_cohort_readiness_mappings",
        lambda: [
            {
                "profile_id": "malicious_temporal_stability_locked",
                "bucket": "android_high_or_strong_vt_with_permission_obs",
                "status": "mapped",
                "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            }
        ],
    )
    monkeypatch.setattr(
        startup_menu._diagnostics_menu,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "degraded",
            "warnings": ["VT confidence surface unavailable: vt_sample_verdict_confidence_current missing on the primary Erebus connection."],
            "buckets": {
                "android_high_or_strong_vt_with_permission_obs": {
                    "sample_count": None,
                    "family_count": None,
                }
            },
            "taxonomy_signals": {},
        },
    )
    monkeypatch.setattr(
        startup_menu._diagnostics_menu.du,
        "print_table",
        lambda rows, **kwargs: tables.append({"rows": list(rows), "kwargs": dict(kwargs)}),
    )
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_stat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(startup_menu._diagnostics_menu.du, "print_note", lambda message: notes.append(str(message)))

    result = startup_menu._diagnostics_menu.show_profile_readiness_mapping_inventory()

    assert result == 0
    assert len(tables) == 3
    bucket_table, profile_table, taxonomy_table = tables
    bucket_row = next(
        row
        for row in bucket_table["rows"]
        if str(row["bucket"]) == "android_high_or_strong_vt_with_permission_obs"
    )
    assert bucket_row["samples"] == "unavailable"
    assert bucket_row["families"] == "unavailable"
    assert profile_table["rows"][0]["samples"] == "unavailable"
    assert profile_table["rows"][0]["families"] == "unavailable"
    assert all(row["samples"] == "unavailable" for row in taxonomy_table["rows"])
    assert any("VT confidence surface unavailable" in note for note in notes)


def test_main_menu_submenu_back_does_not_warn_invalid(monkeypatch) -> None:
    """Returning from a submenu should not emit a false invalid-choice warning."""
    choices = iter([4, 0, 0])
    warnings: list[str] = []

    monkeypatch.setattr(startup_menu, "_print_startup_context", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu.du, "print_warning", lambda message: warnings.append(str(message)))

    result = startup_menu.launch_startup_menu()

    assert result == 0
    assert "[MENU] Invalid choice received." not in warnings


def test_taxonomy_audit_defaults_to_latest_run_profile(monkeypatch, tmp_path: Path) -> None:
    """Taxonomy audit should default to the latest run profile."""
    output_root = tmp_path / "output"
    script_path = tmp_path / "family_label_taxonomy_audit.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(startup_menu, "_read_latest_run_id", lambda: "20260515T141956Z__58d84f")
    monkeypatch.setattr(
        startup_menu,
        "_resolve_latest_manifest_payload",
        lambda **_kwargs: ({"profile_params": {"profile_id": "malicious_temporal_stability"}}, "r1", Path("x")),
    )
    monkeypatch.setattr(startup_menu, "repo_operator_script", lambda _name: script_path)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(
        startup_menu,
        "subprocess",
        type("SubprocessStub", (), {"run": staticmethod(lambda cmd, check=False: commands.append(list(cmd)) or type("P", (), {"returncode": 0})())}),
    )

    result = startup_menu._run_family_label_taxonomy_audit_script()  # pylint: disable=protected-access

    assert result == 0
    assert commands
    assert "--profile" in commands[0]
    assert "malicious_temporal_stability" in commands[0]


def test_taxonomy_audit_warns_on_different_profile(monkeypatch, tmp_path: Path) -> None:
    """Different-profile audits should warn before continuing."""
    output_root = tmp_path / "output"
    script_path = tmp_path / "family_label_taxonomy_audit.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    warnings: list[str] = []
    choices = iter([2])

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(startup_menu, "_read_latest_run_id", lambda: "20260515T141956Z__58d84f")
    monkeypatch.setattr(
        startup_menu,
        "_resolve_latest_manifest_payload",
        lambda **_kwargs: ({"profile_params": {"profile_id": "malicious_temporal_stability"}}, "r1", Path("x")),
    )
    monkeypatch.setattr(startup_menu, "repo_operator_script", lambda _name: script_path)
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu, "resolve_and_validate_profile", lambda **_kwargs: "banker")
    monkeypatch.setattr(startup_menu.mu, "confirm_prompt", lambda _message="": False)
    monkeypatch.setattr(startup_menu.du, "print_warning", lambda message: warnings.append(str(message)))

    result = startup_menu._run_family_label_taxonomy_audit_script()  # pylint: disable=protected-access

    assert result == 1
    assert any("Different profile than latest run" in message for message in warnings)


def test_android_missing_resolution_triage_script_runs_operator_script(monkeypatch, tmp_path: Path) -> None:
    """Android missing-resolution triage should invoke the diagnostics script."""
    script_path = tmp_path / "report_android_missing_resolution_triage.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(startup_menu, "repo_operator_script", lambda *parts: script_path)
    monkeypatch.setattr(
        startup_menu,
        "subprocess",
        type("SubprocessStub", (), {"run": staticmethod(lambda cmd, check=False: commands.append(list(cmd)) or type("P", (), {"returncode": 0})())}),
    )

    result = startup_menu._run_android_missing_resolution_triage_script()  # pylint: disable=protected-access

    assert result == 0
    assert commands
    assert commands[0][0].endswith("python3")
    assert commands[0][1] == str(script_path)


def test_refresh_backlog_triage_exports_runs_all_triage_scripts(monkeypatch) -> None:
    """Composite backlog refresh should run all backlog triage exports in sequence."""
    calls: list[str] = []

    monkeypatch.setattr(
        startup_menu,
        "_run_android_missing_resolution_triage_script",
        lambda: calls.append("android") or 0,
    )
    monkeypatch.setattr(
        startup_menu,
        "_run_vt_false_positive_review_triage_script",
        lambda: calls.append("vt") or 0,
    )
    monkeypatch.setattr(
        startup_menu,
        "_run_policy_held_token_risk_script",
        lambda: calls.append("policy") or 0,
    )

    result = startup_menu._refresh_backlog_triage_exports()  # pylint: disable=protected-access

    assert result == 0
    assert calls == ["android", "vt", "policy"]


def test_policy_held_token_risk_script_runs_operator_script(monkeypatch, tmp_path: Path) -> None:
    """Policy-held token-risk triage should invoke the diagnostics script."""
    script_path = tmp_path / "report_android_policy_held_token_risk.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(startup_menu, "repo_operator_script", lambda *parts: script_path)
    monkeypatch.setattr(
        startup_menu,
        "subprocess",
        type("SubprocessStub", (), {"run": staticmethod(lambda cmd, check=False: commands.append(list(cmd)) or type("P", (), {"returncode": 0})())}),
    )

    result = startup_menu._run_policy_held_token_risk_script()  # pylint: disable=protected-access

    assert result == 0
    assert commands
    assert commands[0][0].endswith("python3")
    assert commands[0][1] == str(script_path)


def test_vt_false_positive_review_triage_script_runs_operator_script(monkeypatch, tmp_path: Path) -> None:
    """VT false-positive triage should invoke the diagnostics script."""
    script_path = tmp_path / "report_vt_false_positive_review_triage.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(startup_menu, "repo_operator_script", lambda *parts: script_path)
    monkeypatch.setattr(
        startup_menu,
        "subprocess",
        type("SubprocessStub", (), {"run": staticmethod(lambda cmd, check=False: commands.append(list(cmd)) or type("P", (), {"returncode": 0})())}),
    )

    result = startup_menu._run_vt_false_positive_review_triage_script()  # pylint: disable=protected-access

    assert result == 0
    assert commands
    assert commands[0][0].endswith("python3")
    assert commands[0][1] == str(script_path)


def test_vt_false_positive_triage_script_exports_live_report(monkeypatch, tmp_path: Path) -> None:
    """The triage report script should be callable from the diagnostics menu helper."""
    script_path = tmp_path / "report_vt_false_positive_review_triage.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    commands: list[list[str]] = []

    result = startup_menu._diagnostics_menu.run_vt_false_positive_review_triage_script(  # pylint: disable=protected-access
        operator_script_resolver=lambda *_parts: script_path,
        subprocess_run=lambda cmd, check=False: commands.append(list(cmd)) or type("P", (), {"returncode": 0})(),
    )

    assert result == 0
    assert commands
    assert commands[0][0].endswith("python3")
    assert commands[0][1] == str(script_path)


def test_parser_menu_does_not_repeat_state_block_when_state_is_unchanged(monkeypatch) -> None:
    """Parser submenu should not reprint the summary block when state did not change."""
    choices = iter([1, 0])
    calls = {"state": 0}

    monkeypatch.setattr(
        startup_menu.vendor_diagnostics,
        "get_parser_summary_state",
        lambda **_kwargs: {
            "csv_ready": True,
            "workbook_ready": False,
            "observed_engines": 95,
            "parser_mapped_vendors": 25,
            "unmapped_vendors": 70,
            "selected_vendors": 8,
            "engine_scoring_universe": 95,
        },
    )
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu.vendor_diagnostics, "print_compact_vendor_coverage_snapshot", lambda: 0)
    monkeypatch.setattr(
        startup_menu.vendor_diagnostics,
        "print_parser_diagnostics_state",
        lambda: calls.__setitem__("state", calls["state"] + 1),
    )

    startup_menu._launch_parser_vendor_coverage_menu()  # pylint: disable=protected-access

    assert calls["state"] == 1


def test_parser_menu_uses_tuning_labels_in_compact_mode(monkeypatch) -> None:
    """Parser submenu should default to tuning workflow labels in compact mode."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, *_, **kwargs):
        captured["title"] = str(kwargs.get("title", ""))
        captured["labels"] = list(options)
        return 0

    monkeypatch.setattr(
        startup_menu.vendor_diagnostics,
        "get_parser_summary_state",
        lambda **_kwargs: {
            "display_mode": "compact",
            "csv_ready": True,
            "workbook_ready": False,
            "observed_engines": 95,
            "parser_mapped_vendors": 25,
            "unmapped_vendors": 70,
            "selected_vendors": 8,
            "engine_scoring_universe": 95,
        },
    )
    monkeypatch.setattr(startup_menu.vendor_diagnostics, "print_parser_diagnostics_state", lambda: None)
    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_parser_vendor_coverage_menu()  # pylint: disable=protected-access

    assert captured["title"] == "Parser & vendor tuning"
    assert captured["labels"] == [
        "Parser summary",
        "Parser onboarding workflow",
        "Selected vendor signal quality",
        "Workbook drill-down requirements",
        "Single-vendor parser drill-down",
    ]


def test_open_run_science_index_falls_back_to_best_available_index(monkeypatch, tmp_path: Path) -> None:
    """Run science index action should fall back to another authoritative index when canonical is missing."""
    output_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root, _ = _make_run_dirs(output_root, run_id)
    _write_text(run_root / "run_evidence_index.md", "# evidence\n")
    notes: list[str] = []

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(startup_menu, "_read_latest_run_id", lambda: run_id)
    monkeypatch.setattr(startup_menu.du, "print_note", lambda message: notes.append(str(message)))

    result = startup_menu._open_run_science_index()  # pylint: disable=protected-access

    assert result == 1
    assert any("Canonical run_science_index.md is missing" in message for message in notes)


def test_data_diagnostics_overview_is_not_reprinted_when_unchanged(monkeypatch) -> None:
    """Data diagnostics should not reprint the overview when returning to the menu without state changes."""
    choices = iter([1, 0])
    calls = {"overview": 0}

    monkeypatch.setattr(startup_menu, "_read_latest_run_id", lambda: "r1")
    monkeypatch.setattr(
        startup_menu.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_: {
            "latest_run_id": "r1",
            "run_science_index_path": "/tmp/r1.md",
            "run_science_index_canonical": True,
            "rows": [{"label": "Cohort / labels", "status": "GREEN"}],
        },
    )
    monkeypatch.setattr(
        startup_menu.diagnostics_banners,
        "print_compact_diagnostics_overview",
        lambda **_: calls.__setitem__("overview", calls["overview"] + 1),
    )
    monkeypatch.setattr(startup_menu.mu, "display_menu", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(startup_menu, "_open_run_science_index", lambda: 0)

    startup_menu._launch_data_diagnostics_menu()  # pylint: disable=protected-access

    assert calls["overview"] == 1


def test_reproducibility_menu_uses_back_label(monkeypatch) -> None:
    """Submenus should present 0 as Back, not Exit."""
    captured: list[str] = []

    def _fake_display_menu(*_args, **kwargs):
        captured.append(str(kwargs.get("exit_label", "")))
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_reproducibility_menu()  # pylint: disable=protected-access

    assert captured == ["Back"]


def test_read_latest_run_id_prefers_newest_run_scoped_manifest(monkeypatch, tmp_path: Path) -> None:
    """Latest run banner should prefer the newest run-scoped manifest over stale pointers."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    old_run = runs_dir / "20260307T213823Z__b74bdb"
    new_run = runs_dir / "20260321T134027Z__f39e96"
    old_run.mkdir(parents=True, exist_ok=True)
    new_run.mkdir(parents=True, exist_ok=True)
    _write_text(old_run / "run_manifest.json", "{}")
    _write_text(new_run / "run_manifest.json", "{}")

    promoted_dir = out_root / "promoted"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    _write_text(promoted_dir / "latest_run.txt", "20260307T213823Z__b74bdb")

    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    _write_json(diagnostics_dir / "run_manifest.latest.json", {"run_id": "20260307T213823Z__b74bdb"})

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    assert startup_menu._read_latest_run_id() == "20260321T134027Z__f39e96"  # pylint: disable=protected-access


def test_read_latest_run_id_ignores_invalid_test_run_ids(monkeypatch, tmp_path: Path) -> None:
    """Latest run banner should prefer valid timestamped runs over junk ids like r1."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T134027Z__f39e96"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        valid_run / "run_manifest.json",
        {
            "run_id": "20260321T134027Z__f39e96",
            "timestamp_utc": "2026-03-21T13:40:27.139708+00:00",
        },
    )
    _write_json(junk_run / "run_manifest.json", {"run_id": "r1", "timestamp_utc": "t1"})

    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    _write_json(diagnostics_dir / "run_manifest.latest.json", {"run_id": "r1"})

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    assert startup_menu._read_latest_run_id() == "20260321T134027Z__f39e96"  # pylint: disable=protected-access


def test_quick_health_check_passes_with_complete_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should pass when required latest artifacts are present."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T000000Z__abc123"
    run_root, _ = _make_run_dirs(out_root, run_id)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    vendor_gate_path = diagnostics_dir / f"vendor_gate_debug_{run_id}.csv"
    run_paths_manifest_path = diagnostics_dir / f"run_paths_manifest_{run_id}.json"
    _write_text(split_path, "sample_id,fold\n1,0\n")
    _write_text(model_config_path, "{}")
    _write_text(vendor_gate_path, "vendor,ok\nv,1\n")
    _write_text(run_paths_manifest_path, "{}")
    _write_text(diagnostics_dir / "parser_quality.latest.csv", "vendor,parser_mapped\nv,1\n")
    _write_text(diagnostics_dir / "vendor_parser_coverage.latest.csv", "vendor,parser_mapped\nv,1\n")

    manifest_payload = {
        "run_id": run_id,
        "timestamp_utc": "2026-03-03T00:00:00Z",
        "split": {"split_audit_path": str(split_path)},
        "model_config_snapshot_path": str(model_config_path),
        "vendor_gate_debug_path": str(vendor_gate_path),
        "profile_params": {"profile_id": "dev_fast"},
        "artifact_list": [],
    }
    _write_json(diagnostics_dir / "run_manifest.latest.json", manifest_payload)

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 0


def test_quick_health_check_fails_when_pointer_manifest_has_no_canonical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should fail for pointer manifest without canonical run manifest."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    pointer_payload = {
        "run_id": "20260303T000000Z__abc123",
        "created_at_utc": "2026-03-03T00:00:00Z",
        "run_root": str(out_root / "runs" / "20260303T000000Z__abc123"),
    }
    _write_json(diagnostics_dir / "run_manifest.latest.json", pointer_payload)

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 1


def test_quick_health_check_warns_but_passes_without_optional_diagnostics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Quick health check should return success when only non-fatal checks are missing."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T000000Z__abc123"
    run_root, _ = _make_run_dirs(out_root, run_id)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    _write_text(split_path, "sample_id,fold\n1,0\n")
    _write_text(model_config_path, "{}")
    _write_json(
        diagnostics_dir / "run_manifest.latest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-03T00:00:00Z",
            "split": {"split_audit_path": str(split_path)},
            "model_config_snapshot_path": str(model_config_path),
            "profile_params": {"profile_id": "dev_fast"},
            "artifact_list": [],
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_quick_health_check()  # pylint: disable=protected-access
    assert result == 0


def test_run_specific_health_check_writes_json_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Run-specific health check should emit a run-scoped JSON report."""
    out_root = tmp_path / "output"
    diagnostics_dir = out_root / "diagnostics"
    run_id = "20260303T010000Z__def456"
    run_root, _ = _make_run_dirs(out_root, run_id)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    split_path = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    model_config_path = diagnostics_dir / f"model_config_snapshot_{run_id}.json"
    _write_text(split_path, "sample_id,fold\n1,0\n")
    _write_text(model_config_path, "{}")
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-03T01:00:00Z",
            "split": {"split_audit_path": str(split_path)},
            "model_config_snapshot_path": str(model_config_path),
            "profile_params": {"profile_id": "malicious_temporal_stability"},
            "artifact_list": [],
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._run_health_check(run_id=run_id)  # pylint: disable=protected-access

    assert result == 0
    report_path = diagnostics_dir / f"quick_health_check_{run_id}.json"
    assert report_path.exists()


def test_recent_runs_overview_returns_warning_when_empty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Recent runs overview should return non-zero when no run manifests exist."""
    out_root = tmp_path / "output"
    (out_root / "runs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)

    result = startup_menu._show_recent_runs_overview()  # pylint: disable=protected-access
    assert result == 1


def test_recent_runs_overview_reads_run_scoped_manifests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Recent runs overview should succeed when run-scoped manifests are present."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    run_a = runs_dir / "20260303T020000Z__aaa111"
    run_b = runs_dir / "20260303T030000Z__bbb222"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    _write_json(
        run_a / "run_manifest.json",
        {
            "run_id": "20260303T020000Z__aaa111",
            "timestamp_utc": "2026-03-03T02:00:00Z",
            "cohort_size": 1200,
            "profile_params": {"profile_id": "malicious_temporal_stability"},
            "model_summary": {"top_model": "random_forest", "top_macro_f1": 0.71},
        },
    )
    _write_json(
        run_b / "run_manifest.json",
        {
            "run_id": "20260303T030000Z__bbb222",
            "timestamp_utc": "2026-03-03T03:00:00Z",
            "cohort_size": 1300,
            "publication_ready_status": "READY",
            "paper_cohort_contract": {"cohort_lock_status": "count_only_incomplete_sample_lock"},
            "profile_params": {"profile_id": "dev_fast"},
            "model_summary": {"top_model": "logistic_regression", "top_macro_f1": 0.80},
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access
    assert result == 0


def test_recent_runs_overview_demotes_invalid_run_ids(monkeypatch, tmp_path: Path) -> None:
    """Recent runs table should hide junk ids like r1 from the default operator view."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T161433Z__fdaeb0"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)

    _write_json(
        valid_run / "run_manifest.json",
        {
            "run_id": "20260321T161433Z__fdaeb0",
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "profile_params": {"profile_id": "malicious_temporal_stability"},
        },
    )
    _write_json(
        junk_run / "run_manifest.json",
        {
            "run_id": "r1",
            "timestamp_utc": "t1",
            "profile_params": {"profile_id": "test"},
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert [row["run_id"] for row in captured["rows"]] == ["20260321T161433Z__fdaeb0"]


def test_recent_runs_overview_can_include_noncanonical_runs(monkeypatch, tmp_path: Path) -> None:
    """Advanced history view should include non-canonical run folders when requested."""
    out_root = tmp_path / "output"
    runs_dir = out_root / "runs"
    valid_run = runs_dir / "20260321T161433Z__fdaeb0"
    junk_run = runs_dir / "r1"
    valid_run.mkdir(parents=True, exist_ok=True)
    junk_run.mkdir(parents=True, exist_ok=True)

    _write_json(
        valid_run / "run_manifest.json",
        {
            "run_id": "20260321T161433Z__fdaeb0",
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "profile_params": {"profile_id": "malicious_temporal_stability"},
        },
    )
    _write_json(
        junk_run / "run_manifest.json",
        {
            "run_id": "r1",
            "timestamp_utc": "t1",
            "profile_params": {"profile_id": "test"},
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5, include_noncanonical=True)  # pylint: disable=protected-access

    assert result == 0
    assert [row["run_id"] for row in captured["rows"]] == [
        "20260321T161433Z__fdaeb0",
        "r1",
    ]


def test_recent_runs_overview_uses_runtime_and_model_fallbacks(monkeypatch, tmp_path: Path) -> None:
    """Recent run history should use run-scoped fallbacks when manifest fields are missing."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)

    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "cohort_size": 1226,
            "profile_params": {"profile_id": "malicious_temporal_stability"},
        },
    )
    _write_text(
        diagnostics_dir / f"pipeline_stage_timings_{run_id}.csv",
        "stage,duration_sec,run_id,timestamp_utc\n"
        f"samples,1.2,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"training,3.4,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"manifest,0.4,{run_id},2026-03-21T16:17:41.213765+00:00\n",
    )
    _write_text(
        diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "Model,Macro F1-Score,Rank,Top\n"
        "random_forest,0.9530,1,*\n",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["top_model"] == "random_forest"
    assert captured["rows"][0]["top_macro_f1"] == "0.9530"
    assert captured["rows"][0]["runtime_sec"] == "5.00"


def test_recent_runs_overview_prefers_canonical_run_summary(monkeypatch, tmp_path: Path) -> None:
    """Recent run history should use run_summary.json when manifest fields are thin."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, _ = _make_run_dirs(out_root, run_id)

    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "profile_params": {"profile_id": "malicious_temporal_stability"},
        },
    )
    _write_json(
        run_root / "run_summary.json",
        {
            "run_id": run_id,
            "profile_id": "malicious_temporal_stability",
            "cohort_size": 1226,
            "top_model": "xgboost",
            "top_macro_f1": 0.9444,
            "pipeline_runtime_sec": 42.5,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["top_model"] == "xgboost"
    assert captured["rows"][0]["top_macro_f1"] == "0.9444"
    assert captured["rows"][0]["runtime_sec"] == 42.5


def test_recent_runs_overview_includes_methodology_columns(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "publication_ready_status": "READY",
            "paper_cohort_contract": {"cohort_lock_status": "count_only_incomplete_sample_lock"},
            "profile_params": {"profile_id": "paper2_demo"},
        },
    )
    _write_text(
        diagnostics_dir / f"cohort_filter_contract_{run_id}.json",
        '{"cohort_gates":{"min_malicious_detections":5}}',
    )
    _write_text(
        diagnostics_dir / f"analysis_snapshot_filter_summary_{run_id}.csv",
        "mode,source_total,post_filter_total\npaper_locked_snapshot_membership,100,98\n",
    )
    _write_text(
        diagnostics_dir / f"cohort_gate_counts_{run_id}.csv",
        (
            "run_id,step,gate_name,count_before,count_after,dropped,details\n"
            f"{run_id},1,min_malicious_detections,98,97,1,"
            "\">=5; rescued_unknown_consensus=3\"\n"
        ),
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["publication_ready_status"] == "READY"
    assert captured["rows"][0]["cohort_lock_status"] == "count-only"
    assert "membership=locked_sample_ids" in str(captured["rows"][0]["cohort_methodology"])
    assert "rescued_unknown=3" in str(captured["rows"][0]["cohort_methodology"])


def test_recent_runs_overview_includes_taxonomy_drift_methodology(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, _diagnostics_dir = _make_run_dirs(out_root, run_id)
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "publication_ready_status": "READY",
            "paper_cohort_contract": {
                "cohort_lock_status": "membership_locked_taxonomy_drift",
                "sample_id_lock": {
                    "taxonomy_label_drift": {
                        "drift_class": "taxonomy_expansion",
                        "family_delta": 5,
                        "type_delta": 1,
                    }
                },
            },
            "profile_params": {"profile_id": "paper2_demo"},
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_table_rows(monkeypatch)

    result = startup_menu._show_recent_runs_overview(limit=5)  # pylint: disable=protected-access

    assert result == 0
    assert captured["rows"][0]["cohort_lock_status"] == "taxonomy-drift"
    assert "taxonomy=taxonomy_expansion" in str(captured["rows"][0]["cohort_methodology"])
    assert "family_delta=+5" in str(captured["rows"][0]["cohort_methodology"])


def test_run_status_history_menu_includes_advanced_history_option(monkeypatch) -> None:
    """Run status menu should expose an explicit advanced history option."""
    captured: list[str] = []

    def _fake_display_menu(options, *_, **__):
        captured.extend(list(options))
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_run_overview_menu()  # pylint: disable=protected-access

    assert captured == [
        "Current Run Summary",
        "Recent Run History",
        "Session and Output Details",
        "Full Run Folder History (Advanced)",
    ]


def test_current_run_summary_uses_status_aware_fallbacks(monkeypatch, tmp_path: Path) -> None:
    """Current run summary should use stage/model exports when manifest fields are thin."""
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)

    _write_latest_run_manifest(out_root, {"run_id": run_id})
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "cohort_size": 1226,
            "selected_vendor_count": 8,
            "vendor_constrained_run_flag": False,
            "profile_params": {"profile_id": "malicious_temporal_stability"},
        },
    )
    _write_text(
        diagnostics_dir / f"pipeline_stage_timings_{run_id}.csv",
        "stage,duration_sec,run_id,timestamp_utc\n"
        f"samples,1.2,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"training,3.4,{run_id},2026-03-21T16:17:41.213765+00:00\n"
        f"manifest,0.4,{run_id},2026-03-21T16:17:41.213765+00:00\n",
    )
    _write_text(
        diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "Model,Macro F1-Score,Rank,Top\n"
        "random_forest,0.9530,1,*\n"
        "xgboost,0.9412,2,\n",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_stat_rows(monkeypatch)

    result = startup_menu._show_latest_run_snapshot()  # pylint: disable=protected-access

    values = {label: value for label, value in captured}
    assert result == 0
    assert values["Run Status"] == "Complete"
    assert values["Completed Through Stage"] == "Manifest Finalization"
    assert values["Top Model"] == "random_forest"
    assert values["Top Macro F1"] == "0.9530"


def test_current_run_summary_includes_methodology_fields(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)
    _write_latest_run_manifest(out_root, {"run_id": run_id})
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "publication_ready_status": "READY",
            "paper_cohort_contract": {"cohort_lock_status": "count_only_incomplete_sample_lock"},
            "profile_params": {"profile_id": "paper2_demo"},
        },
    )
    _write_text(
        diagnostics_dir / f"cohort_filter_contract_{run_id}.json",
        '{"cohort_gates":{"min_malicious_detections":5}}',
    )
    _write_text(
        diagnostics_dir / f"analysis_snapshot_filter_summary_{run_id}.csv",
        "mode,source_total,post_filter_total\npaper_locked_snapshot_membership,100,98\n",
    )
    _write_text(
        diagnostics_dir / f"cohort_gate_counts_{run_id}.csv",
        (
            "run_id,step,gate_name,count_before,count_after,dropped,details\n"
            f"{run_id},1,min_malicious_detections,98,97,1,"
            "\">=5; rescued_unknown_consensus=3\"\n"
        ),
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_stat_rows(monkeypatch)

    result = startup_menu._show_latest_run_snapshot()  # pylint: disable=protected-access

    values = {label: value for label, value in captured}
    assert result == 0
    assert values["Publication-ready Status"] == "READY"
    assert values["Cohort Lock Status"] == "count-only"
    assert "membership=locked_sample_ids" in str(values["Cohort Methodology"])
    assert "rescued_unknown=3" in str(values["Cohort Methodology"])


def test_current_run_summary_includes_taxonomy_drift_semantics(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260321T161433Z__fdaeb0"
    run_root, _diagnostics_dir = _make_run_dirs(out_root, run_id)
    _write_latest_run_manifest(out_root, {"run_id": run_id})
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "timestamp_utc": "2026-03-21T16:14:33.823560+00:00",
            "publication_ready_status": "READY",
            "paper_cohort_contract": {
                "cohort_lock_status": "membership_locked_taxonomy_drift",
                "sample_id_lock": {
                    "taxonomy_label_drift": {
                        "drift_class": "taxonomy_expansion",
                        "family_delta": 5,
                        "type_delta": 1,
                        "recommended_action": "Review newly split families/types.",
                    }
                },
            },
            "profile_params": {"profile_id": "paper2_demo"},
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    captured = _capture_stat_rows(monkeypatch)

    result = startup_menu._show_latest_run_snapshot()  # pylint: disable=protected-access

    values = {label: value for label, value in captured}
    assert result == 0
    assert values["Cohort Lock Status"] == "taxonomy-drift"
    assert "taxonomy_expansion" in str(values["Taxonomy Drift"])
    assert "family_delta=+5" in str(values["Taxonomy Drift"])


def test_within_cross_type_error_snapshot_reads_bundle_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Within-vs-cross snapshot should load bundle artifact and render summary."""
    out_root = tmp_path / "output"
    run_id = "20260305T055230Z__f3e105"
    diagnostics_dir = out_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    _write_latest_run_manifest(out_root, {"run_id": run_id})
    confusion_path = (
        out_root
        / "runs"
        / run_id
        / "bundles"
        / "permission_trends"
        / "tables"
        / "confusion_within_vs_cross_type.latest.csv"
    )
    confusion_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(
        confusion_path,
        "run_id,error_type,count\n"
        f"{run_id},within_type_error,41\n"
        f"{run_id},cross_type_error,39\n"
        f"{run_id},total_error,80\n"
        f"{run_id},within_type_error_ratio,0.5125\n"
        f"{run_id},cross_type_error_ratio,0.4875\n"
        f"{run_id},total_predictions,1286\n",
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_within_cross_type_error_snapshot()  # pylint: disable=protected-access
    assert result == 0


def test_within_cross_type_error_snapshot_fails_on_missing_schema(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Within-vs-cross snapshot should fail if required columns are missing."""
    out_root = tmp_path / "output"
    confusion_path = (
        out_root
        / "bundles"
        / "latest"
        / "permission_trends"
        / "tables"
        / "confusion_within_vs_cross_type.latest.csv"
    )
    confusion_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(confusion_path, "run_id,bad_col\nr1,1\n")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._show_within_cross_type_error_snapshot()  # pylint: disable=protected-access
    assert result == 1


def test_handle_confusion_matrix_export_blocks_multi_model_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Confusion export should not copy a primary matrix when multiple model matrices exist."""
    out_root = tmp_path / "output"
    run_id = "20260305T101010Z__abc123"
    diagnostics_dir = out_root / "diagnostics"
    run_root = out_root / "runs" / run_id
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    _write_latest_run_manifest(out_root, {"run_id": run_id, "run_root": str(run_root)})
    _write_json(
        run_root / "run_manifest.json",
        {"run_id": run_id, "model_summary": {"top_model": "logistic_regression"}},
    )
    _write_text(conf_dir / "confusion_matrix_logistic_regression.png", "a")
    _write_text(conf_dir / "confusion_matrix_random_forest.png", "b")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._handle_confusion_matrix_export()  # pylint: disable=protected-access

    assert result == 0
    assert not (run_root / "evidence_bundle" / "confusion_matrix_primary.png").exists()


def test_handle_confusion_matrix_export_copies_single_model_matrix(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Confusion export should copy the only model matrix into the canonical evidence bundle only."""
    out_root = tmp_path / "output"
    run_id = "20260305T111111Z__def456"
    diagnostics_dir = out_root / "diagnostics"
    run_root = out_root / "runs" / run_id
    conf_dir = run_root / "conf_matrices"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    conf_dir.mkdir(parents=True, exist_ok=True)
    _write_latest_run_manifest(out_root, {"run_id": run_id, "run_root": str(run_root)})
    _write_json(
        run_root / "run_manifest.json",
        {"run_id": run_id, "model_summary": {"top_model": "logistic_regression"}},
    )
    source = conf_dir / "confusion_matrix_logistic_regression.png"
    _write_text(source, "matrix")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    result = startup_menu._handle_confusion_matrix_export()  # pylint: disable=protected-access

    target = run_root / "evidence_bundle" / "confusion_matrix_primary.png"
    assert result == 0
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "matrix"


def test_review_summary_flags_temporal_generalization_gap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260526T124924Z__c55a08"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    _write_latest_run_manifest(
        out_root,
        {
            "run_id": run_id,
            "run_root": str(run_root),
        },
    )
    _write_json(
        run_root / "run_manifest.json",
        {
            "run_id": run_id,
            "profile_params": {"profile_id": "malicious_temporal_stability_locked"},
            "publication_ready_status": "NOT_APPLICABLE",
            "split": {
                "split_algorithm": "temporal_year_holdout_v1",
                "temporal_split_summary": {
                    "test_year_floor": 2024,
                    "observed_year_min": 2020,
                    "observed_year_max": 2025,
                    "test_rows_dropped_unseen_train_classes": 219,
                },
            },
        },
    )
    _write_text(
        diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "\n".join(
            [
                "Model,Accuracy,Precision,Recall,F1-Score,Macro F1-Score,Rank,Top",
                "random_forest,0.5474,0.7295,0.5474,0.589,0.3261,1,*",
                "logistic_regression,0.3504,0.6528,0.3504,0.4386,0.2505,2,",
            ]
        ),
    )
    _write_text(diagnostics_dir / "cohort_funnel.md", "# funnel\n")
    _write_text(diagnostics_dir / "feature_set_ablation_summary.md", "# ablation\n")
    _write_text(diagnostics_dir / "figure_validity_audit.md", "# figure\n")
    _write_text(diagnostics_dir / "run_science_index.md", "# index\n")
    _write_json(diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json", {"taxonomy_mismatch_count": 0})

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(
        startup_menu._review_menu,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )
    monkeypatch.setattr(
        startup_menu._review_menu,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": "Readiness mapping is advisory only; it does not enforce sample selection.",
        },
    )

    summary = startup_menu._review_menu.build_review_latest_run_summary(
        output_root=out_root,
        latest_run_id=run_id,
    )

    temporal_notes = [str(x) for x in summary.get("temporal_generalization_notes", [])]
    warnings = [str(x) for x in summary.get("warnings", [])]
    tuning_actions = [str(x) for x in summary.get("tuning_actions", [])]
    assert any("dropped 219 future-only row(s)" in note for note in temporal_notes)
    assert any("Macro-F1 0.3261" in note for note in temporal_notes)
    assert any("Temporal generalization gap" in note for note in warnings)
    assert any("forward-time family drift" in note for note in tuning_actions)


def test_review_summary_surfaces_label_strategy_in_top_level_review(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "r_labels"
    run_root, diagnostics_dir = _make_run_dirs(out_root, run_id)
    _write_latest_run_manifest(
        out_root,
        {
            "run_id": run_id,
            "profile_id": "dev_fast",
            "publication_ready_status": "NOT_APPLICABLE",
        },
    )
    _write_text(run_root / "run_science_index.md", "# index\n")
    _write_json(diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json", {"taxonomy_mismatch_count": 0})
    _write_json(
        diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json",
        {
            "label_strategy": {
                "preferred_family_target": "family_id",
                "preferred_type_target": "type_slug",
                "avoid_for_primary_claims": ["category_primary"],
                "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
            }
        },
    )

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(
        startup_menu._review_menu,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )
    monkeypatch.setattr(
        startup_menu._review_menu,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": "Readiness mapping is advisory only; it does not enforce sample selection.",
        },
    )

    summary = startup_menu._review_menu.build_review_latest_run_summary(
        output_root=out_root,
        latest_run_id=run_id,
    )

    assert summary["label_strategy_summary"]["preferred_family_target"] == "family_id"
    assert summary["label_strategy_summary"]["preferred_type_target"] == "type_slug"
    assert summary["label_strategy_summary"]["avoid_for_primary_claims"] == ["category_primary"]
    tuning_actions = [str(x) for x in summary.get("tuning_actions", [])]
    assert any("Keep supervision anchored on family_id for family and type_slug for coarse taxonomy before retuning models." in action for action in tuning_actions)


def test_evidence_readiness_hub_uses_generic_labels(monkeypatch) -> None:
    """Evidence readiness hub should expose generic operator-facing labels."""
    captured: dict[str, object] = {}

    def _fake_display_menu(options, **kwargs):
        captured["options"] = list(options)
        captured["title"] = kwargs.get("title")
        return 0

    monkeypatch.setattr(startup_menu.mu, "display_menu", _fake_display_menu)

    startup_menu._launch_evidence_readiness_hub()  # pylint: disable=protected-access

    options = captured["options"]
    assert "Evidence Readiness Summary (export JSON/MD)" in options
    assert "Cohort Lock Checker" in options
    assert "Evidence Bundle Series Aggregator" in options
    assert captured["title"] == "Evidence readiness"
    assert policy_table["kwargs"]["title"] == "Top policy-held token backlog"
    assert policy_table["kwargs"]["columns"] == ["family", "samples", "high_strong", "token_kind"]
    assert policy_table["rows"] == [
        {"family": "badpack", "samples": 8, "high_strong": 8, "token_kind": "packer_evasion_token"},
        {"family": "spybanker", "samples": 4, "high_strong": 4, "token_kind": "generic_family_token"},
    ]
