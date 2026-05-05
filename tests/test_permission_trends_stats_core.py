"""Unit tests for permission-trends pure statistics helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from obsidiandroid.pipeline.permission_trends import stats_core


def test_js_distance_zero_for_identical() -> None:
    p = np.array([0.2, 0.3, 0.5], dtype=float)
    assert stats_core.js_distance(p, p) == pytest.approx(0.0, abs=1e-9)


def test_bh_fdr_monotone() -> None:
    p = [0.01, 0.04, 0.10]
    out = stats_core.bh_fdr(p)
    assert len(out) == 3
    assert all(0.0 <= x <= 1.0 for x in out)


def test_spearman_with_bootstrap_strong_correlation() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    y = pd.Series([1.1, 2.0, 3.2, 3.9, 5.1])
    rho, _p, _lo, _hi = stats_core.spearman_with_bootstrap_ci(x, y, bootstrap_resamples=30)
    assert rho > 0.99
