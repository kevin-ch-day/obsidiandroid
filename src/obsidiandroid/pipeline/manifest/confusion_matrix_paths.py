"""Resolve confusion matrix artifact paths for manifest and paper exports."""

from __future__ import annotations

from pathlib import Path


def find_primary_confusion_matrix(
    *, run_root: Path, top_model: str, evidence_mode: bool = False
) -> Path | None:
    """Resolve primary confusion matrix path from run-scoped output."""
    cm_dir = run_root / "conf_matrices"
    if not cm_dir.exists():
        return None
    primary_stable = cm_dir / "confusion_matrix_primary.png"
    if primary_stable.exists():
        return primary_stable

    rf_headline = cm_dir / "confusion_matrix_random_forest.png"
    if rf_headline.exists():
        return rf_headline

    if evidence_mode:
        rf_suffix = sorted(cm_dir.glob("confusion_matrix_*random_forest*.png"))
        if rf_suffix:
            return rf_suffix[0]
    tm = cm_dir / f"confusion_matrix_{top_model}.png"
    if tm.exists():
        return tm
    prefixed = sorted(cm_dir.glob(f"confusion_matrix_*{top_model}*.png"))
    if prefixed:
        return prefixed[0]
    files = sorted(cm_dir.glob("confusion_matrix_*.png"))
    return files[0] if files else None
