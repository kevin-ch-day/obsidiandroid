"""Config wiring and normalization helpers for ML Readiness Score."""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from config import app_config

from obsidiandroid.evaluation import engine_scoring_summary as ess


def test_effective_readiness_weights_partial_override_renormalizes(monkeypatch):
    monkeypatch.setattr(
        app_config,
        "ENGINE_READINESS_SCORE_WEIGHTS",
        {"malicious_pct": 0.9, "coverage_pct": 0.9},  # threat_signal keeps DEFAULT
        raising=False,
    )
    w = ess._effective_readiness_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w.keys()) == {"coverage_pct", "malicious_pct", "threat_signal_score"}
    assert w["malicious_pct"] > w["threat_signal_score"]


def test_effective_readiness_weights_empty_dict_uses_defaults(monkeypatch):
    monkeypatch.setattr(app_config, "ENGINE_READINESS_SCORE_WEIGHTS", {}, raising=False)
    assert ess._effective_readiness_weights() == ess.DEFAULT_READINESS_WEIGHTS


def test_percentile_rank_ordering_and_bounds():
    ser = pd.Series([3.0, 1.0, 2.0])
    pr = ess._percentile_rank_scale(ser)
    assert pr.min() >= 0 and pr.max() <= 1
    # average-rank percentiles order with values
    assert pr.iloc[1] < pr.iloc[2] < pr.iloc[0]


