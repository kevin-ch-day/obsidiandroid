import pandas as pd
from obsidiandroid.observability.logging import logger as logger_mod

from obsidiandroid.cli.menu.diagnostics import authority_coverage
from obsidiandroid.diagnostics.family_type_authority_coverage import (
    AUTHORITY_VIEW_SELECT,
    classify_missing_candidate,
    generate_authority_coverage_artifacts,
    load_authority_df,
    temporal_feasibility_label,
)


def test_launch_family_type_authority_coverage_menu_degrades_when_view_missing(
    monkeypatch,
    tmp_path,
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
    tmp_path,
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


def test_classify_missing_candidate_generic_coarse() -> None:
    assert classify_missing_candidate("trojan", "resolved_token_coarse_behavior") == "generic_or_coarse_label"
    assert classify_missing_candidate("adware", "resolved_token_not_in_authority_taxonomy") == "generic_or_coarse_label"
    assert classify_missing_candidate("badpack", "resolved_token_not_in_authority_taxonomy") == "generic_or_coarse_label"
    assert classify_missing_candidate("kimsuky", "resolved_token_not_in_authority_taxonomy") == "generic_or_coarse_label"
    assert classify_missing_candidate("blankbot", "resolved_token_policy_held_not_family") == "generic_or_coarse_label"


def test_classify_missing_candidate_unknown_and_malformed() -> None:
    assert classify_missing_candidate("unknown", "resolved_token_unknown") == "unknown_label"
    assert classify_missing_candidate("exobotcompact.d/octo", "resolved_token_malformed_or_composite") == "malformed_or_composite"


def test_classify_missing_candidate_plausible_real_family() -> None:
    assert classify_missing_candidate("blankbot", "resolved_token_not_in_authority_taxonomy") == "plausible_real_family_candidate"


def test_temporal_feasibility_label() -> None:
    assert temporal_feasibility_label(active_years=1, row_count=159) == "single_year_only"
    assert temporal_feasibility_label(active_years=2, row_count=725) == "limited_temporal_persistence"
    assert temporal_feasibility_label(active_years=3, row_count=120) == "multi_year_candidate"
    assert temporal_feasibility_label(active_years=2, row_count=5) == "insufficient_support"


def test_load_authority_df_degrades_when_live_view_required(monkeypatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.family_type_authority_coverage.view_present",
        lambda: False,
    )
    df, source_mode, warning = load_authority_df(require_live_view=True)
    assert df.empty
    assert source_mode == "live_view_missing"
    assert "Authority view unavailable" in str(warning)


def test_generate_authority_coverage_artifacts_writes_outputs(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path / "logs"))
    monkeypatch.setattr(logger_mod.app_config, "LOG_LEVEL", "INFO", raising=False)
    monkeypatch.setattr(logger_mod.app_config, "RUNTIME_RUN_ID", "authority_diag_run", raising=False)
    monkeypatch.setattr(logger_mod.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path / "output" / "diagnostics"), raising=False)
    logger_mod.close_all_loggers()
    sample_df = pd.DataFrame(
        [
            {
                "sample_id": 1,
                "vt_first_submission_at_utc": "2025-01-01T00:00:00Z",
                "authority_bucket": "authority_family_typed",
                "resolved_family_lc": "devixor",
                "authority_gap_reason": "authority_family_typed",
                "family_slug": "devixor",
                "family_name": "Devixor",
                "type_slug": "dropper",
                "raw_vs_authority_status": "raw_conflicts_with_authority",
                "raw_classification_primary": "Trojan",
                "raw_classification_subtype": "Banker",
            },
            {
                "sample_id": 2,
                "vt_first_submission_at_utc": "2025-02-01T00:00:00Z",
                "authority_bucket": "resolved_but_no_authority_family",
                "resolved_family_lc": "blankbot",
                "authority_gap_reason": "resolved_token_not_in_authority_taxonomy",
                "family_slug": None,
                "family_name": None,
                "type_slug": None,
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
            },
            {
                "sample_id": 4,
                "vt_first_submission_at_utc": "2025-03-01T00:00:00Z",
                "authority_bucket": "resolved_but_no_authority_family",
                "resolved_family_lc": "adware",
                "authority_gap_reason": "resolved_token_not_in_authority_taxonomy",
                "family_slug": None,
                "family_name": None,
                "type_slug": None,
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
            },
            {
                "sample_id": 3,
                "vt_first_submission_at_utc": "2024-01-01T00:00:00Z",
                "authority_bucket": "authority_family_unknown_type",
                "resolved_family_lc": "hiddenad",
                "authority_gap_reason": "authority_family_missing_type",
                "family_slug": "hiddenad",
                "family_name": "HiddenAd",
                "type_slug": "unknown",
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
            },
        ]
    )
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.family_type_authority_coverage.load_authority_df",
        lambda require_live_view=False: (sample_df, "live_view", None),
    )
    bundle = generate_authority_coverage_artifacts(
        md_path=tmp_path / "out.md",
        missing_out=tmp_path / "missing.csv",
        unknown_type_out=tmp_path / "unknown.csv",
        year_type_out=tmp_path / "year_type.csv",
        require_live_view=True,
    )
    assert bundle["ok"] is True
    assert bundle["source_mode"] == "live_view"
    assert bundle["md_path"].exists()
    assert bundle["missing_out"].exists()
    assert bundle["unknown_type_out"].exists()
    assert bundle["year_type_out"].exists()
    md_text = bundle["md_path"].read_text(encoding="utf-8")
    assert "## True Missing Authority-Family Candidates" in md_text
    assert "## Policy-Held Generic/Coarse Token Residue" in md_text
    label_text = (tmp_path / "logs" / "runtime" / "authority_diag_run" / "label_authority_alerts.log").read_text(
        encoding="utf-8"
    )
    temporal_text = (
        tmp_path / "logs" / "runtime" / "authority_diag_run" / "temporal_readiness_alerts.log"
    ).read_text(encoding="utf-8")
    assert "label_authority_coverage_summary" in label_text
    assert "missing_family_authority_candidate" in label_text
    assert "raw_authority_conflict" in label_text
    assert "temporal_readiness_summary" in temporal_text
    assert "type_year_concentration_alert" in temporal_text
    assert "temporal_split_caveat" in temporal_text


