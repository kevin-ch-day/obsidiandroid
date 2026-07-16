"""Run-scoped provenance for AV engine, parser, and headline-feature selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name


def _canonical_vendor(value: object) -> str:
    """Normalize a vendor or engine name for cross-surface joins."""
    return canonicalize_engine_name(str(value or ""))


def export_av_selection_contract(
    *,
    lifecycle_df: pd.DataFrame,
    weights_df: pd.DataFrame | None,
    binary_feature_columns: list[str],
    final_feature_columns: list[str],
    selected_vendors: list[str],
    selected_vendor_predictive_field_count: int,
    binary_scope_contract: dict[str, Any] | None,
    diagnostics_dir: str | Path,
    run_id: str,
    profile_id: str,
) -> str:
    """Write one row per observed engine across the three AV selection surfaces.

    ``parser_*`` fields are blank for engines without a mapped parser.  The
    final-feature flag is based on the train-partition feature contract, so it
    answers which binary AV columns actually reached headline training rather
    than merely which columns were available before low-information pruning.
    """
    if not isinstance(lifecycle_df, pd.DataFrame) or lifecycle_df.empty:
        return ""
    if "engine_name_canonical" not in lifecycle_df.columns:
        return ""

    frame = lifecycle_df.copy()
    frame["engine_join_key"] = frame["engine_name_canonical"].map(_canonical_vendor)
    binary_keys = {_canonical_vendor(column) for column in binary_feature_columns}
    final_keys = {_canonical_vendor(column) for column in final_feature_columns}
    selected_keys = {_canonical_vendor(vendor) for vendor in selected_vendors}
    frame["binary_column_in_declared_scope"] = frame["engine_join_key"].isin(binary_keys).astype(int)
    frame["binary_column_retained_for_headline_training"] = frame["engine_join_key"].isin(final_keys).astype(int)
    frame["selected_parser_vendor"] = frame["engine_join_key"].isin(selected_keys).astype(int)

    parser_columns = [
        "Vendor",
        "included_in_model",
        "parser_gate_status",
        "Leakage Safe Score Raw",
        "Leakage Safe Score",
        "Final ML Score",
        "Vendor Category",
    ]
    if isinstance(weights_df, pd.DataFrame) and not weights_df.empty and "Vendor" in weights_df.columns:
        right = weights_df.loc[:, [column for column in parser_columns if column in weights_df.columns]].copy()
        right["engine_join_key"] = right["Vendor"].map(_canonical_vendor)
        right = right.drop_duplicates("engine_join_key", keep="first")
        right = right.rename(
            columns={
                "Vendor": "parser_vendor",
                "included_in_model": "parser_gate_included",
                "parser_gate_status": "parser_gate_status",
                "Leakage Safe Score Raw": "parser_leakage_safe_score_raw",
                "Leakage Safe Score": "parser_leakage_safe_score_gated",
                "Final ML Score": "parser_final_ml_score_diagnostic",
                "Vendor Category": "parser_vendor_category",
            }
        )
        frame = frame.merge(right, on="engine_join_key", how="left", validate="one_to_one")

    scope = dict(binary_scope_contract or {})
    frame["binary_feature_engine_scope"] = str(
        scope.get("binary_feature_engine_scope", "all_observed")
    )
    frame["selected_vendor_predictive_field_count"] = int(selected_vendor_predictive_field_count)
    frame["run_id"] = str(run_id)
    frame["profile_id"] = str(profile_id)
    frame = frame.drop(columns=["engine_join_key"])

    out_dir = Path(diagnostics_dir)
    filename = f"av_selection_contract_{oh.normalize_artifact_run_id(run_id)}.csv"
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=filename,
        csv_text=frame.to_csv(index=False),
        global_latest_name="av_selection_contract.latest.csv",
    )
    return str(paths[0])
