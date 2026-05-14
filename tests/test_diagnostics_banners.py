"""Tests for data-diagnostics banner helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.cli.menu import diagnostics_banners


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        ("—", "—"),
        (97.3109, "97.31%"),
        (100, "100.00%"),
        ("88", "88.00%"),
    ],
)
def test_format_percent_for_menu(value: object, expected: str) -> None:
    assert diagnostics_banners.format_percent_for_menu(value) == expected


def test_governed_cohort_n_prefers_q2_payload(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    assert _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2={"governed_cohort_n": 42}) == 42


def test_governed_cohort_n_falls_back_to_q1_json(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    (rdiag / "dataset_foundation_summary.json").write_text(
        '{"governed_samples": 100}',
        encoding="utf-8",
    )
    assert (
        _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2={"permission_signal_n": 1, "permission_signal_pct": 1.0})
        == 100
    )


def test_governed_cohort_n_infers_from_signal_when_no_json(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    assert (
        _governed_cohort_n_for_q2(
            rdiag=rdiag,
            gdiag=gdiag,
            q2={"permission_signal_n": 97, "permission_signal_pct": 97.0},
        )
        == 100
    )


def test_print_data_diagnostics_banner_reads_q2_from_global_when_run_json_missing(
    tmp_path: Path,
    capsys,
) -> None:
    """Q2 permission/vendor percentages should resolve from global diagnostics when run dir lacks JSON."""
    out_root = tmp_path / "output"
    rdiag = out_root / "runs" / "r1" / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (rdiag / f"split_freeze_headline_r1.csv").write_text("sample_id\n1\n", encoding="utf-8")
    (out_root / "diagnostics" / "modality_contribution_summary.json").write_text(
        '{"permission_signal_pct": 99.5, "vendor_merge_pct": 88.0, "permission_signal_n": 10, "vendor_merge_n": 9}',
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": "r1", "profile_params": {"profile_id": "demo_prof"}}),
        encoding="utf-8",
    )

    diagnostics_banners.print_data_diagnostics_banner(output_root=out_root, latest_run_id="r1")
    out = capsys.readouterr().out
    assert "99.50%" in out
    assert "88.00%" in out
    assert "Frozen profile_params (manifest)" in out
    assert "Available" in out
