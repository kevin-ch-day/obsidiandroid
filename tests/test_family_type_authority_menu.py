from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.cli.menu.diagnostics import authority_coverage


def test_launch_family_type_authority_coverage_menu_degrades_when_view_missing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        authority_coverage,
        "generate_authority_coverage_artifacts",
        lambda **_kwargs: {
            "ok": False,
            "source_mode": "live_view_missing",
            "warning": "Authority view unavailable; run `database/sql/view_android_sample_family_type_authority.sql` against Erebus before using this diagnostic.",
            "df": pd.DataFrame(),
        },
    )

    result = authority_coverage.launch_family_type_authority_coverage_menu(output_root=tmp_path / "output")
    out = capsys.readouterr().out

    assert result == 1
    assert "Family/type authority coverage" in out
    assert "Authority view unavailable" in out
    assert "view_android_sample_family_type_authority.sql" in out


def test_launch_family_type_authority_coverage_menu_renders_sections(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        authority_coverage,
        "generate_authority_coverage_artifacts",
        lambda **_kwargs: {
            "ok": True,
            "source_mode": "live_view",
            "warning": None,
            "df": pd.DataFrame({"sample_id": [1, 2]}),
            "bucket_df": pd.DataFrame(
                [{"authority_bucket": "authority_family_typed", "row_count": 2, "row_pct": 100.0, "family_count": 1}]
            ),
            "year_bucket_df": pd.DataFrame(
                [{"sample_year": 2025, "authority_bucket": "authority_family_typed", "row_count": 2}]
            ),
            "missing_df": pd.DataFrame(
                [{"resolved_family_lc": "blankbot", "authority_gap_reason": "resolved_token_not_in_authority_taxonomy", "candidate_kind": "plausible_real_family_candidate", "row_count": 9}]
            ),
            "unknown_type_df": pd.DataFrame(
                [{"family_slug": "hiddenad", "family_name": "HiddenAd", "row_count": 35, "active_years": 2}]
            ),
            "conflict_summary_df": pd.DataFrame(
                [{"raw_vs_authority_status": "raw_conflicts_with_authority", "row_count": 725}]
            ),
            "top_conflicts_df": pd.DataFrame(
                [{"family_slug": "devixor", "type_slug": "dropper", "raw_classification_primary": "Trojan", "raw_classification_subtype": "Banker", "row_count": 725}]
            ),
            "concentration_df": pd.DataFrame(
                [{"family_slug": "devixor", "type_slug": "dropper", "row_count": 725, "active_years": 2, "min_year": 2025, "max_year": 2026, "temporal_feasibility": "limited_temporal_persistence"}]
            ),
            "md_path": tmp_path / "output" / "diagnostics" / "family_type_authority_coverage_latest.md",
            "missing_out": tmp_path / "output" / "diagnostics" / "family_type_authority_missing_candidates_latest.csv",
            "unknown_type_out": tmp_path / "output" / "diagnostics" / "family_type_authority_unknown_type_latest.csv",
            "year_type_out": tmp_path / "output" / "diagnostics" / "family_type_authority_year_type_latest.csv",
        },
    )

    result = authority_coverage.launch_family_type_authority_coverage_menu(output_root=tmp_path / "output")
    out = capsys.readouterr().out

    assert result == 0
    assert "Source mode" in out
    out_lower = out.lower()
    assert "coverage summary" in out_lower
    assert "raw vs authority" in out_lower
    assert "review next" in out_lower
    assert "top conflicts" in out_lower
    assert "temporal concentration" in out_lower
    assert "temporal split caveats:" in out_lower
    assert "diagnostics" in out_lower
    assert "Missing authority-family candidates:" in out
    assert "Unknown-type families:" in out
    assert "devixor" in out
