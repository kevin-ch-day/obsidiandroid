"""Permission column nonzero counts across the training matrix shrink chain."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh

PermStageBundle = Tuple[dict[str, int], int]


def perm_prefix_nonzero_stats(features_df: pd.DataFrame | None) -> dict[str, int]:
    """Return nonzero counts for ``perm__`` / ``perm_grp__`` columns after numeric coercion."""
    out: dict[str, int] = {}
    if features_df is None or features_df.empty:
        return out
    for col in features_df.columns:
        name = str(col)
        if not (name.startswith("perm__") or name.startswith("perm_grp__")):
            continue
        series = pd.to_numeric(features_df[col], errors="coerce").fillna(0)
        out[name] = int((series > 0).sum())
    return out


def export_permission_training_survival_audit(
    *,
    after_align: PermStageBundle,
    after_family_support: PermStageBundle,
    after_low_information_prune: PermStageBundle,
    after_leakage_prune: PermStageBundle,
    diagnostics_dir: Path,
    run_id: str,
    cohort_fused: PermStageBundle | None = None,
) -> str | None:
    """Write a CSV comparing permission signals from align through leakage pruning.

    Args:
        after_align: ``(perm_prefix_nonzero_stats, row_count)`` after label alignment.
        after_family_support: Stats after min-family-support filtering.
        after_low_information_prune: Stats after low-variance column drops.
        after_leakage_prune: Stats after leakage pruning (final training columns).
        cohort_fused: Optional stats on the full cohort-fused matrix (pre-alignment), for
            comparison with the training shrink chain.
        diagnostics_dir: Run diagnostics directory.
        run_id: Run identifier for filenames.

    Returns:
        Path to the run-scoped CSV, or None when no permission-like columns exist.
    """
    all_cols: set[str] = set()
    for stats_dict, _ in (
        after_align,
        after_family_support,
        after_low_information_prune,
        after_leakage_prune,
    ):
        all_cols |= set(stats_dict.keys())
    if cohort_fused is not None:
        all_cols |= set(cohort_fused[0].keys())
    if not all_cols:
        setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "")
        return None

    def _nz(bundle: PermStageBundle, col: str) -> int | None:
        return bundle[0].get(col)

    def _nrows(bundle: PermStageBundle) -> int:
        return int(bundle[1])

    rows: list[dict[str, object]] = []
    fam_keys = set(after_family_support[0].keys())
    low_keys = set(after_low_information_prune[0].keys())
    leak_keys = set(after_leakage_prune[0].keys())
    for col in sorted(all_cols):
        rows.append(
            {
                "column": col,
                "nonzero_cohort_fused": _nz(cohort_fused, col) if cohort_fused else None,
                "matrix_rows_cohort_fused": _nrows(cohort_fused) if cohort_fused else None,
                "nonzero_after_align": _nz(after_align, col),
                "matrix_rows_after_align": _nrows(after_align),
                "nonzero_after_family_support": _nz(after_family_support, col),
                "matrix_rows_after_family_support": _nrows(after_family_support),
                "nonzero_after_low_information_prune": _nz(after_low_information_prune, col),
                "matrix_rows_after_low_information_prune": _nrows(after_low_information_prune),
                "nonzero_after_leakage_prune": _nz(after_leakage_prune, col),
                "matrix_rows_after_leakage_prune": _nrows(after_leakage_prune),
                "dropped_by_low_information_prune": col in fam_keys and col not in low_keys,
                "dropped_by_leakage_prune": col in low_keys and col not in leak_keys,
            }
        )

    out_df = pd.DataFrame(rows)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    path = diagnostics_dir / f"permission_training_survival_{run_id}.csv"
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=path.name,
        csv_text=out_df.to_csv(index=False),
        global_latest_name="permission_training_survival.latest.csv",
    )
    setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", str(path))
    return str(path)
