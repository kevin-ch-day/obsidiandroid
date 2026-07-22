"""Safe CSV helpers shared by reporting composers and diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd


def require_csv(path: Path | str) -> pd.DataFrame:
    """Load a required CSV; fail clearly on missing or empty files."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    if target.stat().st_size == 0:
        raise ValueError(f"required CSV is empty: {target}")
    try:
        return pd.read_csv(target)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"required CSV has no columns: {target}") from exc


def optional_csv(path: Path | str) -> pd.DataFrame:
    """Load a CSV when present; treat missing or empty files as an empty frame."""
    target = Path(path)
    if not target.is_file() or target.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(target)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def write_csv(
    path: Path | str,
    frame: pd.DataFrame,
    *,
    empty_columns: Sequence[str] | None = None,
) -> None:
    """Write a CSV; empty frames still emit a header row when columns are known."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty and empty_columns is not None and len(frame.columns) == 0:
        pd.DataFrame(columns=list(empty_columns)).to_csv(target, index=False)
        return
    frame.to_csv(target, index=False)
