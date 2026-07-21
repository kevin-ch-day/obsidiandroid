"""Synthetic tests for robust type-contrast classification."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.reporting import robust_type_contrast as mod
from obsidiandroid.reporting.robust_type_contrast import classify_contrast


def test_classify_robust_discriminator() -> None:
    assert (
        classify_contrast(
            sw_delta_pp=30.0,
            pwf_delta_pp=28.0,
            leave_delta_pp=25.0,
            sw_a=0.8,
            sw_b=0.5,
        )
        == "robust_discriminator"
    )


def test_classify_contrast_fragile_and_shared() -> None:
    assert (
        classify_contrast(
            sw_delta_pp=25.0,
            pwf_delta_pp=5.0,
            leave_delta_pp=4.0,
            sw_a=0.9,
            sw_b=0.65,
        )
        == "contrast_fragile"
    )
    assert (
        classify_contrast(
            sw_delta_pp=2.0,
            pwf_delta_pp=1.0,
            leave_delta_pp=1.5,
            sw_a=0.95,
            sw_b=0.93,
        )
        == "shared_background"
    )


def test_sign_flip_is_fragile() -> None:
    assert (
        classify_contrast(
            sw_delta_pp=20.0,
            pwf_delta_pp=-18.0,
            leave_delta_pp=-16.0,
            sw_a=0.7,
            sw_b=0.5,
        )
        == "contrast_fragile"
    )


def test_module_has_no_db_access() -> None:
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "execute_permission_query" not in src
    assert "execute_core_query" not in src
    assert "INSERT INTO" not in src.upper()
