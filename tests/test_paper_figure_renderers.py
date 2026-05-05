"""Tests for strict paper export figure helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image

from obsidiandroid.pipeline.manifest import paper_figure_renderers as pfr


def test_annotate_confusion_matrix_strips_csv_headers(tmp_path: Path) -> None:
    """Spaced column names from CSV exports must still resolve (Excel-friendly)."""
    csv_path = tmp_path / "m.csv"
    csv_path.write_text(
        " Model , MacroF1 , Acc , F1-Score \nrf,0.9,0.91,0.88\n",
        encoding="utf-8",
    )
    png_path = tmp_path / "cm.png"
    Image.new("RGB", (80, 80), color=(200, 200, 200)).save(png_path)
    assert pfr.annotate_confusion_matrix_with_metrics(
        confusion_path=png_path,
        model_comparison_csv=csv_path,
    )


def test_annotate_confusion_matrix_without_weighted_f1_column(tmp_path: Path) -> None:
    """Minimal model comparison tables often omit weighted F1; banner should still annotate."""
    csv_path = tmp_path / "m.csv"
    csv_path.write_text("Model,MacroF1,Acc\nrf,0.9,0.91\n", encoding="utf-8")
    png_path = tmp_path / "cm.png"
    Image.new("RGB", (80, 80), color=(200, 200, 200)).save(png_path)
    assert pfr.annotate_confusion_matrix_with_metrics(
        confusion_path=png_path,
        model_comparison_csv=csv_path,
    )


def test_first_column_match_is_case_insensitive() -> None:
    cols = pd.Index(["macrof1", "ACC"])
    assert pfr._first_column_match(cols, ("MacroF1",)) == "macrof1"
    assert pfr._first_column_match(cols, ("Accuracy", "Acc")) == "ACC"