def test_authority_view_select_filters_inactive_taxonomy_rows() -> None:
    assert "AND fam.is_active = 1" in AUTHORITY_VIEW_SELECT
    assert "AND alias.is_active = 1" in AUTHORITY_VIEW_SELECT
    assert "LEFT JOIN vendor_label_generic_token_fact AS gt" in AUTHORITY_VIEW_SELECT
    assert "resolved_token_policy_held_not_family" in AUTHORITY_VIEW_SELECT
    assert "known_legit_package_identity_review" in AUTHORITY_VIEW_SELECT
    assert "known_legit_package_identity" in AUTHORITY_VIEW_SELECT
    assert "low_context_provenance_review" in AUTHORITY_VIEW_SELECT
    assert "low_context_blank_package_no_family_signal" in AUTHORITY_VIEW_SELECT
    assert "pua_or_provenance_review" in AUTHORITY_VIEW_SELECT
    assert "pua_without_family_signal" in AUTHORITY_VIEW_SELECT
    assert "vt_tail_policy_hold_review" in AUTHORITY_VIEW_SELECT
    assert "vt_tail_token_policy_held_not_family" in AUTHORITY_VIEW_SELECT
    assert "typed_malware_no_family_signal_review" in AUTHORITY_VIEW_SELECT
    assert "coarse_trojan_banker_without_family_signal" in AUTHORITY_VIEW_SELECT
    assert "low_signal_singleton_provenance_review" in AUTHORITY_VIEW_SELECT
    assert "blank_family_singleton_no_signal" in AUTHORITY_VIEW_SELECT


def test_authority_view_fallback_sql_drops_inactive_filters_when_columns_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "obsidiandroid.diagnostics.family_type_authority_coverage._table_has_column",
        lambda table_name, column_name: False,
    )
    from obsidiandroid.diagnostics.family_type_authority_coverage import _authority_view_fallback_sql

    fallback_sql = _authority_view_fallback_sql()
    assert "AND fam.is_active = 1" not in fallback_sql
    assert "AND alias.is_active = 1" not in fallback_sql
