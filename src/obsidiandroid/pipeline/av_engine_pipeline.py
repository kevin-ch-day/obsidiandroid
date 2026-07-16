# Filename: obsidiandroid/pipeline/av_engine_pipeline.py
# Purpose  : Full pipeline for AV engine evaluation using DB-driven matrices and enrichment for ML training
#
# Canonical AV-engine pipeline helpers.

import pandas as pd
from config import app_config
from obsidiandroid.matrix import av_binary_matrix_builder
from obsidiandroid.matrix import enrich_malicious_scores as enrich_scores
from obsidiandroid.pipeline.engine_pipeline_utils import validate_sample_input
from obsidiandroid.pipeline.attach_engine_metadata import attach_engine_metadata
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name
from obsidiandroid.pipeline.score_av_engines import run_av_engine_scoring
from obsidiandroid.cli.ui import display as du


_AV_BINARY_FEATURE_ENGINE_SCOPES = frozenset({"all_observed", "lifecycle_included"})


def resolve_binary_feature_engine_scope(config: dict | None = None) -> str:
    """Return the declared binary-AV feature scope with a safe baseline default."""
    configured = (config or {}).get(
        "binary_feature_engine_scope",
        getattr(app_config, "AV_BINARY_FEATURE_ENGINE_SCOPE", "all_observed"),
    )
    scope = str(configured or "all_observed").strip().lower()
    if scope not in _AV_BINARY_FEATURE_ENGINE_SCOPES:
        allowed = ", ".join(sorted(_AV_BINARY_FEATURE_ENGINE_SCOPES))
        raise ValueError(
            "Invalid binary_feature_engine_scope="
            f"{configured!r}; expected one of: {allowed}."
        )
    return scope


