import pandas as pd
from config import app_config
from obsidiandroid.feature_engineering.compute_vendor_scores import (
    print_debug_top_vendors,
    run_score_analysis,
    print_score_distribution,
)
from obsidiandroid.feature_engineering import compute_vendor_scores


def _sample_df():
    return pd.DataFrame({
        "Vendor": ["a", "b"],
        "Enrichment Score": [50, 60],
        "Family Match Accuracy (%)": [70, 80],
        "Detection Diversity": [10, 12],
        "Unknown Parsed (%)": [5, 10],
        "Unique Labels": [15, 20],
        "Generic Family Ratio": [0.1, 0.2],
        "Avg Genericity Score": [5, 10],
    })


def test_run_score_analysis_basic():
    df = _sample_df()
    scored = run_score_analysis(df, verbose=False)
    assert "Final ML Score" in scored.columns
    assert len(scored) == 2


def test_print_score_distribution_no_error(capsys):
    df = run_score_analysis(_sample_df(), verbose=False)
    print_score_distribution(df)
    captured = capsys.readouterr()
    assert "Score Distribution" in captured.out


def test_print_debug_top_vendors_compact_emits_single_summary_line(monkeypatch):
    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(app_config, "ML_CONSOLE_MODE", "research", raising=False)
    captured: list[str] = []
    monkeypatch.setattr(compute_vendor_scores.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(compute_vendor_scores.du, "print_section", lambda *_a, **_k: captured.append("section"))
    monkeypatch.setattr(compute_vendor_scores.du, "print_table", lambda *_a, **_k: captured.append("table"))

    df = run_score_analysis(_sample_df(), verbose=False)
    print_debug_top_vendors(df)

    assert any("Top vendors by Final ML Score" in msg for msg in captured)
    assert "section" not in captured
    assert "table" not in captured


def test_compute_leakage_safe_score_excludes_non_included_vendors() -> None:
    """Leakage safe scoring should zero-out vendors excluded from model inputs."""
    df = pd.DataFrame(
        {
            "Vendor": ["a", "b"],
            "Enrichment Score": [10.0, 10.0],
            "Family Match Accuracy (%)": [10.0, 10.0],
            "Detection Diversity": [5.0, 8.0],
            "Unknown Parsed (%)": [10.0, 10.0],
            "Unique Labels": [20, 20],
            "Generic Family Ratio": [0.1, 0.1],
            "Avg Genericity Score": [0.2, 0.2],
            "Final ML Score": [0.4, 0.4],
            "unknown_ratio": [0.1, 0.1],
            "generic_ratio": [0.1, 0.1],
            "entropy": [0.6, 0.6],
            "included_in_model": [1, 0],
        }
    )

    out = compute_vendor_scores.compute_leakage_safe_score(df.copy())
    assert "Leakage Safe Score" in out.columns
    assert "Leakage Safe Score Raw" in out.columns
    assert out.loc[out["Vendor"] == "b", "Leakage Safe Score Raw"].iloc[0] > 0
    assert out.loc[out["Vendor"] == "a", "Leakage Safe Score"].iloc[0] > 0
    assert out.loc[out["Vendor"] == "b", "Leakage Safe Score"].iloc[0] == 0.0
