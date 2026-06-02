"""Tests for ``obsidiandroid.modeling.distribution_reporter``."""

from __future__ import annotations

from collections import Counter

import pandas as pd
from config import app_config

from obsidiandroid.modeling import distribution_reporter as dr
from obsidiandroid.reporting import family_distribution_report


def test_build_distribution_df_basic() -> None:
    labels = ["A", "A", "B", "C", "C", "C"]
    df = dr.build_distribution_df(labels)
    assert list(df.columns) == ["family", "count", "percent", "support_tier"]
    assert df.loc[df["family"] == "C", "count"].iloc[0] == 3
    assert round(df["percent"].sum(), 2) == 100.00


def _sample_df_and_labels() -> tuple[pd.DataFrame, pd.Series]:
    df = pd.DataFrame({"feat": [0, 1, 2, 3, 4]}, index=[f"s{i}" for i in range(5)])
    labels = pd.Series(["A", "A", "B", "C", "C"], index=df.index)
    return df, labels


def test_apply_min_family_support_remove() -> None:
    df, labels = _sample_df_and_labels()
    f, lbl, affected, fams, detail = dr.apply_min_family_support(
        df, labels, min_support=2, group_label=None
    )
    assert len(f) == 4
    assert "B" not in lbl.values
    assert affected == 1
    assert fams == 1
    assert detail == [{"family": "B", "aligned_support": 1}]


def test_apply_min_family_support_group() -> None:
    df, labels = _sample_df_and_labels()
    f, lbl, affected, fams, detail = dr.apply_min_family_support(
        df, labels, min_support=2, group_label="other"
    )
    assert len(f) == 5
    assert (lbl == "other").sum() == 1
    assert "B" not in lbl.values
    assert affected == 1
    assert fams == 1
    assert detail == [{"family": "B", "aligned_support": 1}]


def test_generate_family_report_uses_configured_min_support() -> None:
    fam_counts = Counter({"A": 19, "B": 20, "C": 48})

    report = family_distribution_report._generate_family_report_text(  # pylint: disable=protected-access
        fam_counts,
        min_support=20,
    )

    assert "Configured Min Family Support       : 20" in report
    assert "Low-Sample Families (<20)          : 1" in report
    assert "Sufficient-Sample Families (>=20)  : 2" in report


def test_resolve_min_family_support_prefers_dataframe_attr() -> None:
    df = pd.DataFrame({"family_name": ["A", "B"]})
    df.attrs["configured_min_samples_per_family"] = 20

    out = family_distribution_report._resolve_min_family_support(df)  # pylint: disable=protected-access

    assert out == 20


def test_print_family_distribution_stats_normalizes_missing_family_names(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", False, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "debug", raising=False)
    monkeypatch.setattr(family_distribution_report.du, "print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_stat",
        lambda key, value: stats.append((str(key), value)),
    )
    monkeypatch.setattr(
        family_distribution_report,
        "_export_family_distribution_report",
        lambda *_args, **_kwargs: None,
    )

    df = pd.DataFrame({"family_name": ["Applite", None, float("nan"), "Irata", ""]})

    family_distribution_report.print_family_distribution_stats(df)

    rendered_keys = [key for key, _ in stats]
    assert "unknown" in rendered_keys
    assert "Applite" in rendered_keys
    assert "Irata" in rendered_keys


def test_print_family_distribution_stats_prefers_family_canonical(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []
    infos: list[str] = []

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", False, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "debug", raising=False)
    monkeypatch.setattr(family_distribution_report.du, "print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_info",
        lambda message: infos.append(str(message)),
    )
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_stat",
        lambda key, value: stats.append((str(key), value)),
    )
    monkeypatch.setattr(
        family_distribution_report,
        "_export_family_distribution_report",
        lambda *_args, **_kwargs: None,
    )

    df = pd.DataFrame(
        {
            "family_name": ["RawFoo", "RawBar", "RawFoo"],
            "family_canonical": ["CanonA", "CanonB", "CanonA"],
        }
    )

    family_distribution_report.print_family_distribution_stats(df)

    rendered_keys = [key for key, _ in stats]
    assert "CanonA" in rendered_keys
    assert "CanonB" in rendered_keys
    assert "RawFoo" not in rendered_keys
    assert any("family_canonical" in message for message in infos)


def test_print_family_distribution_stats_compact_benchmark_mode_summarizes(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []
    infos: list[str] = []
    warnings: list[str] = []

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(family_distribution_report.du, "print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_warning",
        lambda message: warnings.append(str(message)),
    )
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_info",
        lambda message: infos.append(str(message)),
    )
    monkeypatch.setattr(family_distribution_report.du, "print_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_stat",
        lambda key, value: stats.append((str(key), value)),
    )
    monkeypatch.setattr(
        family_distribution_report,
        "_export_family_distribution_report",
        lambda *_args, **_kwargs: None,
    )

    df = pd.DataFrame(
        {
            "family_canonical": [
                "GINP",
                "Marcher",
                "Applite", "Applite", "Applite", "Applite",
                "Irata", "Irata", "Irata", "Irata", "Irata",
                "Joker", "Joker", "Joker",
            ],
        }
    )
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["support_floor_mode"] = "benchmark_eligibility"

    family_distribution_report.print_family_distribution_stats(df)

    stat_keys = [key for key, _ in stats]
    assert "Family Leaders" in stat_keys
    assert "Benchmark-excluded" in stat_keys
    assert "-- Low-Support Families --" not in infos
    assert "-- Sufficient-Support Families --" not in infos
    assert any("excluded from supervised family benchmarking" in message for message in warnings)
    assert not any("see full report at" in message for message in infos)


def test_print_family_distribution_stats_full_mode_orders_benchmark_families_by_support(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []
    infos: list[str] = []

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", False, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "debug", raising=False)
    monkeypatch.setattr(family_distribution_report.du, "print_subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(family_distribution_report.du, "print_warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_info",
        lambda message: infos.append(str(message)),
    )
    monkeypatch.setattr(family_distribution_report.du, "print_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        family_distribution_report.du,
        "print_stat",
        lambda key, value: stats.append((str(key), value)),
    )
    monkeypatch.setattr(
        family_distribution_report,
        "_export_family_distribution_report",
        lambda *_args, **_kwargs: None,
    )

    df = pd.DataFrame(
        {
            "family_canonical": [
                "GINP",
                "Marcher",
                "Applite", "Applite", "Applite", "Applite",
                "Irata", "Irata", "Irata", "Irata", "Irata",
                "Joker", "Joker", "Joker",
            ],
        }
    )
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["support_floor_mode"] = "benchmark_eligibility"

    family_distribution_report.print_family_distribution_stats(df)

    benchmark_heading_index = infos.index("-- Benchmark-Eligible Families --")
    stat_keys = [key for key, _ in stats]
    assert "GINP" in stat_keys and "Marcher" in stat_keys
    sufficient_keys = [key for key in stat_keys if key in {"Irata", "Applite", "Joker"}]
    assert sufficient_keys == ["Irata", "Applite", "Joker"]
    assert benchmark_heading_index >= 0