def apply_binary_feature_engine_scope(
    binary_matrix: pd.DataFrame,
    engine_lifecycle: pd.DataFrame | None,
    *,
    scope: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Apply a declared engine-column policy after lifecycle scoring.

    The readiness score is computed from the full observed matrix in both
    modes.  The scope only controls which binary verdict columns are then
    exposed to enrichment and training.  This keeps the historical
    ``all_observed`` surface bit-for-bit equivalent in column membership while
    allowing a reproducible lifecycle-gated experiment.
    """
    if not isinstance(binary_matrix, pd.DataFrame) or binary_matrix.empty:
        raise ValueError("Cannot apply AV feature scope to an empty binary matrix.")
    if "sample_id" not in binary_matrix.columns:
        raise ValueError("AV binary matrix is missing required sample_id column.")

    engine_columns = [str(col) for col in binary_matrix.columns if str(col) != "sample_id"]
    included_canonical: set[str] = set()
    if isinstance(engine_lifecycle, pd.DataFrame) and not engine_lifecycle.empty:
        required = {"engine_name_canonical", "included_in_model_flag"}
        if required.issubset(engine_lifecycle.columns):
            included_canonical = {
                canonicalize_engine_name(name)
                for name in engine_lifecycle.loc[
                    engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool),
                    "engine_name_canonical",
                ].tolist()
                if canonicalize_engine_name(name)
            }

    if scope == "all_observed":
        selected_columns = engine_columns
    else:
        if not included_canonical:
            raise ValueError(
                "lifecycle_included AV feature scope requires lifecycle rows with "
                "engine_name_canonical and included_in_model_flag."
            )
        selected_columns = [
            column
            for column in engine_columns
            if canonicalize_engine_name(column) in included_canonical
        ]
        if not selected_columns:
            raise ValueError(
                "lifecycle_included AV feature scope selected zero binary engine columns."
            )

    scoped = binary_matrix.loc[:, ["sample_id", *selected_columns]].copy()
    scoped.attrs.update(dict(binary_matrix.attrs))
    scan_counts = dict(binary_matrix.attrs.get("engine_scan_counts", {}) or {})
    scoped.attrs["engine_scan_counts"] = {
        key: value for key, value in scan_counts.items() if str(key) in selected_columns
    }
    contract = {
        "binary_feature_engine_scope": scope,
        "observed_binary_engine_columns": int(len(engine_columns)),
        "selected_binary_engine_columns": int(len(selected_columns)),
        "lifecycle_included_engine_count": int(len(included_canonical)),
        "excluded_binary_engine_columns": int(len(engine_columns) - len(selected_columns)),
    }
    scoped.attrs["av_binary_feature_scope_contract"] = dict(contract)
    return scoped, contract


def run_av_analysis_pipeline(
    samples_df: pd.DataFrame,
    config: dict = None,
    verbose: bool = True
) -> dict:
    """
    Executes the full AV engine analysis pipeline:
    1. Builds binary detection matrix from sample set.
    2. Computes detection quality tiers and scores for each observed engine.
    3. Applies the declared binary-engine feature scope.
    4. Enriches the scoped matrix and resolves engine-level metadata (the
       overlay remains separate from matrix rows).

    Args:
        samples_df (pd.DataFrame): Input malware sample metadata with 'sample_id' column.
        config (dict, optional): Configuration parameters for scoring engines.
        verbose (bool): Enable diagnostic output.

    Returns:
        dict: {
            "error": str | None,
            "binary_matrix": pd.DataFrame,
            "enriched_matrix": pd.DataFrame,
            "engine_scores": pd.DataFrame
        }
    """
    if not validate_sample_input(samples_df):
        return {
            "error": "Invalid sample input (missing 'sample_id' or empty DataFrame)",
            "binary_matrix": None,
            "enriched_matrix": None,
            "engine_scores": None
        }

    try:
        binary_matrix = av_binary_matrix_builder.generate_binary_detection_matrix(samples_df, verbose=verbose)
        if binary_matrix.empty:
            raise ValueError("Binary matrix is empty after generation.")
    except Exception as e:
        du.print_error(f"[PIPELINE] Binary matrix stage failed: {e}")
        return {
            "error": f"Binary matrix error: {e}",
            "binary_matrix": None,
            "enriched_matrix": None,
            "engine_scores": None
        }

    try:
        engine_scores = run_av_engine_scoring(
            binary_matrix,
            config=config,
            verbose=verbose
        )
        if engine_scores is None:
            engine_scores = pd.DataFrame()
    except Exception as exc:
        err_type = exc.__class__.__name__
        du.print_error(f"[PIPELINE] Engine scoring stage failed ({err_type}): {exc}")
        return {
            "error": f"Engine scoring error ({err_type}): {exc}",
            "binary_matrix": binary_matrix,
            "enriched_matrix": None,
            "engine_scores": None,
            "engine_lifecycle": None,
        }

    engine_lifecycle = None
    if isinstance(engine_scores, pd.DataFrame):
        engine_lifecycle = engine_scores.attrs.get("engine_lifecycle")

    try:
        feature_scope = resolve_binary_feature_engine_scope(config)
        binary_matrix, feature_scope_contract = apply_binary_feature_engine_scope(
            binary_matrix,
            engine_lifecycle,
            scope=feature_scope,
        )
        if verbose:
            du.print_stat(
                "AV Binary Feature Scope",
                (
                    f"{feature_scope}: "
                    f"{feature_scope_contract['selected_binary_engine_columns']}/"
                    f"{feature_scope_contract['observed_binary_engine_columns']} engine columns"
                ),
            )
    except Exception as exc:
        du.print_error(f"[PIPELINE] AV feature-scope application failed: {exc}")
        return {
            "error": f"AV feature-scope error: {exc}",
            "binary_matrix": binary_matrix,
            "enriched_matrix": None,
            "engine_scores": engine_scores,
            "engine_lifecycle": engine_lifecycle,
        }

    try:
        enriched_matrix = enrich_scores.apply_score_enrichment(binary_matrix, verbose=verbose)
        if enriched_matrix.empty:
            raise ValueError("Score enrichment returned empty matrix.")
    except Exception as e:
        du.print_error(f"[PIPELINE] Score enrichment stage failed: {e}")
        return {
            "error": f"Score enrichment error: {e}",
            "binary_matrix": binary_matrix,
            "enriched_matrix": None,
            "engine_scores": engine_scores,
            "engine_lifecycle": engine_lifecycle,
            "av_binary_feature_scope_contract": feature_scope_contract,
        }

    try:
        enriched_matrix = attach_engine_metadata(enriched_matrix, verbose=verbose)
    except Exception as exc:
        du.print_warning(f"[PIPELINE] Engine metadata attachment failed: {exc}. Continuing without metadata.")
        enriched_matrix = enriched_matrix.copy()

    return {
        "error": None,
        "binary_matrix": binary_matrix,
        "enriched_matrix": enriched_matrix,
        "engine_scores": engine_scores,
        "engine_lifecycle": engine_lifecycle,
        "av_binary_feature_scope_contract": feature_scope_contract,
    }
