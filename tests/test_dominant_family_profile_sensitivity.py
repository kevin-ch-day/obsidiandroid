"""Tests for type-level dominant-family permission profile sensitivity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from obsidiandroid.pipeline.permission_trends.stats_core import js_distance
from obsidiandroid.reporting.dominant_family_profile_sensitivity import (
    build_dominant_family_type_robustness,
    classify_type_profile_robustness,
    spearman_rank_corr,
)


def test_rank_correlation_and_jsd() -> None:
    a = np.asarray([0.9, 0.5, 0.1, 0.0], dtype=float)
    b = np.asarray([0.85, 0.55, 0.12, 0.01], dtype=float)
    corr = spearman_rank_corr(a, b)
    assert corr > 0.9
    p = a / a.sum()
    q = b / b.sum()
    assert js_distance(p, q) < 0.1
    c = np.asarray([0.0, 0.0, 0.1, 0.9], dtype=float)
    assert spearman_rank_corr(a, c) < 0.0
    assert js_distance(a / a.sum(), c / c.sum()) > 0.3


def test_insufficient_support_classes() -> None:
    assert (
        classify_type_profile_robustness(
            n_families_full=3,
            n_samples_full=90,
            n_families_ex=1,
            n_samples_ex=40,
            spearman=0.9,
            jsd=0.05,
            max_abs_shift_pp=2.0,
            headline_lost=0,
        )
        == "insufficient_family_support"
    )
    assert (
        classify_type_profile_robustness(
            n_families_full=3,
            n_samples_full=90,
            n_families_ex=2,
            n_samples_ex=10,
            spearman=0.9,
            jsd=0.05,
            max_abs_shift_pp=2.0,
            headline_lost=0,
        )
        == "insufficient_sample_support"
    )


def test_exclude_largest_family_changes_profile() -> None:
    fam = pd.DataFrame(
        [
            {"family_canonical": "ClayRat", "type_slug": "rat", "family_support": 40, "permission": "android.permission.send_sms", "prevalence_pct": 95.0, "positive_count": 38},
            {"family_canonical": "ClayRat", "type_slug": "rat", "family_support": 40, "permission": "android.permission.internet", "prevalence_pct": 100.0, "positive_count": 40},
            {"family_canonical": "ArsinkRAT", "type_slug": "rat", "family_support": 30, "permission": "android.permission.send_sms", "prevalence_pct": 20.0, "positive_count": 6},
            {"family_canonical": "ArsinkRAT", "type_slug": "rat", "family_support": 30, "permission": "android.permission.internet", "prevalence_pct": 100.0, "positive_count": 30},
            {"family_canonical": "SpyNote", "type_slug": "rat", "family_support": 20, "permission": "android.permission.send_sms", "prevalence_pct": 15.0, "positive_count": 3},
            {"family_canonical": "SpyNote", "type_slug": "rat", "family_support": 20, "permission": "android.permission.internet", "prevalence_pct": 100.0, "positive_count": 20},
        ]
    )
    table = build_dominant_family_type_robustness(
        fam_prev=fam,
        type_inventory=pd.DataFrame([{"type_slug": "rat", "sample_count": 90, "active_families": 3, "largest_family_canonical": "ClayRat"}]),
        role_annotations=pd.DataFrame(),
        pairwise_headline=pd.DataFrame(),
        lane_lookup=None,
        min_samples=20,
        min_families=2,
    )
    rat_ex = table[(table.type_slug == "rat") & (table.scenario == "exclude_largest")]
    assert not rat_ex.empty
    assert rat_ex.iloc[0].excluded_families == "ClayRat"
