# Filename: obsidiandroid/pipeline/attach_engine_metadata.py
# Purpose  : Resolve AV engine metadata for matrices; persist overlay CSV without mutating sample rows.
#
# Canonical (**Pass 71**): legacy ``analysis.pipeline.attach_engine_metadata`` is shim.

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.database import db_av_engine_detection_totals

METADATA_FIELDS = [
    "detection_strategy", "is_trusted_vendor", "is_engine_active",
    "total_scanned", "malicious_count", "suspicious_count", "benign_count",
    "undetected_count", "unknown_count", "family_name_hits",
    "coverage_pct", "malicious_pct", "suspicious_pct", "threat_signal_score"
]

def fetch_engine_metadata(verbose: bool = True) -> pd.DataFrame:
    try:
        engine_df = db_av_engine_detection_totals.get_engine_detection_totals(as_dataframe=True)

        if not isinstance(engine_df, pd.DataFrame) or engine_df.empty:
            raise ValueError("Engine metadata is empty or invalid.")

        required_columns = {"engine_name", "detection_strategy", "is_trusted_vendor", "is_engine_active"}
        missing = required_columns - set(engine_df.columns)
        if missing:
            raise KeyError(f"Missing metadata fields: {sorted(missing)}")

        return engine_df

    except Exception:
        return pd.DataFrame()


def _build_metadata_overlay(
    matrix_columns: list[str], engine_df: pd.DataFrame, verbose: bool
) -> pd.DataFrame:
    """Construct metadata rows aligned to the detection matrix columns."""
    if "engine_name" not in engine_df.columns:
        return pd.DataFrame()

    engine_df = engine_df.set_index("engine_name")
    overlay_rows = {}

    for field in METADATA_FIELDS:
        values = engine_df.get(field)
        if values is None:
            overlay_rows[f"meta::{field}"] = [None] * len(matrix_columns)
        else:
            overlay_rows[f"meta::{field}"] = values.reindex(matrix_columns).tolist()

    meta_df = pd.DataFrame(overlay_rows, index=matrix_columns).T
    meta_df.dropna(how="all", inplace=True)
    return meta_df


def _overlay_diagnostics_dir() -> Path:
    diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if diag:
        return Path(diag)
    base = str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output") or "output")
    return Path(base) / "diagnostics"


def _write_engine_metadata_overlay_csv(meta_df: pd.DataFrame, *, verbose: bool) -> str | None:
    """Persist engine metadata rows for inspection; does not append to the sample matrix."""
    if meta_df.empty:
        return None
    out_dir = _overlay_diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = oh.normalize_artifact_run_id(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    path = out_dir / f"engine_metadata_overlay_{run_id}.csv"
    csv_text = meta_df.to_csv(index=True)
    path.write_text(csv_text, encoding="utf-8")
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=path.name,
        csv_text=csv_text,
        global_latest_name="engine_metadata_overlay.latest.csv",
    )
    setattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", str(path))
    if verbose:
        du.print_info(
            f"[AV] Engine metadata overlay written to {path} "
            "(not concatenated onto the enriched matrix)."
        )
    return str(path)


def attach_engine_metadata(matrix_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    setattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "")
    engine_df = fetch_engine_metadata(verbose=verbose)
    if engine_df.empty:
        return matrix_df

    matrix_columns = matrix_df.columns.tolist()
    engine_names = set(engine_df["engine_name"])
    matched_columns = [col for col in matrix_columns if col in engine_names]

    if not matched_columns:
        return matrix_df

    meta_df = _build_metadata_overlay(matrix_columns, engine_df, verbose)
    meta_df = meta_df.reindex(columns=matrix_df.columns)
    meta_df.fillna(value=pd.NA, inplace=True)
    meta_df = meta_df.dropna(axis=1, how="all")

    for col in meta_df.columns:
        if col in matrix_df.columns:
            try:
                meta_df[col] = meta_df[col].astype(matrix_df[col].dtype)
            except Exception:
                meta_df[col] = meta_df[col].astype("object")

    if meta_df.empty:
        return matrix_df

    try:
        _write_engine_metadata_overlay_csv(meta_df, verbose=verbose)
    except Exception as exc:
        if verbose:
            du.print_warning(f"[AV] Engine metadata overlay export failed: {exc}")
        setattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "")
    return matrix_df
