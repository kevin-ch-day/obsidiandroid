"""Synthetic tests for joint enriched package–family sensitivity."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.reporting import enriched_package_family_sensitivity as mod
from obsidiandroid.reporting.enriched_package_family_sensitivity import (
    classify_joint_survival,
    build_headline_joint_survival,
    build_type_lane_joint_weighting,
)
from obsidiandroid.reporting.package_balanced_permission_analysis import assign_package_keys


def test_classify_joint_survival_matrix() -> None:
    assert (
        classify_joint_survival(
            identity_gate="package_identity_conflicted",
            sw=0.5,
            pwf=0.5,
            leave_pwf=0.5,
            package_delta_pp=0.0,
            family_leave_delta_pp=0.0,
        )
        == "identity_gated"
    )
    assert (
        classify_joint_survival(
            identity_gate="eligible",
            sw=0.5,
            pwf=0.48,
            leave_pwf=0.47,
            package_delta_pp=2.0,
            family_leave_delta_pp=3.0,
        )
        == "survives_joint_sensitivity"
    )
    assert (
        classify_joint_survival(
            identity_gate="eligible",
            sw=0.5,
            pwf=0.2,
            leave_pwf=0.48,
            package_delta_pp=30.0,
            family_leave_delta_pp=2.0,
        )
        == "package_balance_fragile"
    )
    assert (
        classify_joint_survival(
            identity_gate="eligible",
            sw=0.5,
            pwf=0.2,
            leave_pwf=0.1,
            package_delta_pp=30.0,
            family_leave_delta_pp=40.0,
        )
        == "jointly_fragile"
    )


def test_joint_weighting_and_headline_filter() -> None:
    rows = []
    for i in range(10):
        rows.append(
            {
                "sample_id": i,
                "package_name": f"com.clay.{i}",
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "android.permission.internet": 1,
                "android.permission.send_sms": 1 if i < 8 else 0,
            }
        )
    for i in range(10):
        rows.append(
            {
                "sample_id": 100 + i,
                "package_name": "com.arsink.same",
                "family_canonical": "ArsinkRAT",
                "type_slug": "rat",
                "android.permission.internet": 1,
                "android.permission.send_sms": 0,
            }
        )
    mem = assign_package_keys(pd.DataFrame(rows))
    weighting = build_type_lane_joint_weighting(
        membership=mem,
        permissions_by_type_lane={
            ("rat", "aosp_normal"): ["android.permission.internet", "android.permission.send_sms"]
        },
        largest_family_by_type={"rat": "ClayRat"},
        identity_gate_by_type={"rat": "eligible"},
    )
    assert not weighting.empty
    assert "joint_survival_status" in weighting.columns
    headlines = build_headline_joint_survival(weighting)
    assert (headlines.sample_weighted_prevalence >= 0.20).all()


def test_module_has_no_db_access() -> None:
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "execute_permission_query" not in src
    assert "execute_core_query" not in src
    assert "INSERT INTO" not in src.upper()
