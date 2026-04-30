"""Canonical serialization and hashing helpers for governance artifacts."""

from __future__ import annotations

import csv
import io
import re
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def normalize_sha256(value: Any) -> str:
    """Normalize and validate SHA256 string for paper-mode contracts."""
    text = str(value or "").strip().lower()
    if not SHA256_PATTERN.match(text):
        raise ValueError(f"Invalid SHA256 value: {value!r}")
    return text


def canonical_csv_bytes(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    """Serialize rows as canonical UTF-8/LF CSV bytes without BOM."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        normalized = {}
        for field in fieldnames:
            value = row.get(field, "")
            if isinstance(value, str):
                normalized[field] = value.strip()
            else:
                normalized[field] = value
        writer.writerow(normalized)
    return output.getvalue().encode("utf-8")
