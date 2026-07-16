# Filename: obsidiandroid/features/vectorization/feature_vector_builder.py
# Purpose  : Entry point to construct ML-ready feature matrix using modular components

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
from pandas.api.types import is_numeric_dtype
from pathlib import Path
import hashlib
from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common import output_hygiene as output_hygiene_mod
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from .feature_engine_selection import get_top_engines_by_score
from .feature_encoder import encode_features
from .feature_vendor_extractor import (
    extract_vendor_fields,
    merge_vendor_features
)


def _sample_ids_from_feature_index(index) -> list[int]:
    """Stable integer sample_ids from the encoded matrix index (may be float-like)."""
    out: set[int] = set()
    for v in index:
        try:
            x = float(v)
            if pd.isna(x):
                continue
            i = int(x)
            if float(i) == x:
                out.add(i)
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _resolve_merge_sample_ids(encoded: pd.DataFrame) -> pd.Series:
    """Per-row sample_id for joining extras (prefer column over index).

    After some merges/exports the encoded matrix can keep ``sample_id`` as a normal
    column while the index is a default ``RangeIndex``. Extras must always align on
    ``sample_id`` values, not on positional index.
    """
    if "sample_id" in encoded.columns:
        return encoded["sample_id"]
    return pd.Series(encoded.index, index=encoded.index)


def _extra_column_is_numeric_permission_signal(col: str) -> bool:
    """True for permission-bag / VT-count columns that must never use categorical codes."""
    c = str(col)
    return c.startswith("perm__") or c.startswith("perm_grp__") or c == "meta__permissions"


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory for current runtime context."""
    return resolve_diagnostics_dir()


def _select_top_vendors(
    weights_df,
    top_k,
    score_preference,
    exclude_categories,
    min_score,
    verbose,
):
    """
    Selects the top K antivirus vendors based on scoring criteria.
    """
    try:
        return get_top_engines_by_score(
            weights_df=weights_df,
            top_k=top_k,
            score_preference=score_preference,
            exclude_categories=exclude_categories,
            min_score=min_score,
            verbose=verbose,
            enforce_included_in_model=True,
        )
    except Exception as e:
        du.print_error(f"[BUILD] Vendor ranking failed: {e}")
        return []


def _export_pre_gate_vendor_scores(
    weights_df: pd.DataFrame,
    score_preference: str | None,
    exclude_categories: list | None,
    *,
    verbose: bool,
) -> None:
    """Export top vendor scores before gating for audit/debug transparency."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return
    requested_score_field = str(score_preference or "")
    if requested_score_field not in weights_df.columns:
        return
    score_field = requested_score_field
    if (
        requested_score_field == str(getattr(app_config, "LEAKAGE_SAFE_SCORE_FIELD", "Leakage Safe Score"))
        and "Leakage Safe Score Raw" in weights_df.columns
    ):
        score_field = "Leakage Safe Score Raw"
    name_col = next(
        (c for c in ["engine_name", "vendor", "Vendor"] if c in weights_df.columns),
        None,
    )
    if not name_col:
        return
    frame = weights_df.copy()
    if exclude_categories and "Vendor Category" in frame.columns:
        frame = frame[~frame["Vendor Category"].isin(exclude_categories)].copy()
    frame[score_field] = pd.to_numeric(frame[score_field], errors="coerce")
    frame = frame.dropna(subset=[score_field])
    if frame.empty:
        return
    top = frame.sort_values(score_field, ascending=False).head(10).copy()
    top["rank"] = range(1, len(top) + 1)
    cols = ["rank", name_col, score_field]
    for optional in ("Vendor Category", "Parser Quality Score", "Family Match Accuracy (%)"):
        if optional in top.columns:
            cols.append(optional)
    out = top[cols]
    out_dir = _diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip() or "unknown"
    csv_text = out.to_csv(index=False)
    paths = output_hygiene_mod.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=f"vendor_gate_top10_pre_gate_{rid}.csv",
        csv_text=csv_text,
        global_latest_name="vendor_gate_top10_pre_gate.latest.csv",
    )
    out_path = paths[0]
    if verbose and ml_console.show_debug_tables():
        try:
            du.print_table(out, title="Top 10 vendors by pre-gate score", show_index=False)
        except Exception:
            pass
    if verbose and score_field != requested_score_field:
        du.print_info(
            "[FEATURE BUILD] Pre-gate table uses 'Leakage Safe Score Raw' to surface "
            "vendor ranking signal before parser-gate zeroing."
        )
    if verbose or ml_console.is_debug():
        du.print_info(f"[FEATURE BUILD] Vendor pre-gate scores:{du.format_console_path(out_path)}")


