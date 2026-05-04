# Filename: analysis/pipeline/av_engine_pipeline.py
# Purpose  : Full pipeline for AV engine evaluation using DB-driven matrices and enrichment for ML training

import pandas as pd
from analysis.matrix import av_binary_matrix_builder
from analysis.matrix import enrich_malicious_scores as enrich_scores
from analysis.pipeline import score_av_engines
from .engine_pipeline_utils import validate_sample_input
from .attach_engine_metadata import attach_engine_metadata
from utils import display_utils as du


def run_av_analysis_pipeline(
    samples_df: pd.DataFrame,
    config: dict = None,
    verbose: bool = True
) -> dict:
    """
    Executes the full AV engine analysis pipeline:
    1. Builds binary detection matrix from sample set.
    2. Enriches matrix with malicious score features.
    3. Resolves engine-level metadata and writes an overlay CSV (not appended as matrix rows).
    4. Computes detection quality tiers and scores for each engine.

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
        enriched_matrix = enrich_scores.apply_score_enrichment(binary_matrix, verbose=verbose)
        if enriched_matrix.empty:
            raise ValueError("Score enrichment returned empty matrix.")
    except Exception as e:
        du.print_error(f"[PIPELINE] Score enrichment stage failed: {e}")
        return {
            "error": f"Score enrichment error: {e}",
            "binary_matrix": binary_matrix,
            "enriched_matrix": None,
            "engine_scores": None
        }

    try:
        enriched_matrix = attach_engine_metadata(enriched_matrix, verbose=verbose)
    except Exception as exc:
        du.print_warning(f"[PIPELINE] Engine metadata attachment failed: {exc}. Continuing without metadata.")
        enriched_matrix = enriched_matrix.copy()

    try:
        engine_scores = score_av_engines.run_av_engine_scoring(
            binary_matrix,
            config=config,
            verbose=verbose
        )
        if engine_scores is None:
            engine_scores = pd.DataFrame()
    except Exception as exc:
        du.print_error(f"[PIPELINE] Engine scoring stage failed: {exc}")
        engine_scores = pd.DataFrame()

    engine_lifecycle = None
    if isinstance(engine_scores, pd.DataFrame):
        engine_lifecycle = engine_scores.attrs.get("engine_lifecycle")

    return {
        "error": None,
        "binary_matrix": binary_matrix,
        "enriched_matrix": enriched_matrix,
        "engine_scores": engine_scores,
        "engine_lifecycle": engine_lifecycle,
    }
