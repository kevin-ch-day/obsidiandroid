"""Observation-date temporal contract for offline research reports.

This is an observation-date framework, not APK creation dating.

Precedence (when fields are present and parseable):

1. first_seen_in_the_wild (highest evidentiary value; often sparse)
2. first_discovered (when an explicit discovered field exists)
3. first_analyzed / VirusTotal first submission (default broad-coverage proxy)

Original source fields are always retained alongside the selected date.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd

TEMPORAL_OBSERVATION_CONTRACT_VERSION = "1.0.0"
TEMPORAL_COMPOSER_VERSION = "1.0.0"

SOURCE_FIRST_SEEN_IN_THE_WILD = "first_seen_in_the_wild"
SOURCE_FIRST_DISCOVERED = "first_discovered"
SOURCE_FIRST_ANALYZED_SUBMISSION = "first_analyzed_or_first_submission"
SOURCE_COLLECTION_TIMESTAMP = "collection_timestamp"
SOURCE_MISSING = "missing"

SOURCE_CONFIDENCE = {
    SOURCE_FIRST_SEEN_IN_THE_WILD: "high",
    SOURCE_FIRST_DISCOVERED: "medium_high",
    SOURCE_FIRST_ANALYZED_SUBMISSION: "medium",
    SOURCE_COLLECTION_TIMESTAMP: "low",
    SOURCE_MISSING: "none",
}

# Column aliases observed in run artifacts / possible future fields.
ITW_COLUMNS = ("vt_first_seen_itw_date", "first_seen_in_the_wild", "first_seen_itw_date")
DISCOVERED_COLUMNS = ("first_discovered", "first_discovered_at_utc", "vt_first_discovered_date")
SUBMISSION_COLUMNS = (
    "vt_first_submission_date",
    "vt_first_submission_at_utc",
    "first_analyzed",
    "first_analyzed_at_utc",
    "effective_first_seen_at_utc",
)
COLLECTION_COLUMNS = ("collection_timestamp", "collected_at_utc", "ingest_at_utc")


def temporal_observation_contract_metadata() -> dict[str, Any]:
    """Return durable temporal contract metadata."""
    return {
        "temporal_observation_contract_version": TEMPORAL_OBSERVATION_CONTRACT_VERSION,
        "composer_version": TEMPORAL_COMPOSER_VERSION,
        "framework": "observation_date_not_apk_creation",
        "precedence": [
            SOURCE_FIRST_SEEN_IN_THE_WILD,
            SOURCE_FIRST_DISCOVERED,
            SOURCE_FIRST_ANALYZED_SUBMISSION,
        ],
        "source_confidence": dict(SOURCE_CONFIDENCE),
        "apk_creation_dating": False,
        "notes": (
            "Selected temporal dates are observation / submission / discovery proxies. "
            "They must not be treated as APK creation timestamps. "
            "Original source fields are retained; selection does not overwrite them."
        ),
    }


def _is_missing_scalar(value: Any) -> bool:
    if value is None:
        return True
    try:
        # Covers float NaN, pd.NaT, and pd.NA without treating non-empty strings as NA.
        if value is pd.NA:
            return True
        if not isinstance(value, (str, bytes)) and pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "nat", "none", "null", "(null)", "<na>"}


def parse_observation_timestamp(value: Any) -> pd.Timestamp | pd.NaT:
    """Parse a timestamp without inventing values for blanks."""
    if _is_missing_scalar(value):
        return pd.NaT
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return ts


def _usable_timestamp_field(row: Mapping[str, Any], columns: tuple[str, ...]) -> tuple[str, Any, pd.Timestamp]:
    """Return the first column with a parseable timestamp, else empty."""
    for col in columns:
        if col not in row or _is_missing_scalar(row[col]):
            continue
        ts = parse_observation_timestamp(row[col])
        if pd.notna(ts):
            return col, row[col], ts
    return "", None, pd.NaT


def select_temporal_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    """Select temporal date for one sample while preserving original fields."""
    originals: dict[str, Any] = {}
    for col in (*ITW_COLUMNS, *DISCOVERED_COLUMNS, *SUBMISSION_COLUMNS, *COLLECTION_COLUMNS):
        if col in row:
            originals[f"original__{col}"] = row[col]

    itw_col, itw_val, itw_ts = _usable_timestamp_field(row, ITW_COLUMNS)
    disc_col, disc_val, disc_ts = _usable_timestamp_field(row, DISCOVERED_COLUMNS)
    sub_col, sub_val, sub_ts = _usable_timestamp_field(row, SUBMISSION_COLUMNS)
    col_col, col_val, col_ts = _usable_timestamp_field(row, COLLECTION_COLUMNS)

    selected_source = SOURCE_MISSING
    selected_raw = None
    selected_field = ""
    selected_ts: pd.Timestamp | pd.NaT = pd.NaT

    if itw_col:
        selected_source = SOURCE_FIRST_SEEN_IN_THE_WILD
        selected_raw = itw_val
        selected_field = itw_col
        selected_ts = itw_ts
    elif disc_col:
        selected_source = SOURCE_FIRST_DISCOVERED
        selected_raw = disc_val
        selected_field = disc_col
        selected_ts = disc_ts
    elif sub_col:
        selected_source = SOURCE_FIRST_ANALYZED_SUBMISSION
        selected_raw = sub_val
        selected_field = sub_col
        selected_ts = sub_ts
    elif col_col:
        selected_source = SOURCE_COLLECTION_TIMESTAMP
        selected_raw = col_val
        selected_field = col_col
        selected_ts = col_ts

    year = int(selected_ts.year) if pd.notna(selected_ts) else pd.NA
    eligible = bool(pd.notna(selected_ts))
    missingness = {
        "missing_first_seen_in_the_wild": not bool(itw_col),
        "missing_first_discovered": not bool(disc_col),
        "missing_first_analyzed_or_submission": not bool(sub_col),
        "missing_collection_timestamp": not bool(col_col),
        "missing_selected_temporal_date": not eligible,
    }
    return {
        "selected_temporal_date": selected_ts.isoformat() if pd.notna(selected_ts) else "",
        "selected_temporal_timestamp_utc": selected_ts,
        "selected_date_source": selected_source,
        "selected_date_source_field": selected_field,
        "source_confidence": SOURCE_CONFIDENCE[selected_source],
        "observation_year": year,
        "temporal_eligibility_status": "eligible" if eligible else "ineligible_missing_date",
        "apk_creation_dating": False,
        **missingness,
        **originals,
    }


def attach_temporal_observations(labels: pd.DataFrame) -> pd.DataFrame:
    """Attach temporal selection columns to a labels frame."""
    if labels.empty:
        return labels.copy()
    records = [select_temporal_observation(row._asdict() if hasattr(row, "_asdict") else row) for row in labels.to_dict(orient="records")]
    temporal = pd.DataFrame(records)
    out = labels.reset_index(drop=True).copy()
    for col in temporal.columns:
        out[col] = temporal[col].values
    return out


def extract_observation_year(value: Any) -> int | None:
    """Extract calendar year from a timestamp-like value."""
    ts = parse_observation_timestamp(value)
    if pd.isna(ts):
        return None
    return int(ts.year)


__all__ = [
    "SOURCE_CONFIDENCE",
    "SOURCE_FIRST_ANALYZED_SUBMISSION",
    "SOURCE_FIRST_DISCOVERED",
    "SOURCE_FIRST_SEEN_IN_THE_WILD",
    "SOURCE_MISSING",
    "TEMPORAL_OBSERVATION_CONTRACT_VERSION",
    "attach_temporal_observations",
    "extract_observation_year",
    "parse_observation_timestamp",
    "select_temporal_observation",
    "temporal_observation_contract_metadata",
]
