"""Concise, run-safe classifier summary rendering.

This module intentionally reports the observed metric and artifact locations.
It does not infer deployment readiness, causal feature effects, or model
generalization from a single accuracy value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_MODEL_DISPLAY_NAMES = {
    "random_forest": "Random Forest",
    "balanced_random_forest": "Balanced Random Forest",
    "xgboost": "XGBoost",
    "logistic_regression": "Logistic Regression",
    "svm": "Support Vector Machine",
}


def generate_classification_summary(
    *,
    accuracy: float | None,
    report_path: str,
    model_path: str,
    metadata: dict[str, Any] | None = None,
    output_dir: str | Path = "output/diagnostics",
    model_name: str = "random_forest",
    write_report: bool = False,
) -> list[str]:
    """Build and print a compact descriptive classifier summary.

    A timestamped text artifact is written only when ``write_report`` is true.
    Run-scoped structured metrics remain the canonical output for normal runs.
    """
    display_name = _MODEL_DISPLAY_NAMES.get(model_name.lower(), model_name.replace("_", " ").title())
    lines = [
        "Classifier Summary",
        f"Model: {display_name}",
        (
            f"Accuracy: {accuracy:.4f} ({accuracy * 100:.2f}%)"
            if accuracy is not None
            else "Accuracy: unavailable"
        ),
        f"Classification report: {report_path}",
        f"Model artifact: {model_path}",
    ]
    if metadata:
        for key, label in (("samples", "Samples"), ("families", "Families"), ("features", "Features")):
            value = metadata.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                lines.append(f"{label}: {value:,}")
    lines.append("Interpret held-out metrics with the run's cohort, feature contract, and split artifacts.")

    print("\n".join(lines))
    if write_report:
        _write_report(lines, Path(output_dir))
    return lines


def _write_report(lines: list[str], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"classifier_summary_eval_{timestamp}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Classifier summary report written: {path}")
    return path


__all__ = ["generate_classification_summary"]