def test_export_summary_log_compact_skips_table_and_emits_single_info(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        ess,
        "_resolve_summary_export_paths",
        lambda: (tmp_path / "engine_scoring_summary_log.txt", tmp_path / "engine_scoring_summary.csv"),
    )
    captured: list[str] = []
    monkeypatch.setattr(ess.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(ess.du, "print_table", lambda *_a, **_k: captured.append("table"))

    df = pd.DataFrame(
        {
            "engine_name": ["a", "b", "c", "d", "e", "f"],
            "ML Readiness Score": [99.0, 97.0, 95.0, 93.0, 91.0, 89.0],
            "Tier Label": ["Tier 1 (High)"] * 6,
            "contributor_flag": [1, 1, 1, 1, 1, 1],
        }
    )
    ess._export_summary_log(df)

    assert "table" not in captured
    assert any("Top engines by ML Readiness Score" in msg for msg in captured)


def test_log_summary_stats_compact_skips_statistical_ranges(monkeypatch):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    calls: list[str] = []
    monkeypatch.setattr(ess.du, "print_metric_summary", lambda *_a, **_k: calls.append("metric_summary"))
    monkeypatch.setattr(ess.du, "print_statistical_range", lambda *_a, **_k: calls.append("range"))
    monkeypatch.setattr(ess.du, "print_tier_distribution", lambda *_a, **_k: calls.append("tier_distribution"))
    monkeypatch.setattr(ess.du, "print_subheader", lambda *_a, **_k: None)

    df = pd.DataFrame(
        {
            "ML Readiness Score": [10.0, 20.0, 30.0],
            "malicious_pct": [1.0, 2.0, 3.0],
            "coverage_pct": [4.0, 5.0, 6.0],
            "threat_signal_score": [7.0, 8.0, 9.0],
            "Detection Tier": [1, 2, 3],
            "Tier Label": ["Tier 1 (High)", "Tier 2 (Moderate)", "Tier 3 (Low)"],
            "iqr_flag": [0, 0, 0],
        }
    )
    ess._log_summary_stats(df)

    assert calls == ["metric_summary", "tier_distribution"]


def test_print_summary_context_distinguishes_db_and_cohort_engine_universes(monkeypatch, tmp_path: Path):
    captured_stats: list[tuple[str, object]] = []
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_OBSERVED", 93, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_CANONICAL", 93, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", 56, raising=False)
    monkeypatch.setattr(ess.du, "print_subheader", lambda *_a, **_k: None)
    monkeypatch.setattr(ess.du, "print_stat", lambda label, value, *_a, **_k: captured_stats.append((str(label), value)))
    monkeypatch.setattr(ess.du, "format_console_path", lambda path: f"obsidiandroid/{Path(path).name}")

    engine_df = pd.DataFrame({"engine_name": [f"e{i}" for i in range(102)]})
    summary_df = pd.DataFrame({"engine_name": [f"e{i}" for i in range(102)]})

    ess._print_summary_context(
        engine_df=engine_df,
        summary_df=summary_df,
        drift_df=None,
        export_paths={"csv_path": str(tmp_path / "engine_scoring_summary.csv")},
    )

    stat_map = dict(captured_stats)
    assert stat_map["Source"] == "DB verdict-table summary"
    assert "db_verdict_table=102" in str(stat_map["Engine Universe"])
    assert "cohort_observed=93" in str(stat_map["Engine Universe"])
    assert "cohort_canonical=93" in str(stat_map["Engine Universe"])
    assert "included_after_gating=56" in str(stat_map["Engine Universe"])
    assert stat_map["Export"] == "obsidiandroid/engine_scoring_summary.csv"


def test_build_engine_metadata_drift_df_surfaces_metadata_only_and_verdict_only(monkeypatch):
    monkeypatch.setattr(
        ess.verdict_contracts,
        "fetch_vendor_verdict_columns",
        lambda: ["sample_id", "engine_a", "engine_b"],
    )
    monkeypatch.setattr(
        ess.verdict_contracts,
        "fetch_vendor_engine_flags",
        lambda: pd.DataFrame(
            [
                {"vendor_key": "engine_a", "is_engine_active": 1, "is_trusted_vendor": 1},
                {"vendor_key": "engine_c", "is_engine_active": 1, "is_trusted_vendor": 0},
            ]
        ),
    )

    drift_df = ess._build_engine_metadata_drift_df()
    status_map = dict(zip(drift_df["vendor_key"], drift_df["drift_status"]))

    assert status_map["engine_a"] == "metadata_and_verdict"
    assert status_map["engine_b"] == "verdict_only"
    assert status_map["engine_c"] == "metadata_only"
    suggestion_map = dict(zip(drift_df["vendor_key"], drift_df["likely_current_vendor_key"]))
    basis_map = dict(zip(drift_df["vendor_key"], drift_df["suggestion_basis"]))
    assert suggestion_map["engine_c"] == ""
    assert basis_map["engine_c"] == ""


def test_build_engine_metadata_drift_df_adds_legacy_alias_suggestions(monkeypatch):
    monkeypatch.setattr(
        ess.verdict_contracts,
        "fetch_vendor_verdict_columns",
        lambda: ["sample_id", "webroot", "cyren"],
    )
    monkeypatch.setattr(
        ess.verdict_contracts,
        "fetch_vendor_engine_flags",
        lambda: pd.DataFrame(
            [
                {"vendor_key": "webrootd", "is_engine_active": 1, "is_trusted_vendor": 1},
                {"vendor_key": "cyrencloud", "is_engine_active": 1, "is_trusted_vendor": 0},
                {"vendor_key": "nod32", "is_engine_active": 1, "is_trusted_vendor": 0},
            ]
        ),
    )

    drift_df = ess._build_engine_metadata_drift_df()
    rows = drift_df.set_index("vendor_key").to_dict(orient="index")

    assert rows["webrootd"]["drift_status"] == "metadata_only"
    assert rows["webrootd"]["likely_current_vendor_key"] == "webroot"
    assert rows["webrootd"]["suggestion_basis"] == "legacy_metadata_alias_to_current_vt_prefix"
    assert rows["cyrencloud"]["likely_current_vendor_key"] == "cyren"
    assert rows["nod32"]["likely_current_vendor_key"] == "nod32"
    assert rows["nod32"]["suggestion_basis"] == "current_vt_documented_prefix_without_verdict_column"
    assert int(rows["nod32"]["vt_current_prefix_flag"]) == 1


def test_export_summary_log_writes_metadata_drift_csv(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        ess,
        "_resolve_summary_export_paths",
        lambda: (tmp_path / "engine_scoring_summary_log.txt", tmp_path / "engine_scoring_summary.csv"),
    )
    monkeypatch.setattr(ess.du, "print_info", lambda *_a, **_k: None)
    monkeypatch.setattr(ess.du, "print_table", lambda *_a, **_k: None)
    monkeypatch.setattr(ess.du, "format_console_path", lambda path: f"obsidiandroid/{Path(path).name}")

    df = pd.DataFrame(
        {
            "engine_name": ["a", "b"],
            "ML Readiness Score": [99.0, 97.0],
            "Tier Label": ["Tier 1 (High)", "Tier 1 (High)"],
            "contributor_flag": [1, 1],
        }
    )
    drift_df = pd.DataFrame(
        [
            {"vendor_key": "engine_a", "drift_status": "metadata_and_verdict"},
            {"vendor_key": "engine_c", "drift_status": "metadata_only"},
        ]
    )

    export_paths = ess._export_summary_log(df, drift_df=drift_df)

    drift_path = tmp_path / "engine_metadata_drift.csv"
    assert drift_path.is_file()
    assert export_paths["metadata_drift_path"] == str(drift_path)


def test_resolve_summary_export_paths_uses_slot_run_root(monkeypatch, tmp_path: Path):
    run_id = "20260604T104155Z__2df6cf"
    slot_root = tmp_path / "output" / "runs" / "allcurrent_diagnostic"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(slot_root), raising=False)

    log_path, csv_path = ess._resolve_summary_export_paths()

    assert log_path == slot_root / "diagnostics" / "engine_scoring_summary_log.txt"


def test_export_summary_log_does_not_create_sibling_run_id_tree_for_slot_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_id = "20260604T104155Z__2df6cf"
    slot_root = tmp_path / "output" / "runs" / "allcurrent_diagnostic"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(slot_root), raising=False)
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(ess.du, "print_info", lambda *_a, **_k: None)
    monkeypatch.setattr(ess.du, "print_table", lambda *_a, **_k: None)

    df = pd.DataFrame(
        {
            "engine_name": ["a", "b"],
            "ML Readiness Score": [99.0, 97.0],
            "Tier Label": ["Tier 1 (High)", "Tier 1 (High)"],
            "contributor_flag": [1, 1],
        }
    )

    export_paths = ess._export_summary_log(df)

    assert Path(export_paths["log_path"]).parent == slot_root / "diagnostics"
    assert Path(export_paths["csv_path"]).parent == slot_root / "diagnostics"
    assert not (tmp_path / "output" / "runs" / run_id / "diagnostics").exists()
    assert not (tmp_path / "output" / "runs" / run_id / "diagnostics").exists()