def _prepare_vendor_features(parsed_vendor_data, vendor_list, fields):
    """
    Extracts and merges feature frames from selected vendors.
    """
    feature_frames = extract_vendor_fields(parsed_vendor_data, vendor_list, fields)
    if not feature_frames:
        du.print_error("[BUILD] No vendor fields were successfully extracted.")
        return pd.DataFrame()

    merged = merge_vendor_features(feature_frames)
    if merged.empty:
        du.print_error("[BUILD] Merged feature matrix is empty. Aborting build.")
    return merged


def _filter_vendors_with_parsed_data(
    parsed_vendor_data: dict,
    vendor_list: list[str],
    *,
    verbose: bool,
) -> list[str]:
    """Filter selected vendors to those present in parsed vendor data."""
    if not isinstance(parsed_vendor_data, dict) or not vendor_list:
        return []

    def _normalize_vendor_key(name: str) -> str:
        return (name or "").strip().lower().replace("-", "").replace("_", "")

    normalized_available = {
        _normalize_vendor_key(str(key)) for key in parsed_vendor_data.keys()
    }
    filtered = [
        vendor for vendor in vendor_list
        if _normalize_vendor_key(str(vendor)) in normalized_available
    ]
    missing = [vendor for vendor in vendor_list if vendor not in filtered]
    if missing and verbose:
        preview = ", ".join(missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        du.print_warning(
            "[FEATURE BUILD] Dropping selected vendors missing parsed data: "
            f"{preview}{suffix} (missing={len(missing)})"
        )
    return filtered


def _ensure_min_vendor_selection(
    weights_df: pd.DataFrame,
    selected_vendors: list[str],
    min_required: int,
    top_k: int,
    score_preference: str | None,
    exclude_categories: list | None,
    verbose: bool,
) -> list[str]:
    """Backfill vendor selection when strict score filtering yields too few engines."""
    paper_mode_enabled = bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
    if paper_mode_enabled:
        # Paper cohorts must keep deterministic vendor constraints without fallback widening.
        return selected_vendors

    strict_evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    allow_fallback = bool(getattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", False))
    if not allow_fallback:
        # Vendor widening must be an explicit policy choice.
        return selected_vendors
    if strict_evidence_mode and not allow_fallback:
        # Evidence mode must not relax parser-gate policy via fallback.
        return selected_vendors

    if len(selected_vendors) >= min_required:
        return selected_vendors

    fallback_target = max(min_required, top_k)
    fallback_vendors = get_top_engines_by_score(
        weights_df=weights_df,
        top_k=fallback_target,
        score_preference=score_preference,
        exclude_categories=exclude_categories,
        min_score=None,
        verbose=False,
        enforce_included_in_model=False,
    )
    merged = list(dict.fromkeys([*selected_vendors, *fallback_vendors]))
    if verbose:
        du.print_warning(
            "[FEATURE BUILD] Backfilled vendor set using score-ranked fallback "
            f"without min_score threshold: {len(selected_vendors)} -> {len(merged)}. "
            "This run is using an explicit widened vendor-selection policy."
        )
    return merged[:fallback_target]


def _sorted_int_cohort_ids(cohort_sample_ids: Iterable[Any]) -> list[int]:
    """Stable sorted unique integer sample_ids from a cohort iterable."""
    out: set[int] = set()
    for v in cohort_sample_ids:
        try:
            x = float(v)
            if pd.isna(x):
                continue
            i = int(x)
            if float(i) == x:
                out.add(i)
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _normalize_matrix_sample_id_index(feature_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the matrix is indexed by integer ``sample_id`` (drops redundant column)."""
    df = feature_df.copy()
    attrs = dict(df.attrs)
    if "sample_id" in df.columns:
        sid = pd.to_numeric(df["sample_id"], errors="coerce")
        df = df.drop(columns=["sample_id"])
        df.index = sid.astype("int64")
        df.index.name = "sample_id"
    elif df.index.name not in ("sample_id", None):
        df.index.name = "sample_id"
    elif df.index.name is None:
        df.index.name = "sample_id"
    df.attrs.update(attrs)
    return df


def _unknown_like_code(col: str, encoder_mappings: dict[str, dict[str, int]]) -> int:
    """Category code used for missing vendor rows (matches ``unknown`` fill in encoding)."""
    col_map = encoder_mappings.get(col) or {}
    for key in ("unknown", "Unknown", "UNKNOWN", "none", "None"):
        if key in col_map:
            return int(col_map[key])
    return 0


def _encode_extra_series_raw(
    raw: pd.Series,
    col: str,
    encoder_mappings: dict[str, dict[str, int]],
) -> pd.Series:
    """Encode enrichment-column raw values the same way as :func:`_merge_extra_features`."""
    col_map = encoder_mappings.get(col)
    if col_map:
        def _map_one(v: object) -> float:
            if pd.isna(v):
                return float("nan")
            s = str(v).strip()
            if s in col_map:
                return float(int(col_map[s]))
            if "unknown" in col_map:
                return float(int(col_map["unknown"]))
            if "Unknown" in col_map:
                return float(int(col_map["Unknown"]))
            return float(int(next(iter(col_map.values()))))

        return raw.map(_map_one)
    return pd.to_numeric(raw, errors="coerce")


def _prep_extra_indexed(extra_df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate extras and index by ``sample_id`` (int64)."""
    ex = extra_df.copy()
    if "sample_id" not in ex.columns:
        return pd.DataFrame()
    sid = pd.to_numeric(ex["sample_id"], errors="coerce")
    ex = ex.loc[sid.notna()].copy()
    ex["sample_id"] = sid.loc[sid.notna()].round().astype("int64")
    ex = ex.drop_duplicates("sample_id", keep="first").set_index("sample_id")
    ex.index = ex.index.astype("int64")
    ex.index.name = "sample_id"
    return ex


def _expand_to_cohort_authoritative(
    merged: pd.DataFrame,
    *,
    cohort_sample_ids: Iterable[Any],
    vendor_feature_columns: list[str],
    encoder_mappings: dict[str, dict[str, int]],
    vendor_merge_sample_ids: list[int],
    extra_features_df: pd.DataFrame | None,
    verbose: bool,
) -> pd.DataFrame:
    """Reindex the fused matrix to the governed cohort; zero/unknown-fill vendor-only gaps.

    Permission and metadata columns are refreshed from ``extra_features_df`` for cohort rows that
    were absent from the vendor-merge universe so PI signal is not dropped when vendor parsers fail.
    """
    cohort_list = _sorted_int_cohort_ids(cohort_sample_ids)
    if not cohort_list:
        return merged

    out = _normalize_matrix_sample_id_index(merged)
    cohort_index = pd.Index(cohort_list, dtype="int64", name="sample_id")

    out = out.reindex(cohort_index)

    for col in vendor_feature_columns:
        if col not in out.columns:
            continue
        unk = _unknown_like_code(col, encoder_mappings)
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(unk)

    non_vendor_cols = [c for c in out.columns if c not in vendor_feature_columns]
    ex_idx = _prep_extra_indexed(extra_features_df) if isinstance(extra_features_df, pd.DataFrame) else pd.DataFrame()
    if not ex_idx.empty:
        ex_aligned = ex_idx.reindex(cohort_index)
        for col in non_vendor_cols:
            if col not in ex_aligned.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
                continue
            encoded_fill = _encode_extra_series_raw(ex_aligned[col], col, encoder_mappings)
            base = pd.to_numeric(out[col], errors="coerce")
            out[col] = base.combine_first(encoded_fill).fillna(0)
    else:
        for col in non_vendor_cols:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out.attrs.update(dict(merged.attrs))
    out.attrs["vendor_merge_sample_ids"] = list(vendor_merge_sample_ids)
    out.attrs["vendor_merge_sample_id_count"] = int(len(set(vendor_merge_sample_ids)))
    out.attrs["cohort_governed_sample_id_count"] = int(len(cohort_list))
    out.attrs["cohort_authoritative_row_count"] = int(len(out))
    out.attrs["feature_matrix_row_authority"] = "governed_cohort"
    out.attrs["vendor_feature_column_names"] = list(vendor_feature_columns)

    if verbose:
        du.print_info(
            "[FEATURE BUILD] Cohort-authoritative matrix: "
            f"governed_n={len(cohort_list)} rows × {out.shape[1]} cols; "
            f"vendor_merge_n={len(set(vendor_merge_sample_ids))} "
            "(vendor gaps filled with encoded 'unknown' / 0)."
        )
    return out


def _merge_extra_features(
    encoded: pd.DataFrame,
    extra_df: pd.DataFrame,
    verbose: bool,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """
    Merges additional enriched features into the encoded feature matrix.

    Joins on ``sample_id`` explicitly (column if present, otherwise the frame index).
    Does not assume ``encoded.index`` matches ``extra_df['sample_id']``.
    """
    if not isinstance(extra_df, pd.DataFrame) or extra_df.empty:
        return encoded, {}

    if "sample_id" not in extra_df.columns:
        du.print_warning("[BUILD] Extra feature DataFrame missing 'sample_id' column. Skipping merge.")
        return encoded, {}

    # Reuse the canonical extra-frame preparation used by cohort expansion.
    # It selects and copies once, instead of materializing several nearly
    # identical full enrichment frames during feature alignment.
    extras = _prep_extra_indexed(extra_df)
    # Preserve the historical zero-filled feature columns when every extra
    # row is invalid, but skip the no-op case with no extra columns at all.
    if not len(extras.columns):
        return encoded, {}

    extra_encoder_mappings: dict[str, dict[str, int]] = {}
    for col in extras.columns:
        if _extra_column_is_numeric_permission_signal(col):
            extras[col] = pd.to_numeric(extras[col], errors="coerce").fillna(0)
        elif is_numeric_dtype(extras[col]):
            extras[col] = pd.to_numeric(extras[col], errors="coerce").fillna(0)
        else:
            cat_series = extras[col].astype("category")
            extras[col] = cat_series.cat.codes
            extra_encoder_mappings[col] = {
                str(category): int(code)
                for code, category in enumerate(cat_series.cat.categories.tolist())
            }

    join_keys = pd.to_numeric(_resolve_merge_sample_ids(encoded), errors="coerce")
    aligned = extras.reindex(join_keys.to_numpy())
    aligned = aligned.reset_index(drop=True)

    overlap_cols = [c for c in extras.columns if c in encoded.columns]
    base = encoded.drop(columns=overlap_cols, errors="ignore") if overlap_cols else encoded
    assign_kw = {str(col): aligned[col].to_numpy() for col in extras.columns}
    additions = pd.DataFrame(assign_kw, index=base.index)
    result = pd.concat([base, additions], axis=1).fillna(0)
    # One copy to reduce fragmentation warnings when hundreds of columns are added at once.
    result = result.copy()
    result.attrs.update(dict(encoded.attrs))
    if verbose:
        du.print_debug(f"[BUILD] Added extra features -> new shape: {result.shape}")
    return result, extra_encoder_mappings


def _export_vendor_gate_debug(
    *,
    weights_df: pd.DataFrame,
    selected_vendors: list[str],
    parsed_vendor_data: dict,
    top_vendors_initial: list[str],
) -> str:
    """Export vendor gate debug table and publish runtime vendor set hash."""
    run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    out_dir = _diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    name_col = next((c for c in ["engine_name", "vendor", "Vendor"] if c in weights_df.columns), None)
    if not name_col:
        rows = []
    else:
        frame = weights_df.copy()
        frame[name_col] = frame[name_col].astype(str)
        rows = frame.to_dict(orient="records")

    parsed_keys_norm = {
        (str(key).strip().lower().replace("-", "").replace("_", "")): str(key)
        for key in (parsed_vendor_data.keys() if isinstance(parsed_vendor_data, dict) else [])
    }
    selected_set = set(selected_vendors)
    initial_set = set(top_vendors_initial)
    debug_rows: list[dict[str, object]] = []
    for record in rows:
        vendor = str(record.get(name_col, ""))
        vendor_norm = vendor.strip().lower().replace("-", "").replace("_", "")
        parsed_available = vendor_norm in parsed_keys_norm
        selected = vendor in selected_set
        fallback_flag = (vendor in selected_set) and (vendor not in initial_set)
        reason = ""
        if not parsed_available:
            reason = "missing_parsed_data"
        elif not selected:
            reason = "not_selected"
        debug_rows.append(
            {
                "vendor": vendor,
                "selected_flag": int(selected),
                "fallback_flag": int(fallback_flag),
                "parsed_available": int(parsed_available),
                "gate_reason": reason,
                "pre_gate_score_raw": record.get("Leakage Safe Score Raw", record.get("Leakage Safe Score", "")),
                "post_gate_score": record.get("Leakage Safe Score", ""),
                "vendor_category": record.get("Vendor Category", ""),
            }
        )

    debug_df = pd.DataFrame(debug_rows)
    if not debug_df.empty:
        debug_df = debug_df.sort_values(["selected_flag", "pre_gate_score_raw"], ascending=[False, False])
    path = out_dir / f"vendor_gate_debug_{run_id}.csv"
    output_hygiene_mod.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=path.name,
        csv_text=debug_df.to_csv(index=False),
        global_latest_name="vendor_gate_debug.latest.csv",
    )

    vendor_canonical = "\n".join(sorted(set(map(str, selected_vendors))))
    vendor_set_hash = hashlib.sha256(vendor_canonical.encode("utf-8")).hexdigest()
    setattr(app_config, "RUNTIME_VENDOR_SET_HASH", vendor_set_hash)
    setattr(app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", str(path))
    return str(path)


def build_feature_vector(
    weights_df: pd.DataFrame,
    parsed_vendor_data: dict,
    top_k: int = 10,
    score_preference: str = None,
    exclude_categories: list = None,
    min_score: float | None = None,
    include_fields: list = None,
    encoding: str = "category",
    verbose: bool = True,
    extra_features_df: pd.DataFrame | None = None,
    cohort_sample_ids: Iterable[Any] | None = None,
) -> pd.DataFrame:
    """
    Constructs an ML-ready feature matrix by:
      1. Selecting top antivirus engines
      2. Extracting and merging vendor field data
      3. Encoding categorical features
      4. Optionally enriching with external features
    """
    from obsidiandroid.evaluation.ml_terminal_presentation import should_suppress_ablation_feature_build_terminal

    suppress_build_terminal = should_suppress_ablation_feature_build_terminal()
    if suppress_build_terminal:
        verbose = False
    elif verbose or ml_console.is_debug():
        du.print_section("[FEATURE BUILD] Constructing AV-based ML Feature Matrix")
    elif ml_console.is_compact():
        du.print_info("[FEATURE BUILD] Building AV feature matrix...")

    # An omitted field list is a safe contract: retain binary/consensus
    # enrichment but do not add lexical vendor labels.  Label-derived fields
    # must be supplied explicitly by a scoped ablation or experiment.
    fields = list(include_fields or [])
    requested_top_k = int(top_k)
    min_selected_vendors = safe_int_config_value(
        getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1), default=1
    )
    fail_on_low_vendor_count = bool(
        getattr(app_config, "FEATURE_FAIL_ON_LOW_VENDOR_COUNT", False)
    )
    strict_evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    allow_fallback = bool(getattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", False))
    allow_adaptive_top_k = bool(getattr(app_config, "ALLOW_ADAPTIVE_TOP_K", False))

    # Step 1: Vendor Selection
    _export_pre_gate_vendor_scores(
        weights_df=weights_df,
        score_preference=score_preference,
        exclude_categories=exclude_categories,
        verbose=bool(verbose),
    )
    top_vendors = _select_top_vendors(
        weights_df,
        top_k,
        score_preference,
        exclude_categories,
        min_score,
        verbose,
    )
    top_vendors_initial = list(top_vendors)
    if not top_vendors:
        if strict_evidence_mode and not allow_fallback:
            du.print_error(
                "[FEATURE BUILD] Evidence mode violation: no vendors selected after parser-gate filtering."
            )
            return pd.DataFrame()
        top_vendors = _ensure_min_vendor_selection(
            weights_df=weights_df,
            selected_vendors=[],
            min_required=max(min_selected_vendors, 1),
            top_k=top_k,
            score_preference=score_preference,
            exclude_categories=exclude_categories,
            verbose=verbose,
        )
        top_vendors = _filter_vendors_with_parsed_data(
            parsed_vendor_data=parsed_vendor_data,
            vendor_list=top_vendors,
            verbose=verbose,
        )
        if not top_vendors:
            du.print_error("[FEATURE BUILD] No vendors remain after fallback recovery.")
            return pd.DataFrame()
        if verbose and not ml_console.is_compact():
            du.print_warning(
                "[FEATURE BUILD] Recovered from empty parser-gated selection using fallback vendors."
            )

    if strict_evidence_mode and len(top_vendors) < requested_top_k and not allow_fallback:
        du.print_error(
            "[FEATURE BUILD] Evidence mode violation: "
            f"included_clean_engines={len(top_vendors)} < top_k={requested_top_k}."
        )
        return pd.DataFrame()
    if len(top_vendors) < min_selected_vendors:
        top_vendors = _ensure_min_vendor_selection(
            weights_df=weights_df,
            selected_vendors=top_vendors,
            min_required=min_selected_vendors,
            top_k=top_k,
            score_preference=score_preference,
            exclude_categories=exclude_categories,
            verbose=verbose,
        )
        top_vendors = _filter_vendors_with_parsed_data(
            parsed_vendor_data=parsed_vendor_data,
            vendor_list=top_vendors,
            verbose=verbose,
        )
        if len(top_vendors) < min_selected_vendors:
            message = (
                f"[FEATURE BUILD] Selected vendors below minimum: "
                f"{len(top_vendors)} < {min_selected_vendors}. "
                f"top_k={top_k}, min_score={min_score}, vendors={top_vendors}"
            )
            if strict_evidence_mode or fail_on_low_vendor_count:
                du.print_error(message)
                return pd.DataFrame()
            du.print_warning(message)
    else:
        top_vendors = _filter_vendors_with_parsed_data(
            parsed_vendor_data=parsed_vendor_data,
            vendor_list=top_vendors,
            verbose=verbose,
        )
        if len(top_vendors) < min_selected_vendors:
            message = (
                "[FEATURE BUILD] Selected vendors dropped below minimum after parsed-data filtering: "
                f"{len(top_vendors)} < {min_selected_vendors}. vendors={top_vendors}"
            )
            if strict_evidence_mode or fail_on_low_vendor_count:
                du.print_error(message)
                return pd.DataFrame()
            du.print_warning(message)
    if strict_evidence_mode and len(top_vendors) < requested_top_k and not allow_fallback:
        du.print_error(
            "[FEATURE BUILD] Evidence mode violation after parsed-data filtering: "
            f"included_clean_engines={len(top_vendors)} < top_k={requested_top_k}."
        )
        return pd.DataFrame()

    # Step 2: Feature Extraction + Merging
    _export_vendor_gate_debug(
        weights_df=weights_df if isinstance(weights_df, pd.DataFrame) else pd.DataFrame(),
        selected_vendors=top_vendors,
        parsed_vendor_data=parsed_vendor_data if isinstance(parsed_vendor_data, dict) else {},
        top_vendors_initial=top_vendors_initial,
    )
    merged = _prepare_vendor_features(parsed_vendor_data, top_vendors, fields)
    if merged.empty:
        return pd.DataFrame()

    # Step 3: Feature Encoding.  A safe headline contract may intentionally
    # contain no lexical vendor fields; keep its sample index so permission and
    # numeric AV-consensus enrichment can form the final matrix.
    if fields:
        encoded = encode_features(merged, encoding=encoding, verbose=verbose, skip_numeric=True)
    else:
        sample_ids = pd.to_numeric(merged["sample_id"], errors="coerce")
        sample_ids = sample_ids[sample_ids.notna()].round().astype("int64")
        encoded = pd.DataFrame(index=pd.Index(sample_ids, name="sample_id"))
        encoded.attrs["encoder_mappings"] = {}
    if len(encoded.index) == 0:
        du.print_error("[BUILD] Final encoded matrix is empty.")
        return pd.DataFrame()

    vendor_feature_columns = [c for c in encoded.columns if c != "sample_id"]

    # Row authority: sample_ids used for vendor rows (same keys used for extras join).
    _merge_ids = _resolve_merge_sample_ids(encoded)
    encoded.attrs["vendor_merge_sample_ids"] = _sample_ids_from_feature_index(
        pd.Index(_merge_ids.dropna())
    )
    encoded.attrs["vendor_merge_sample_id_count"] = int(len(encoded.index))

    # Step 4: Feature Enrichment (optional)
    encoded, extra_encoder_mappings = _merge_extra_features(encoded, extra_features_df, verbose)

    combined_mappings = dict(encoded.attrs.get("encoder_mappings", {}))
    combined_mappings.update(extra_encoder_mappings)
    encoded.attrs["encoder_mappings"] = combined_mappings

    vendor_merge_ids = list(encoded.attrs.get("vendor_merge_sample_ids") or [])
    if cohort_sample_ids is not None:
        cohort_list = _sorted_int_cohort_ids(cohort_sample_ids)
        if cohort_list:
            encoded = _expand_to_cohort_authoritative(
                encoded,
                cohort_sample_ids=cohort_list,
                vendor_feature_columns=vendor_feature_columns,
                encoder_mappings=combined_mappings,
                vendor_merge_sample_ids=vendor_merge_ids,
                extra_features_df=extra_features_df,
                verbose=verbose,
            )
            combined_mappings = dict(encoded.attrs.get("encoder_mappings", {}))
    encoded.attrs["selected_vendors"] = list(top_vendors)
    encoded.attrs["include_fields"] = list(fields)
    encoded.attrs["feature_build_encoding"] = str(encoding)
    effective_top_k = int(len(top_vendors))
    if allow_adaptive_top_k and effective_top_k < requested_top_k:
        if verbose and not ml_console.is_compact():
            du.print_warning(
                "[FEATURE BUILD] Adaptive top-k active: "
                f"requested_k={requested_top_k}, effective_k={effective_top_k}."
            )
    else:
        effective_top_k = int(requested_top_k)
    encoded.attrs["feature_top_k"] = int(requested_top_k)
    encoded.attrs["feature_effective_top_k"] = int(effective_top_k)
    fallback_added_count = len(set(top_vendors) - set(top_vendors_initial))
    fallback_used = fallback_added_count > 0
    selection_policy = (
        "explicit_widening" if fallback_used else "parser_gated_only"
    )
    encoded.attrs["vendor_fallback_used"] = bool(fallback_used)
    encoded.attrs["vendor_fallback_added_count"] = int(fallback_added_count)
    encoded.attrs["vendor_selection_policy"] = selection_policy
    setattr(app_config, "RUNTIME_VENDOR_FALLBACK_USED", bool(fallback_used))
    setattr(app_config, "RUNTIME_VENDOR_FALLBACK_ADDED_COUNT", int(fallback_added_count))
    setattr(app_config, "RUNTIME_VENDOR_SELECTION_POLICY", selection_policy)
    setattr(app_config, "RUNTIME_K_REQUESTED", int(requested_top_k))
    setattr(app_config, "RUNTIME_EFFECTIVE_TOP_K", int(effective_top_k))
    non_standard_features = bool(
        fallback_used
        or (effective_top_k < requested_top_k)
        or bool(getattr(app_config, "RUNTIME_EVIDENCE_OVERRIDE_USED", False))
    )
    setattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", non_standard_features)
    encoded.attrs["non_standard_features"] = non_standard_features
    if strict_evidence_mode and fallback_used and not allow_fallback:
        du.print_error(
            "[FEATURE BUILD] Evidence mode violation: vendor fallback required to satisfy feature width."
        )
        return pd.DataFrame()
    if strict_evidence_mode and fallback_used and allow_fallback:
        du.print_warning(
            "[FEATURE BUILD] Non-standard evidence run: vendor fallback override enabled."
        )
    if isinstance(weights_df, pd.DataFrame):
        encoded.attrs["feature_score_field"] = str(score_preference or "")

    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)) and not ml_console.is_debug():
        return encoded
    if ml_console.is_compact():
        selected_count = len(top_vendors)
        du.print_success(
            "[BUILD] Final Feature Matrix - "
            f"{encoded.shape[0]} samples x {encoded.shape[1]} features "
            f"| selected_vendors={selected_count} | effective_top_k={effective_top_k}"
        )
    elif verbose or ml_console.is_research() or ml_console.is_debug():
        du.print_success(
            f"[BUILD] Final Feature Matrix - {encoded.shape[0]} samples x {encoded.shape[1]} features"
        )
    return encoded
