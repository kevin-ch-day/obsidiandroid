"""Canonical cohort family/type count semantics (offline-safe).

Ambiguous phrases such as ``visible families`` are forbidden in new operator
copy when the treatment of ``unknown`` is unclear. Prefer the metric names in
this module.

Evidence from the live all-current diagnostic prepared cohort:

- known/governed family identities (non-blank, non-``unknown``): 206
- observed family labels after blank→``unknown``: 207
- known/governed type identities (excluding ``unknown``): 14
- observed ``type_slug`` values including ``unknown``: 15

Callers that only have a prepared-cohort dataframe (analysis snapshot / samples
frame) can compute these offline without database access.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

COHORT_COUNT_CONTRACT_VERSION = "1.0.0"

# Blank / null tokens that are *not* governed identities.
_EMPTY_TOKENS = frozenset({"", "nan", "none", "null", "(null)", "n/a", "<na>"})
_UNKNOWN_TOKEN = "unknown"

METRIC_GOVERNED_KNOWN_FAMILY_COUNT = "governed_known_family_count"
METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN = (
    "observed_family_label_count_including_unknown"
)
METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT = "unknown_family_sample_count"
METRIC_GOVERNED_KNOWN_TYPE_COUNT = "governed_known_type_count"
METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN = (
    "observed_type_slug_count_including_unknown"
)
METRIC_UNKNOWN_TYPE_SAMPLE_COUNT = "unknown_type_sample_count"


def _clean_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    lower = text.str.lower()
    return text.mask(lower.isin(_EMPTY_TOKENS), "")


def normalize_family_labels_including_unknown(series: pd.Series) -> pd.Series:
    """Map blank/null family labels to ``unknown``; keep other tokens as-is."""
    cleaned = _clean_series(series)
    out = cleaned.mask(cleaned.eq(""), _UNKNOWN_TOKEN)
    # Literal unknown stays unknown (case-normalized for identity counting).
    lower = out.str.lower()
    return out.mask(lower.eq(_UNKNOWN_TOKEN), _UNKNOWN_TOKEN)


def normalize_type_slugs_including_unknown(series: pd.Series) -> pd.Series:
    """Map blank/null type_slug to ``unknown``; keep other tokens as-is."""
    return normalize_family_labels_including_unknown(series)


def compute_cohort_identity_counts(
    frame: pd.DataFrame,
    *,
    family_col: str = "family_canonical",
    type_col: str = "type_slug",
    source_surface: str = "prepared_cohort",
    authority_stage: str = "prepared_cohort_before_train_split",
) -> dict[str, Any]:
    """Return canonical family/type identity metrics for a prepared cohort frame.

    Parameters
    ----------
    frame:
        Prepared cohort rows (e.g. analysis snapshot or samples_df).
    family_col / type_col:
        Column names present on ``frame``.
    source_surface / authority_stage:
        Provenance labels recorded on each metric for operator/report copy.
    """
    metrics: dict[str, dict[str, Any]] = {}

    if family_col in frame.columns:
        cleaned = _clean_series(frame[family_col])
        observed = normalize_family_labels_including_unknown(frame[family_col])
        known_mask = cleaned.ne("") & cleaned.str.lower().ne(_UNKNOWN_TOKEN)
        known_count = int(cleaned[known_mask].nunique())
        observed_count = int(observed.nunique())
        unknown_samples = int((observed.str.lower() == _UNKNOWN_TOKEN).sum())
        metrics[METRIC_GOVERNED_KNOWN_FAMILY_COUNT] = _metric(
            name=METRIC_GOVERNED_KNOWN_FAMILY_COUNT,
            value=known_count,
            includes_unknown=False,
            authority_stage=authority_stage,
            filtering_stage="exclude_blank_and_unknown_family_labels",
            source_surface=source_surface,
            field=family_col,
            label="Known governed families",
            explanation=(
                "Distinct non-blank family_canonical identities after excluding "
                "the unknown/blank bucket."
            ),
        )
        metrics[METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN] = _metric(
            name=METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN,
            value=observed_count,
            includes_unknown=True,
            authority_stage=authority_stage,
            filtering_stage="blank_normalized_to_unknown",
            source_surface=source_surface,
            field=family_col,
            label="Observed family labels (including unknown)",
            explanation=(
                "Distinct family labels after mapping blank/null to unknown. "
                "Equals known governed families plus the unknown bucket when present."
            ),
        )
        metrics[METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT] = _metric(
            name=METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT,
            value=unknown_samples,
            includes_unknown=True,
            authority_stage=authority_stage,
            filtering_stage="blank_normalized_to_unknown",
            source_surface=source_surface,
            field=family_col,
            label="Unknown/blank family samples",
            explanation="Sample rows whose family label is blank/null or unknown.",
        )
    else:
        for name, label in (
            (METRIC_GOVERNED_KNOWN_FAMILY_COUNT, "Known governed families"),
            (
                METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN,
                "Observed family labels (including unknown)",
            ),
            (METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT, "Unknown/blank family samples"),
        ):
            metrics[name] = _metric(
                name=name,
                value=0,
                includes_unknown=name != METRIC_GOVERNED_KNOWN_FAMILY_COUNT,
                authority_stage=authority_stage,
                filtering_stage="missing_family_column",
                source_surface=source_surface,
                field=family_col,
                label=label,
                explanation=f"Column {family_col!r} absent on source frame.",
            )

    if type_col in frame.columns:
        cleaned = _clean_series(frame[type_col])
        observed = normalize_type_slugs_including_unknown(frame[type_col])
        known_mask = cleaned.ne("") & cleaned.str.lower().ne(_UNKNOWN_TOKEN)
        known_count = int(cleaned[known_mask].nunique())
        observed_count = int(observed.nunique())
        unknown_samples = int((observed.str.lower() == _UNKNOWN_TOKEN).sum())
        metrics[METRIC_GOVERNED_KNOWN_TYPE_COUNT] = _metric(
            name=METRIC_GOVERNED_KNOWN_TYPE_COUNT,
            value=known_count,
            includes_unknown=False,
            authority_stage=authority_stage,
            filtering_stage="exclude_blank_and_unknown_type_slug",
            source_surface=source_surface,
            field=type_col,
            label="Known governed types",
            explanation=(
                "Distinct non-blank type_slug identities after excluding the unknown bucket."
            ),
        )
        metrics[METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN] = _metric(
            name=METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN,
            value=observed_count,
            includes_unknown=True,
            authority_stage=authority_stage,
            filtering_stage="blank_normalized_to_unknown",
            source_surface=source_surface,
            field=type_col,
            label="Observed type_slug values (including unknown)",
            explanation=(
                "Distinct type_slug values after mapping blank/null to unknown."
            ),
        )
        metrics[METRIC_UNKNOWN_TYPE_SAMPLE_COUNT] = _metric(
            name=METRIC_UNKNOWN_TYPE_SAMPLE_COUNT,
            value=unknown_samples,
            includes_unknown=True,
            authority_stage=authority_stage,
            filtering_stage="blank_normalized_to_unknown",
            source_surface=source_surface,
            field=type_col,
            label="Unknown/blank type samples",
            explanation="Sample rows whose type_slug is blank/null or unknown.",
        )
    else:
        for name, label in (
            (METRIC_GOVERNED_KNOWN_TYPE_COUNT, "Known governed types"),
            (
                METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN,
                "Observed type_slug values (including unknown)",
            ),
            (METRIC_UNKNOWN_TYPE_SAMPLE_COUNT, "Unknown/blank type samples"),
        ):
            metrics[name] = _metric(
                name=name,
                value=0,
                includes_unknown=name != METRIC_GOVERNED_KNOWN_TYPE_COUNT,
                authority_stage=authority_stage,
                filtering_stage="missing_type_column",
                source_surface=source_surface,
                field=type_col,
                label=label,
                explanation=f"Column {type_col!r} absent on source frame.",
            )

    values = {name: int(payload["value"]) for name, payload in metrics.items()}
    return {
        "contract_version": COHORT_COUNT_CONTRACT_VERSION,
        "metrics": metrics,
        "values": values,
        # Convenience aliases for callers.
        "governed_known_family_count": values[METRIC_GOVERNED_KNOWN_FAMILY_COUNT],
        "observed_family_label_count_including_unknown": values[
            METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN
        ],
        "unknown_family_sample_count": values[METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT],
        "governed_known_type_count": values[METRIC_GOVERNED_KNOWN_TYPE_COUNT],
        "observed_type_slug_count_including_unknown": values[
            METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN
        ],
        "unknown_type_sample_count": values[METRIC_UNKNOWN_TYPE_SAMPLE_COUNT],
    }


def resolve_cohort_counts_from_snapshot(
    snapshot_path: Any,
    *,
    family_col: str = "family_canonical",
    type_col: str = "type_slug",
) -> dict[str, Any]:
    """Load an analysis snapshot CSV and compute the canonical metrics."""
    from pathlib import Path

    path = Path(snapshot_path)
    frame = pd.read_csv(path)
    payload = compute_cohort_identity_counts(
        frame,
        family_col=family_col,
        type_col=type_col,
        source_surface=str(path),
        authority_stage="analysis_snapshot",
    )
    payload["snapshot_path"] = str(path)
    payload["prepared_sample_count"] = int(len(frame))
    return payload


def format_family_type_count_lines(counts: Mapping[str, Any]) -> list[str]:
    """Operator-facing lines with unambiguous unknown treatment."""
    values = counts.get("values") if isinstance(counts.get("values"), dict) else counts
    return [
        (
            f"Known governed families: {int(values.get(METRIC_GOVERNED_KNOWN_FAMILY_COUNT, 0)):,}"
        ),
        (
            "Observed family labels: "
            f"{int(values.get(METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN, 0)):,} "
            "including `unknown`"
        ),
        (
            f"Known governed types: {int(values.get(METRIC_GOVERNED_KNOWN_TYPE_COUNT, 0)):,}"
        ),
        (
            "Observed type_slug values: "
            f"{int(values.get(METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN, 0)):,} "
            "including `unknown`"
        ),
    ]


def _metric(
    *,
    name: str,
    value: int,
    includes_unknown: bool,
    authority_stage: str,
    filtering_stage: str,
    source_surface: str,
    field: str,
    label: str,
    explanation: str,
) -> dict[str, Any]:
    return {
        "metric_name": name,
        "value": int(value),
        "includes_unknown": bool(includes_unknown),
        "authority_stage": authority_stage,
        "filtering_stage": filtering_stage,
        "source_surface": source_surface,
        "field": field,
        "label": label,
        "explanation": explanation,
    }


__all__ = [
    "COHORT_COUNT_CONTRACT_VERSION",
    "METRIC_GOVERNED_KNOWN_FAMILY_COUNT",
    "METRIC_OBSERVED_FAMILY_LABEL_COUNT_INCLUDING_UNKNOWN",
    "METRIC_UNKNOWN_FAMILY_SAMPLE_COUNT",
    "METRIC_GOVERNED_KNOWN_TYPE_COUNT",
    "METRIC_OBSERVED_TYPE_SLUG_COUNT_INCLUDING_UNKNOWN",
    "METRIC_UNKNOWN_TYPE_SAMPLE_COUNT",
    "compute_cohort_identity_counts",
    "format_family_type_count_lines",
    "normalize_family_labels_including_unknown",
    "normalize_type_slugs_including_unknown",
    "resolve_cohort_counts_from_snapshot",
]
