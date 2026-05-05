"""Resolve on-disk split ledger CSV paths (headline preferred; audit mirror for compatibility)."""

from __future__ import annotations

from pathlib import Path


def resolve_split_freeze_csv(diagnostics_dir: Path, run_id: str) -> Path | None:
    """Return the best-matching split ledger file, or ``None`` if missing.

    Preference order:
    1. Run-scoped headline ledger (canonical contract for manifest ``split_hash``)
    2. Global/latest headline mirror
    3. Run-scoped legacy ``split_freeze_audit`` mirror (byte copy of headline when present)
    4. Legacy global/latest mirror
    """
    rid = str(run_id).strip()
    candidates = [
        diagnostics_dir / f"split_freeze_headline_{rid}.csv",
        diagnostics_dir / "split_freeze_headline.latest.csv",
        diagnostics_dir / f"split_freeze_audit_{rid}.csv",
        diagnostics_dir / "split_freeze_audit.latest.csv",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


__all__ = ["resolve_split_freeze_csv"]
