"""Synthetic tests for package-balance attribution."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.reporting import package_balance_attribution as mod
from obsidiandroid.reporting.package_balance_attribution import (
    build_banker_collision_deep_dive,
    build_rat_family_leaveout_attribution,
    build_source_batch_package_coupling,
)
from obsidiandroid.reporting.package_balanced_permission_analysis import assign_package_keys


def _mini_membership() -> pd.DataFrame:
    rows = []
    # ClayRat: diverse packages, permission mostly on
    for i in range(20):
        rows.append(
            {
                "sample_id": i,
                "package_name": f"com.clay.{i}",
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "source_batch_label": "zimperium",
                "perm_a": 1,
                "perm_b": 1 if i % 2 == 0 else 0,
            }
        )
    # ArsinkRAT: repeated packages
    for i in range(20):
        rows.append(
            {
                "sample_id": 100 + i,
                "package_name": f"com.arsink.{i % 4}",
                "family_canonical": "ArsinkRAT",
                "type_slug": "rat",
                "source_batch_label": "other",
                "perm_a": 1,
                "perm_b": 1,
            }
        )
    # Tiny concentrated RAT
    for i in range(6):
        rows.append(
            {
                "sample_id": 200 + i,
                "package_name": "com.xrat.only",
                "family_canonical": "XRat",
                "type_slug": "rat",
                "source_batch_label": "other",
                "perm_a": 0,
                "perm_b": 1,
            }
        )
    frame = pd.DataFrame(rows)
    return assign_package_keys(frame)


def test_rat_leaveout_attributes_concentrated_families() -> None:
    mem = _mini_membership()
    fam_conc = pd.DataFrame(
        [
            {"family_canonical": "ClayRat", "concentration_state": "broad_package_diversity"},
            {"family_canonical": "ArsinkRAT", "concentration_state": "moderate_package_concentration"},
            {"family_canonical": "XRat", "concentration_state": "single_package_dominated"},
        ]
    )
    attr = build_rat_family_leaveout_attribution(
        membership=mem,
        permissions=["perm_a", "perm_b"],
        family_concentration=fam_conc,
    )
    assert not attr.empty
    full_pwf = attr[attr.scenario == "full_package_within_family_balanced"].iloc[0]
    leave_x = attr[attr.scenario == "leave_concentrated_rat_families_package_within_family"].iloc[0]
    assert pd.notna(full_pwf.max_abs_prevalence_shift_pp)
    assert "XRat" in str(leave_x.excluded_families)


def test_banker_collision_deep_dive_no_raw_packages() -> None:
    collisions = pd.DataFrame(
        [
            {
                "package_key_hash": "abc",
                "collision_class": "cross_family_collision",
                "sample_count": 5,
                "sha_count": 5,
                "family_count": 2,
                "type_count": 1,
                "batch_count": 1,
                "affected_families": "Godfather|Applite",
                "affected_types": "banker",
            }
        ]
    )
    mem = assign_package_keys(
        pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "package_name": "com.bank",
                    "family_canonical": "Godfather",
                    "type_slug": "banker",
                    "source_batch_label": "b",
                }
            ]
        )
    )
    # Force hash match for the synthetic collision
    mem["package_key_hash"] = "abc"
    dive = build_banker_collision_deep_dive(collisions=collisions, membership=mem)
    assert len(dive) == 1
    assert bool(dive.iloc[0].same_type_multi_family)
    assert "com.bank" not in dive.to_csv(index=False)


def test_source_batch_package_coupling() -> None:
    mem = _mini_membership()
    coup = build_source_batch_package_coupling(membership=mem, families=["ClayRat", "ArsinkRAT"])
    clay = coup[coup.family_canonical == "ClayRat"].iloc[0]
    assert clay.largest_source_batch_label == "zimperium"
    assert bool(clay.batch_dominates_samples) is True


def test_module_boundaries() -> None:
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "execute_permission_query" not in src
    assert "execute_core_query" not in src
    assert "INSERT INTO" not in src.upper()
