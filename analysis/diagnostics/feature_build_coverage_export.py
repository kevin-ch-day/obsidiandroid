"""Export cohort vs feature-matrix row coverage for alignment-gap debugging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from config import app_config
from utils import display_utils as du


def _normalize_sample_ids(values: Iterable[Any]) -> set[int]:
    out: set[int] = set()
    for v in values:
        try:
            x = float(v)
            if pd.isna(x):
                continue
            i = int(x)
            if float(i) == x:
                out.add(i)
        except (TypeError, ValueError):
            continue
    return out


def _index_sample_ids(index: Any) -> set[int]:
    return _normalize_sample_ids(list(index))


def export_feature_build_coverage(
    *,
    cohort_sample_ids: Iterable[Any],
    feature_df: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
    enabled: bool | None = None,
) -> tuple[Path | None, Path | None]:
    """Write JSON summary + CSV of cohort ids absent from the built feature matrix index.

    Uses ``feature_df.attrs["vendor_merge_sample_ids"]`` when present (row authority before
    extras join); otherwise falls back to the final matrix index.

    Returns:
        Tuple of (json_path, csv_path) or (None, None) when disabled or invalid inputs.
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True))
    if not enabled:
        return None, None
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        du.print_warning("[COVERAGE] Feature matrix empty — skipping coverage export.")
        return None, None

    cohort_set = _normalize_sample_ids(cohort_sample_ids)
    final_set = _index_sample_ids(feature_df.index)
    vendor_attrs = feature_df.attrs.get("vendor_merge_sample_ids")
    if isinstance(vendor_attrs, list) and vendor_attrs:
        vendor_set = _normalize_sample_ids(vendor_attrs)
    else:
        vendor_set = set(final_set)

    missing_from_feature = sorted(cohort_set - final_set)
    extra_in_feature = sorted(final_set - cohort_set)

    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "cohort_unique_sample_count": len(cohort_set),
        "feature_matrix_unique_row_count": len(final_set),
        "vendor_merge_authority_unique_count": len(vendor_set),
        "cohort_rows_missing_from_feature_matrix": len(missing_from_feature),
        "feature_rows_not_in_cohort": len(extra_in_feature),
        "vendor_merge_equals_final_index": vendor_set == final_set,
        "row_authority_note": (
            "Final matrix index equals encoded vendor-merge rows; extras join is left onto that "
            "index (see ml_classification/vectorization/feature_vector_builder._merge_extra_features)."
        ),
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = str(run_id)

    json_named = out_dir / f"feature_build_coverage_{rid}.json"
    json_latest = out_dir / "feature_build_coverage.latest.json"
    for target in (json_named, json_latest):
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    csv_named = out_dir / f"cohort_missing_from_feature_matrix_{rid}.csv"
    csv_latest = out_dir / "cohort_missing_from_feature_matrix.latest.csv"
    missing_df = pd.DataFrame({"sample_id": missing_from_feature})
    for target in (csv_named, csv_latest):
        missing_df.to_csv(target, index=False)

    du.print_info(
        "[COVERAGE] Feature build cohort gap: "
        f"missing_from_matrix={len(missing_from_feature)} "
        f"(cohort={len(cohort_set)}, matrix_rows={len(final_set)})."
    )
    return json_latest, csv_latest


__all__ = ["export_feature_build_coverage", "_normalize_sample_ids"]
