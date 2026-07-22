"""Safe CSV helpers shared by reporting composers and diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pandas as pd


def require_csv(path: Path | str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """Load a required CSV; fail clearly on missing or empty files."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    if target.stat().st_size == 0:
        raise ValueError(f"required CSV is empty: {target}")
    try:
        return pd.read_csv(target, **read_csv_kwargs)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"required CSV has no columns: {target}") from exc


def optional_csv(path: Path | str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """Load a CSV when present; treat missing or empty files as an empty frame."""
    target = Path(path)
    if not target.is_file():
        return pd.DataFrame()
    try:
        if target.stat().st_size == 0:
            return pd.DataFrame()
        # Headerless newline/whitespace stubs from older writers.
        sample = target.read_bytes()[:64]
        if not sample.strip():
            return pd.DataFrame()
        return pd.read_csv(target, **read_csv_kwargs)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def write_csv(
    path: Path | str,
    frame: pd.DataFrame,
    *,
    empty_columns: Sequence[str] | None = None,
) -> None:
    """Write a CSV; never emit a headerless newline-only stub.

    Empty frames with known ``empty_columns`` get a header row. Empty frames with
    no columns write a zero-byte file so later ``optional_csv`` reads stay safe.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty and len(frame.columns) == 0:
        if empty_columns is not None:
            pd.DataFrame(columns=list(empty_columns)).to_csv(target, index=False)
            return
        target.write_text("", encoding="utf-8")
        return
    frame.to_csv(target, index=False)
