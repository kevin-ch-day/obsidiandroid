# Filename: ml_classification/vectorization/feature_vector_builder.py
# Purpose  : Entry point to construct ML-ready feature matrix using modular components

import pandas as pd
from pandas.api.types import is_numeric_dtype
from pathlib import Path
import hashlib
from config import app_config
from utils import display_utils as du
from utils import ml_console
from .feature_engine_selection import get_top_engines_by_score
from .feature_encoder import encode_features
from .feature_vendor_extractor import (
    extract_vendor_fields,
    merge_vendor_features
)


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory for current runtime context."""
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_dir:
        return Path(runtime_dir)
    return Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics"


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
    out_path = out_dir / "vendor_gate_top10_pre_gate.latest.csv"
    out.to_csv(out_path, index=False)
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
        du.print_info(f"[FEATURE BUILD] Vendor pre-gate scores exported: {out_path}")


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


def _merge_extra_features(
    encoded: pd.DataFrame,
    extra_df: pd.DataFrame,
    verbose: bool,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """
    Merges additional enriched features into the encoded feature matrix.
    """
    if not isinstance(extra_df, pd.DataFrame) or extra_df.empty:
        return encoded, {}

    if "sample_id" not in extra_df.columns:
        du.print_warning("[BUILD] Extra feature DataFrame missing 'sample_id' column. Skipping merge.")
        return encoded, {}

    extras = (
        extra_df.drop_duplicates("sample_id")
        .set_index("sample_id")
        .copy()
    )

    extra_encoder_mappings: dict[str, dict[str, int]] = {}
    for col in extras.columns:
        if is_numeric_dtype(extras[col]):
            extras[col] = pd.to_numeric(extras[col], errors="coerce").fillna(0)
        else:
            cat_series = extras[col].astype("category")
            extras[col] = cat_series.cat.codes
            extra_encoder_mappings[col] = {
                str(category): int(code)
                for code, category in enumerate(cat_series.cat.categories.tolist())
            }

    result = encoded.join(extras, how="left").fillna(0)
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
    latest = out_dir / "vendor_gate_debug.latest.csv"
    debug_df.to_csv(path, index=False)
    debug_df.to_csv(latest, index=False)

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
) -> pd.DataFrame:
    """
    Constructs an ML-ready feature matrix by:
      1. Selecting top antivirus engines
      2. Extracting and merging vendor field data
      3. Encoding categorical features
      4. Optionally enriching with external features
    """
    if verbose or ml_console.is_debug():
        du.print_section("[FEATURE BUILD] Constructing AV-based ML Feature Matrix")

    fields = include_fields or ["Parsed Family", "Threat Class", "Malware Type"]
    requested_top_k = int(top_k)
    min_selected_vendors = int(getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1))
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
        if verbose:
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

    # Step 3: Feature Encoding
    encoded = encode_features(merged, encoding=encoding, verbose=verbose, skip_numeric=True)
    if encoded.empty:
        du.print_error("[BUILD] Final encoded matrix is empty.")
        return pd.DataFrame()

    # Step 4: Feature Enrichment (optional)
    encoded, extra_encoder_mappings = _merge_extra_features(encoded, extra_features_df, verbose)

    combined_mappings = dict(encoded.attrs.get("encoder_mappings", {}))
    combined_mappings.update(extra_encoder_mappings)
    encoded.attrs["encoder_mappings"] = combined_mappings
    encoded.attrs["selected_vendors"] = list(top_vendors)
    encoded.attrs["include_fields"] = list(fields)
    encoded.attrs["feature_build_encoding"] = str(encoding)
    effective_top_k = int(len(top_vendors))
    if allow_adaptive_top_k and effective_top_k < requested_top_k:
        if verbose:
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

    if verbose or ml_console.is_research() or ml_console.is_debug():
        du.print_success(
            f"[BUILD] Final Feature Matrix - {encoded.shape[0]} samples x {encoded.shape[1]} features"
        )
    return encoded
