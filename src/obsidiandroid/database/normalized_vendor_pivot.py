"""Project normalized VirusTotal verdicts into the legacy wide AV shape.

This adapter is read only. Callers supply normalized rows joined to
``virustotal_vendor_engines`` and the wide table's engine column names.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def pivot_vendor_verdicts(
    rows: Iterable[Mapping[str, Any]], vendor_columns: Iterable[str]
) -> dict[int, dict[str, str | None]]:
    """Return one legacy-shaped row per sample, with absent cells as ``None``.

    ``verdict_label`` takes precedence over ``verdict_category``, matching the
    maintained Erebus wide backfill. Unknown vendor keys are excluded because
    the existing wide table has no corresponding column.
    """
    columns = tuple(vendor_columns)
    allowed = set(columns)
    result: dict[int, dict[str, str | None]] = {}
    for row in rows:
        sample_id = int(row["sample_id"])
        cells = result.setdefault(sample_id, {column: None for column in columns})
        key = str(row.get("vendor_key") or "").strip()
        if key not in allowed:
            continue
        value = row.get("verdict_label") or row.get("verdict_category") or None
        cells[key] = str(value) if value is not None else None
    return result
