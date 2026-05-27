"""Tests for evaluation console reporting semantics."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.evaluation import ml_report_builder


def test_print_evaluation_summary_surfaces_macro_metrics_and_uses_macro_f1_for_tier(
    monkeypatch, capsys
):
    df = pd.DataFrame(
        [
            {
                "Rank": 1,
                "Family": "Irata",
                "Precision": 0.90,
                "Recall": 0.80,
                "F1-Score": 0.85,
                "Support": 20,
                "Status": "T3 - Strong (85-89%)",
            }
        ]
    )

    infos: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(ml_report_builder.du, "print_info", lambda msg: infos.append(str(msg)))
    monkeypatch.setattr(ml_report_builder.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(ml_report_builder.du, "print_error", lambda msg: errors.append(str(msg)))

    ml_report_builder.print_evaluation_summary(
        df=df,
        acc=0.80,
        prec=0.90,
        recall=0.80,
        f1=0.84,
        macro_prec=0.40,
        macro_recall=0.35,
        macro_f1=0.32,
    )

    out = capsys.readouterr().out
    assert "Macro Prec" in out
    assert "Macro Recall" in out
    assert "Macro F1" in out
    assert "Weighted F1 across families" in out
    assert any(msg.startswith("T10 - Critically Weak") for msg in warnings)
    assert any("Model-quality failure on evaluation" in msg for msg in warnings)
    assert not errors
