# Filename: db_av_engine_verdicts.py
# Simplified AV verdict processor for data engineering and analysis

from __future__ import annotations

from collections import OrderedDict
import pandas as pd

from config import app_config
from database import db_engine
from utils import display_utils as du

METADATA_COLS = {
    "updated_at",
    "record_id",
    "sample_id",
    "malicious",
    "suspicious",
    "undetected",
    "harmless",
    "timeout",
    "confirmed_timeout",
    "failure",
    "type_unsupported",
    "total_engines",
    "record_created_at",
}

_VERDICT_QUERY_CACHE: OrderedDict[tuple[int, int], pd.DataFrame] = OrderedDict()


def _build_cache_key(sample_ids: list[int]) -> tuple[int, int]:
    """Create deterministic cache key for a sample ID universe."""
    canonical_ids = tuple(sorted(int(value) for value in sample_ids))
    return (len(canonical_ids), hash(canonical_ids))


def _cache_enabled() -> bool:
    """Return whether verdict query caching is enabled for this run."""
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        return False
    return bool(getattr(app_config, "ENABLE_AV_VERDICT_QUERY_CACHE", True))


def _cache_get(cache_key: tuple[int, int]) -> pd.DataFrame | None:
    """Return cached verdict DataFrame copy when available."""
    cached = _VERDICT_QUERY_CACHE.get(cache_key)
    if cached is None:
        return None
    _VERDICT_QUERY_CACHE.move_to_end(cache_key)
    return cached.copy(deep=True)


def _cache_set(cache_key: tuple[int, int], df: pd.DataFrame) -> None:
    """Store verdict DataFrame in bounded LRU cache."""
    cache_limit = max(1, int(getattr(app_config, "AV_VERDICT_QUERY_CACHE_SIZE", 2)))
    _VERDICT_QUERY_CACHE[cache_key] = df.copy(deep=True)
    _VERDICT_QUERY_CACHE.move_to_end(cache_key)
    while len(_VERDICT_QUERY_CACHE) > cache_limit:
        _VERDICT_QUERY_CACHE.popitem(last=False)


def fetch_verdicts_simple_ids(sample_ids, verbose=True):
    """Fetch wide AV verdict rows for supplied sample IDs.

    Uses chunked IN queries to avoid excessively long SQL statements on larger
    cohorts while preserving the existing dataframe contract.
    """
    if not sample_ids:
        du.print_debug("[VERDICT:SKIP] No sample_ids provided to fetch_verdicts_simple_ids.")
        return pd.DataFrame()

    unique_ids = list(dict.fromkeys(sample_ids))
    cache_key = _build_cache_key(unique_ids)
    if _cache_enabled():
        cached_df = _cache_get(cache_key)
        if cached_df is not None:
            du.print_debug("[VERDICT:CACHE] Using cached AV verdict query result.")
            return cached_df

    chunk_size = max(1, int(getattr(app_config, "AV_VERDICT_QUERY_CHUNK_SIZE", 500)))

    cols = None
    rows = []
    try:
        for idx in range(0, len(unique_ids), chunk_size):
            batch = unique_ids[idx : idx + chunk_size]
            placeholders = ", ".join(["%s"] * len(batch))
            query = (
                "SELECT * FROM virustotal_sample_vendor_engine_verdicts "
                f"WHERE sample_id IN ({placeholders})"
            )
            batch_cols, batch_rows = db_engine.execute_query(
                query,
                params=batch,
                fetch=True,
                return_columns=True,
            )
            if cols is None:
                cols = batch_cols
            rows.extend(batch_rows or [])
    except Exception as exc:
        du.print_error(f"[VERDICT:FAIL] SQL query failed:\n  {exc}")
        return pd.DataFrame()

    if isinstance(rows, list) and rows and all(isinstance(r, str) for r in rows):
        du.print_error(
            "[VERDICT:ERROR] Malformed row data: received list of strings instead of tuple rows."
        )
        du.print_debug(f"[VERDICT:DEBUG] First row sample: {rows[:5]}")
        return pd.DataFrame()

    if not rows or not cols:
        du.print_warning("[VERDICT:EMPTY] No AV verdicts retrieved.")
        return pd.DataFrame()

    if any(len(row) != len(cols) for row in rows):
        du.print_error(
            f"[VERDICT:CORRUPT] Row/column mismatch - rows: {len(rows)}, cols: {len(cols)}"
        )
        mismatch = next((r for r in rows if len(r) != len(cols)), None)
        du.print_debug(f"[VERDICT:DEBUG] Example mismatch row: {mismatch}")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        du.print_warning("[VERDICT:EMPTY] DataFrame is empty after conversion.")
        return pd.DataFrame()

    if "total_engines" in df.columns and df["total_engines"].gt(0).any():
        for col in ["malicious", "suspicious", "undetected", "harmless"]:
            if col in df.columns:
                df[f"{col}_pct"] = (df[col] / df["total_engines"] * 100).round(2)
        df.drop(
            columns=["malicious", "suspicious", "undetected", "harmless"],
            inplace=True,
            errors="ignore",
        )

    engine_cols = [col for col in df.columns if col not in METADATA_COLS]
    df["av_hits"] = df[engine_cols].notna().sum(axis=1)
    if _cache_enabled():
        _cache_set(cache_key, df)
    return df
