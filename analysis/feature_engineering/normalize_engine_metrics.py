"""Deprecated compatibility shim for engine metric preparation.

Use ``analysis.feature_engineering.prepare_engine_metrics.prepare_engine_metrics_for_ml``
as the canonical implementation.
"""

from __future__ import annotations

import warnings
import pandas as pd

from .prepare_engine_metrics import prepare_engine_metrics_for_ml as _canonical_prepare


def prepare_engine_metrics_for_ml(engine_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Backward-compatible wrapper that delegates to canonical implementation."""
    warnings.warn(
        "analysis.feature_engineering.normalize_engine_metrics is deprecated; "
        "use analysis.feature_engineering.prepare_engine_metrics instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _canonical_prepare(engine_df=engine_df, verbose=verbose)
