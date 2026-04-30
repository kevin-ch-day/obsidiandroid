"""Deterministic hashing helpers for manifest and evidence artifacts."""

from __future__ import annotations

import hashlib
from typing import Iterable

import pandas as pd


def sha256_hex(payload: bytes) -> str:
    """Return SHA-256 digest for bytes payload."""
    return hashlib.sha256(payload).hexdigest()


def canonical_csv_bytes(
    dataframe: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    float_format: str = "%.6f",
    lineterminator: str = "\n",
) -> bytes:
    """Serialize dataframe to canonical CSV bytes.

    Args:
        dataframe: Source dataframe.
        columns: Optional fixed column order.
        float_format: Float formatting contract.
        lineterminator: Newline contract.

    Returns:
        UTF-8 canonical CSV bytes.
    """
    frame = dataframe.copy()
    if columns is not None:
        frame = frame[columns].copy()
    csv_text = frame.to_csv(
        index=False,
        float_format=float_format,
        lineterminator=lineterminator,
    )
    return csv_text.encode("utf-8")


def dataset_hash_from_sample_ids(sample_ids: Iterable[object]) -> str:
    """Compute dataset hash from sorted sample-id values."""
    normalized = sorted(str(value) for value in sample_ids if value is not None)
    return sha256_hex("\n".join(normalized).encode("utf-8"))

