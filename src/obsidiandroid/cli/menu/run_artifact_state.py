"""Shared run-artifact lookup helpers for operator-facing menus."""

from __future__ import annotations

from pathlib import Path


def resolve_model_comparison_summary_csv(*, output_root: Path, run_id: str | None) -> Path | None:
    """Resolve the best available model comparison summary CSV for a run."""
    base = Path(output_root)
    diagnostics_dir = base / "diagnostics"
    token = str(run_id or "").strip()
    if token:
        run_scoped_dir = base / "runs" / token / "diagnostics"
        candidates = [
            run_scoped_dir / f"model_comparison_summary_{token}.csv",
            diagnostics_dir / f"model_comparison_summary_{token}.csv",
            *sorted(run_scoped_dir.glob("model_comparison_summary_*.csv"), reverse=True),
        ]
    else:
        candidates = []
    candidates.extend(sorted(diagnostics_dir.glob("model_comparison_summary_*.csv"), reverse=True))
    return next((path for path in candidates if path.is_file()), None)


def resolve_within_cross_type_confusion_csv(*, output_root: Path, run_id: str | None) -> Path | None:
    """Resolve the best available within-vs-cross-type confusion summary CSV."""
    base = Path(output_root)
    token = str(run_id or "").strip()
    candidates: list[Path] = []
    if token:
        candidates.extend(
            [
                base / "runs" / token / "diagnostics" / "confusion_within_vs_cross_type.latest.csv",
                base
                / "runs"
                / token
                / "bundles"
                / "permission_trends"
                / "tables"
                / "confusion_within_vs_cross_type.latest.csv",
            ]
        )
    candidates.append(
        base / "bundles" / "latest" / "permission_trends" / "tables" / "confusion_within_vs_cross_type.latest.csv"
    )
    return next((path for path in candidates if path.is_file()), None)


__all__ = [
    "resolve_model_comparison_summary_csv",
    "resolve_within_cross_type_confusion_csv",
]
