"""Unit coverage for the read-only taxonomy type lifecycle review queue."""

from __future__ import annotations

import obsidiandroid.database.db_cohort_readiness as db_cohort_readiness
from scripts.diagnostics import report_taxonomy_type_lifecycle_gaps


def test_fetch_active_family_inactive_type_gaps_is_read_only_and_preserves_counts(monkeypatch) -> None:
    """The query should expose, not modify, retired-type mapping contradictions."""
    captured: dict[str, str] = {}

    def fake_execute(query, **_kwargs):
        captured["query"] = query
        return (
            [
                "family_id",
                "family_slug",
                "family_status",
                "primary_type_id",
                "type_slug",
                "authority_sample_count",
            ],
            [(85, "smsworm", "active", 10, "worm", 8)],
        )

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_execute)

    rows = db_cohort_readiness.fetch_active_family_inactive_type_gaps()

    assert rows == [
        {
            "family_id": 85,
            "family_slug": "smsworm",
            "family_status": "active",
            "primary_type_id": 10,
            "type_slug": "worm",
            "authority_sample_count": 8,
        }
    ]
    assert "SELECT" in captured["query"]
    assert "t.is_active = 0" in captured["query"]
    assert "UPDATE" not in captured["query"]


def test_lifecycle_report_marks_rows_for_review_only(monkeypatch) -> None:
    """Export rows must carry a non-mutating, evidence-first recommendation."""
    monkeypatch.setattr(
        report_taxonomy_type_lifecycle_gaps,
        "fetch_active_family_inactive_type_gaps",
        lambda: [
            {
                "family_id": 80,
                "family_slug": "kuguo",
                "family_status": "active",
                "primary_type_id": 19,
                "type_slug": "pua",
                "authority_sample_count": 670,
            }
        ],
    )

    report = report_taxonomy_type_lifecycle_gaps.build_report()

    assert report.loc[0, "family_slug"] == "kuguo"
    assert report.loc[0, "authority_sample_count"] == 670
    assert "No automatic change" in report.loc[0, "recommended_action"]


def test_readiness_lifecycle_query_avoids_authority_view_expansion(monkeypatch) -> None:
    """Preflight warning should stay quick while the full report counts impact."""
    captured: dict[str, str] = {}

    def fake_execute(query, **_kwargs):
        captured["query"] = query
        return (
            [
                "family_id",
                "family_slug",
                "family_status",
                "primary_type_id",
                "type_slug",
                "authority_sample_count",
            ],
            [(80, "kuguo", "active", 19, "pua", 0)],
        )

    monkeypatch.setattr(db_cohort_readiness.db_engine, "execute_query", fake_execute)

    rows = db_cohort_readiness.fetch_active_family_inactive_type_gaps(
        include_authority_sample_count=False,
    )

    assert rows[0]["authority_sample_count"] == 0
    assert "v_android_sample_family_type_authority" not in captured["query"]
