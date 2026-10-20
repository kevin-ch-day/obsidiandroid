"""Opt-in training-pool requirement for both AV-detection and permission evidence.

Profiles enable it with ``cohort_gates.require_vendor_and_permission: true``
(``RUNTIME_REQUIRE_BOTH_MODALITIES``). Vendor presence means the sample has AV
detection data (a row in the run's binary/enriched AV matrix), not parsed vendor
label columns. Permission presence means any positive permission feature in the
run's gated permission frame. Both sets are cohort-level, so headline and
ablation pools are filtered identically, and the filter runs before the family
support floor so families are counted after the requirement.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from config import app_config

# Legacy token/count columns and source-aware (V2) token columns. A positive value
# in any of them is permission evidence.
_PERMISSION_TOKEN_PREFIXES = (
    "perm__",
    "perm_grp__",
    "perm_provider__",
    "perm_manifest__",
    "perm_provider_unresolved__",
)
# Source-aware status columns that assert evidence exists. Others such as
# ``perm_status__provider_missing`` are 1 when evidence is absent.
_PERMISSION_PRESENCE_STATUS = frozenset(
    {
        "perm_status__has_provider_report",
        "perm_status__has_manifest_parse",
        "perm_status__provider_reported_unresolved_count",
    }
)


def _int_ids(values: Any) -> set[int]:
    ids = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    return set(ids.astype("int64").tolist())


def permission_presence_columns(columns: Iterable[Any]) -> list[Any]:
    """Columns whose positive value means a sample has permission evidence."""
    return [
        c
        for c in columns
        if str(c).startswith(_PERMISSION_TOKEN_PREFIXES) or str(c) in _PERMISSION_PRESENCE_STATUS
    ]


def av_detection_sample_ids(pipeline_results: dict[str, Any] | None) -> set[int] | None:
    """Sample IDs with AV detection rows, or ``None`` when no AV matrix was built.

    Prefers the enriched matrix, the same membership the modality coverage audit
    reports as ``in_av_enrichment_matrix``.
    """
    for key in ("enriched_matrix", "binary_matrix"):
        frame = (pipeline_results or {}).get(key)
        if isinstance(frame, pd.DataFrame) and "sample_id" in frame.columns:
            return _int_ids(frame["sample_id"])
    return None


def permission_present_sample_ids(permission_features_df: pd.DataFrame | None) -> set[int] | None:
    """Sample IDs with permission evidence (see :func:`permission_presence_columns`)."""
    if not isinstance(permission_features_df, pd.DataFrame) or "sample_id" not in permission_features_df.columns:
        return None
    cols = permission_presence_columns(permission_features_df.columns)
    if not cols:
        return set()
    values = permission_features_df[cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    return _int_ids(permission_features_df.loc[(values > 0).any(axis=1), "sample_id"])


def apply_modality_requirement(
    features_df: pd.DataFrame, labels: pd.Series
) -> tuple[pd.DataFrame, pd.Series, int]:
    """Drop training rows lacking AV detections or permissions when the profile requires both.

    Returns the inputs unchanged (and 0 dropped) when the requirement is off.
    Fails closed when it is on but either evidence set was not recorded.
    """
    if not bool(getattr(app_config, "RUNTIME_REQUIRE_BOTH_MODALITIES", False)):
        return features_df, labels, 0
    av_ids = getattr(app_config, "RUNTIME_AV_DETECTION_SAMPLE_IDS", None)
    perm_ids = getattr(app_config, "RUNTIME_PERMISSION_PRESENT_SAMPLE_IDS", None)
    if av_ids is None:
        raise ValueError("[MODALITY] require_vendor_and_permission needs the run's AV detection sample IDs.")
    if perm_ids is None:
        raise ValueError("[MODALITY] require_vendor_and_permission needs the run's permission sample IDs.")
    keep_ids = set(av_ids) & set(perm_ids)
    row_ids = pd.to_numeric(pd.Index(features_df.index), errors="coerce")
    keep = pd.Index(row_ids).isin(list(keep_ids))
    dropped = int((~keep).sum())
    return features_df.loc[keep], labels.loc[keep], dropped
