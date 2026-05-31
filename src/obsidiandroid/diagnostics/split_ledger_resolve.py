"""Resolve on-disk split ledger CSV paths (canonical headline ledger only)."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.common import output_hygiene as oh


def resolve_split_freeze_csv(diagnostics_dir: Path, run_id: str) -> Path | None:
    """Return the best-matching split ledger file, or ``None`` if missing.

    Preference order:
    1. Run-scoped headline ledger (canonical contract for manifest ``split_hash``)
    2. Global/latest headline mirror
    """
    rid = str(run_id).strip()
    candidates = [
        diagnostics_dir / f"split_freeze_headline_{rid}.csv",
        diagnostics_dir / "split_freeze_headline.latest.csv",
        oh.global_diagnostics_root() / "split_freeze_headline.latest.csv",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


__all__ = ["resolve_split_freeze_csv"]
