"""Tests for shared backlog triage context and operator summary."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.backlog_triage_context import (
    format_pipeline_preflight_backlog_lines,
    load_backlog_triage_context,
    load_backlog_triage_context_with_refresh,
    preflight_auto_refresh_backlog_enabled,
    preflight_backlog_snapshot_enabled,
)


def test_preflight_auto_refresh_backlog_enabled_respects_env(monkeypatch) -> None:
    monkeypatch.delenv("OBSIDIANDROID_PREFLIGHT_REFRESH_BACKLOG", raising=False)
    monkeypatch.delenv("OBSIDIANDROID_PREFLIGHT_SKIP_BACKLOG", raising=False)
    monkeypatch.delenv("OBSIDIANDROID_TEST_OUTPUT_ROOT", raising=False)
    assert preflight_auto_refresh_backlog_enabled() is True
    monkeypatch.setenv("OBSIDIANDROID_PREFLIGHT_REFRESH_BACKLOG", "0")
    assert preflight_auto_refresh_backlog_enabled() is False
    monkeypatch.setenv("OBSIDIANDROID_PREFLIGHT_REFRESH_BACKLOG", "off")
    assert preflight_auto_refresh_backlog_enabled() is False


def test_preflight_backlog_snapshot_disabled_for_tests_and_skip_env(monkeypatch) -> None:
    monkeypatch.delenv("OBSIDIANDROID_TEST_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("OBSIDIANDROID_PREFLIGHT_SKIP_BACKLOG", raising=False)
    assert preflight_backlog_snapshot_enabled() is True
    monkeypatch.setenv("OBSIDIANDROID_TEST_OUTPUT_ROOT", "/tmp/pytest-output")
    assert preflight_backlog_snapshot_enabled() is False
    monkeypatch.delenv("OBSIDIANDROID_TEST_OUTPUT_ROOT", raising=False)
    monkeypatch.setenv("OBSIDIANDROID_PREFLIGHT_SKIP_BACKLOG", "1")
    assert preflight_backlog_snapshot_enabled() is False
    assert preflight_auto_refresh_backlog_enabled() is False


def test_format_pipeline_preflight_backlog_lines_includes_focus_and_stale_exports() -> None:
    lines = format_pipeline_preflight_backlog_lines(
        {
            "debt_summary": {
                "focus_label": "Android missing-resolution backlog",
                "focus_count": 152,
                "profile_mapping_note": "blank_resolved=159; policy_held=77",
            },
            "backlog_triage_health": {
                "needs_refresh": True,
                "refresh_exports": ["android_missing_resolution"],
            },
        }
    )

    assert any("Live curation debt focus" in line for line in lines)
    assert any("Profile mapping split" in line for line in lines)
    assert any("Stale backlog triage export" in line for line in lines)


def test_format_pipeline_preflight_backlog_lines_includes_lane_focus() -> None:
    lines = format_pipeline_preflight_backlog_lines(
        {
            "debt_summary": {
                "focus_label": "Android missing-resolution backlog",
                "focus_count": 152,
            },
            "android_missing_triage": {
                "top_lane": "vt_tail_review",
                "top_lane_count": 89,
                "lane_counts": {"vt_tail_review": 89, "package_cluster_review": 40},
            },
            "backlog_triage_health": {"needs_refresh": False, "refresh_exports": []},
        }
    )

    assert any("top lane: vt_tail_review" in line for line in lines)
    assert any("VT-tail review lane: 89" in line for line in lines)


def test_load_backlog_triage_context_with_refresh_refreshes_when_stale(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[bool] = []

    def _load(*, output_root: Path) -> dict[str, object]:
        needs_refresh = len(calls) == 0
        calls.append(True)
        return {
            "backlog_triage_health": {
                "needs_refresh": needs_refresh,
                "refresh_exports": ["android_missing_resolution"] if needs_refresh else [],
            },
            "debt_summary": {"focus_label": "Android missing-resolution backlog", "focus_count": 2},
        }

    monkeypatch.setattr(
        "obsidiandroid.diagnostics.backlog_triage_context.load_backlog_triage_context",
        _load,
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.backlog_triage_context.refresh_stale_backlog_triage_exports",
        lambda **_kwargs: (0, ["android_missing_resolution", "operator_summary"]),
    )

    context = load_backlog_triage_context_with_refresh(
        output_root=tmp_path,
        auto_refresh_stale=True,
    )

    assert len(calls) == 2
    assert context["auto_refreshed_exports"] == ["android_missing_resolution", "operator_summary"]


def test_load_backlog_triage_context_uses_local_exports(tmp_path: Path, monkeypatch) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "sample_id": 1,
                "residual_lane": "manual_review",
                "recommended_triage_action": "Manual review before classification_primary backfill.",
            }
        ]
    ).to_csv(diag / "missing_primary_label_triage_latest.csv", index=False)
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.backlog_triage_context.get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "taxonomy_signals": {
                "missing_primary_label_samples": 1,
                "missing_primary_label_active_residual_samples": 1,
                "blank_resolved_family_samples": 0,
                "unresolved_family_samples": 0,
                "policy_held_family_samples": 0,
                "family_type_conflict_count": 0,
            },
        },
    )

    context = load_backlog_triage_context(output_root=tmp_path)

    assert context["missing_primary_triage"]["row_count"] == 1
    assert context["debt_summary"]["focus_label"] == "Missing primary labels"


def test_report_backlog_debt_operator_summary_writes_files(tmp_path: Path, monkeypatch) -> None:
    import scripts.diagnostics.report_backlog_debt_operator_summary as module

    monkeypatch.setattr(
        module,
        "load_backlog_triage_context",
        lambda **_kwargs: {
            "debt_summary": {
                "focus_label": "Android missing-resolution backlog",
                "focus_count": 2,
                "rows": [
                    {
                        "label": "Android missing-resolution backlog",
                        "count": 2,
                        "detail": "freshness=current",
                    }
                ],
            },
            "priority_backlog": {"label": "Android missing-resolution triage", "row_count": 2},
            "backlog_triage_health": {"needs_refresh": False, "refresh_exports": []},
            "readiness": {"status": "ok"},
        },
    )
    monkeypatch.setattr(module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_OUT", tmp_path / "backlog_debt_operator_summary_latest.json")
    monkeypatch.setattr(module, "MD_OUT", tmp_path / "backlog_debt_operator_summary_latest.md")

    assert module.main() == 0
    payload = json.loads((tmp_path / "backlog_debt_operator_summary_latest.json").read_text(encoding="utf-8"))
    md_text = (tmp_path / "backlog_debt_operator_summary_latest.md").read_text(encoding="utf-8")
    assert payload["debt_summary"]["focus_count"] == 2
    assert "## Backlog and operator queues" in md_text
