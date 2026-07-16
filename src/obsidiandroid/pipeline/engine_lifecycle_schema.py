"""Versioned names for the AV-engine readiness lifecycle.

``included_in_model_flag`` historically meant passage through the readiness
gate, not survival into a trained feature matrix.  It remains a compatibility
alias while v2 artifacts use ``readiness_eligible_flag``.
"""

from __future__ import annotations

import pandas as pd


LIFECYCLE_SCHEMA_VERSION = "2"
READINESS_FLAG = "readiness_eligible_flag"
DEPRECATED_READINESS_FLAG = "included_in_model_flag"


def readiness_mask(frame: pd.DataFrame) -> pd.Series:
    """Return the canonical readiness mask, accepting v1 artifacts safely."""
    if READINESS_FLAG in frame.columns:
        return frame[READINESS_FLAG].fillna(False).astype(bool)
    if DEPRECATED_READINESS_FLAG in frame.columns:
        return frame[DEPRECATED_READINESS_FLAG].fillna(False).astype(bool)
    return pd.Series(False, index=frame.index, dtype=bool)


def add_readiness_compatibility_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add v2 readiness names and retain a synchronized deprecated alias."""
    out = frame.copy()
    mask = readiness_mask(out)
    out[READINESS_FLAG] = mask
    out[DEPRECATED_READINESS_FLAG] = mask
    out["lifecycle_schema_version"] = LIFECYCLE_SCHEMA_VERSION
    out["deprecated_included_in_model_flag"] = True
    return out
