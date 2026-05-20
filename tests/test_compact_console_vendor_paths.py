"""Compact-mode console behavior for vendor-analysis helper entrypoints."""

from __future__ import annotations

import pandas as pd

from config import app_config
from obsidiandroid.evaluation import av_results_fetcher
from obsidiandroid.evaluation import evaluate_av_classifications
from obsidiandroid.evaluation import vendor_feature_extractor
from obsidiandroid.pipeline import vendor_metadata_pipeline


def test_fetch_av_results_compact_uses_single_info_line(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        av_results_fetcher.db_fetch_av_engine_raw_results,
        "fetch_av_engine_results_for_samples",
        lambda *_args, **_kwargs: pd.DataFrame({"sample_id": [1], "engine_a": [1]}),
    )
    captured: list[str] = []
    monkeypatch.setattr(av_results_fetcher.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(av_results_fetcher.du, "print_section", lambda *_a, **_k: captured.append("section"))

    out = av_results_fetcher.fetch_av_results(pd.DataFrame({"sample_id": [1]}), verbose=False)

    assert not out.empty
    assert "section" not in captured
    assert any("Loading AV engine results" in msg for msg in captured)


def test_run_vendor_classification_analysis_compact_avoids_section(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        evaluate_av_classifications,
        "parse_vendor_classifications",
        lambda **_kwargs: (
            {"vendor_a": pd.DataFrame()},
            pd.DataFrame({"Vendor": ["vendor_a"], "Final ML Score": [0.5]}),
            {"vendor_a": [{}]},
            pd.DataFrame({"sample_id": [1]}),
        ),
    )
    monkeypatch.setattr(
        evaluate_av_classifications.inspector,
        "print_summary_table",
        lambda *_args, **_kwargs: None,
    )
    captured: list[str] = []
    monkeypatch.setattr(evaluate_av_classifications.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(evaluate_av_classifications.du, "print_section", lambda *_a, **_k: captured.append("section"))

    result = evaluate_av_classifications.run_vendor_classification_analysis(
        samples_df=pd.DataFrame({"sample_id": [1]}),
        engine_metadata={},
        export=False,
        verbose=False,
    )

    assert result["summary_df"].shape[0] == 1
    assert "section" not in captured
    assert any("Running vendor classification analysis" in msg for msg in captured)


def test_extract_vendor_metadata_compact_suppresses_extra_headers(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(
        vendor_metadata_pipeline,
        "_validate_inputs",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        vendor_metadata_pipeline,
        "_perform_vendor_extraction",
        lambda *_args, **_kwargs: (
            pd.DataFrame({"Vendor": ["vendor_a"], "Enrichment Score": [1.0]}),
            {"vendor_a": [{}]},
            {"vendor_a": pd.DataFrame()},
            pd.DataFrame({"Final ML Score": [0.5]}),
        ),
    )
    monkeypatch.setattr(vendor_metadata_pipeline, "_print_diagnostics", lambda *_a, **_k: None)
    monkeypatch.setattr(vendor_metadata_pipeline, "_check_dataframe_structure", lambda *_a, **_k: None)
    monkeypatch.setattr(vendor_metadata_pipeline, "_inject_pipeline_state", lambda pipeline_results, vendor_eval_df: pipeline_results.setdefault("vendor_eval_df", vendor_eval_df))
    monkeypatch.setattr(vendor_metadata_pipeline, "_export_parser_quality", lambda *_a, **_k: None)

    captured: list[str] = []
    monkeypatch.setattr(vendor_metadata_pipeline.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(vendor_metadata_pipeline.du, "print_subheader", lambda *_a, **_k: captured.append("subheader"))

    pipeline_results: dict[str, object] = {}
    result = vendor_metadata_pipeline.extract_vendor_metadata(
        pipeline_results=pipeline_results,
        samples_df=pd.DataFrame({"sample_id": [1]}),
        verbose=False,
    )

    assert result[0] is not None
    assert "subheader" not in captured
    assert any("Extracting vendor metadata and parser diagnostics" in msg for msg in captured)


def test_vendor_feature_extractor_compact_uses_subheader_not_banner(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    monkeypatch.setattr(vendor_feature_extractor, "_is_valid_pipeline_input", lambda *_a, **_k: True)
    monkeypatch.setattr(vendor_feature_extractor, "_export_pipeline_results", lambda *_a, **_k: None)
    monkeypatch.setattr(vendor_feature_extractor, "_generate_engine_metadata_map", lambda *_a, **_k: {})
    monkeypatch.setattr(
        vendor_feature_extractor,
        "_execute_vendor_classification",
        lambda *_a, **_k: {
            "summary_df": pd.DataFrame({"Vendor": ["vendor_a"], "Final ML Score": [0.5]}),
            "records_by_vendor": {"vendor_a": [{}]},
            "parsed_data": {"vendor_a": pd.DataFrame()},
        },
    )
    monkeypatch.setattr(
        vendor_feature_extractor,
        "_finalize_extraction_output",
        lambda *_a, **_k: (
            pd.DataFrame({"Vendor": ["vendor_a"], "Final ML Score": [0.5]}),
            {"vendor_a": [{}]},
            {"vendor_a": pd.DataFrame()},
            pd.DataFrame({"Vendor": ["vendor_a"], "Final ML Score": [0.5]}),
        ),
    )

    captured: list[str] = []
    monkeypatch.setattr(vendor_feature_extractor.du, "print_subheader", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(vendor_feature_extractor.du, "print_banner", lambda *_a, **_k: captured.append("banner"))
    monkeypatch.setattr(vendor_feature_extractor.du, "print_warning", lambda *_a, **_k: None)

    out = vendor_feature_extractor.extract_vendor_feature_metadata(
        av_pipeline_results={"enriched_matrix": pd.DataFrame({"sample_id": [1]})},
        samples_df=pd.DataFrame({"sample_id": [1]}),
        verbose=False,
    )

    assert out[0] is not None
    assert "banner" not in captured
    assert "Vendor Feature Extraction" in captured
