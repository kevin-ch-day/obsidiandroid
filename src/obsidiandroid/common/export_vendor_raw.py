"""Vendor raw artifact export helpers."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from typing import Callable

import pandas as pd


LogEvent = Callable[..., None]


def is_parquet_supported() -> bool:
    """Return whether a parquet engine is installed.

    Returns:
        ``True`` when either ``pyarrow`` or ``fastparquet`` is available.
    """
    return bool(find_spec("pyarrow") or find_spec("fastparquet"))


def export_vendor_raw_artifacts(
    parsed_data: dict,
    export_enabled: bool,
    export_formats: tuple[str, ...],
    output_root: Path,
    run_id: str,
    safe_artifact_name: Callable[[str], str],
    log_event: LogEvent,
    logger,
) -> dict[str, int]:
    """Persist raw vendor parser outputs to lightweight artifacts.

    Args:
        parsed_data: Vendor-to-DataFrame mapping.
        export_enabled: Runtime flag controlling whether artifacts are emitted.
        export_formats: Requested output formats (e.g. ``csv`` and ``parquet``).
        output_root: Export root directory.
        run_id: Current runtime identifier.
        safe_artifact_name: Sanitizer for artifact file tokens.
        log_event: Structured logging callback.
        logger: Logger instance used by ``log_event``.

    Returns:
        Counts for emitted artifacts and errors.
    """
    metrics = {"vendors": 0, "csv": 0, "parquet": 0, "errors": 0}
    if not export_enabled or not export_formats:
        return metrics

    raw_root = output_root / "vendor_raw" / run_id
    raw_root.mkdir(parents=True, exist_ok=True)

    for vendor, df in parsed_data.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        metrics["vendors"] += 1
        vendor_token = safe_artifact_name(vendor)
        for fmt in export_formats:
            try:
                if fmt == "csv":
                    out_path = raw_root / f"{vendor_token}.csv"
                    df.to_csv(out_path, index=False)
                    metrics["csv"] += 1
                elif fmt == "parquet":
                    out_path = raw_root / f"{vendor_token}.parquet"
                    df.to_parquet(out_path, index=False)
                    metrics["parquet"] += 1
            except Exception as exc:  # pragma: no cover - defensive logging path
                metrics["errors"] += 1
                log_event(
                    logger,
                    "export_vendor_raw_failed",
                    event_id="EXPORT_VENDOR_RAW_500",
                    level="WARNING",
                    vendor=vendor,
                    format=fmt,
                    error=str(exc),
                    path=str(raw_root),
                )

    return metrics


__all__ = ["export_vendor_raw_artifacts", "is_parquet_supported"]
