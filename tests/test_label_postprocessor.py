import pandas as pd

from obsidiandroid.labeling import label_postprocessor


def test_summarize_prediction_results_excludes_synthetic_other_from_family_count(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []
    warnings: list[str] = []

    monkeypatch.setattr(label_postprocessor.du, "print_stat", lambda key, value: stats.append((str(key), value)))
    monkeypatch.setattr(label_postprocessor.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(label_postprocessor.du, "print_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(label_postprocessor.du, "print_table", lambda *_args, **_kwargs: None)

    df = pd.DataFrame(
        [
            {"sample_id": 1, "predicted_family": "SpyNote", "classification_label": "x", "confidence": 0.9},
            {
                "sample_id": 2,
                "predicted_family": "other",
                "classification_label": "y",
                "confidence": 0.8,
                "override_tag": "type_guard_family_suppressed",
            },
            {"sample_id": 3, "predicted_family": "Irata", "classification_label": "z", "confidence": 0.7},
            {"sample_id": 4, "predicted_family": "Applite", "classification_label": "q", "confidence": 0.6},
        ]
    )

    label_postprocessor.summarize_prediction_results(df)

    assert ("Unique Predicted Families", "3 (+ synthetic other bucket)") in stats
    assert ("Type-Guard Synthetic Other Rows", 1) in stats
    assert not any("Low prediction diversity" in message for message in warnings)


def test_summarize_prediction_results_surfaces_guardrail_abstains(monkeypatch) -> None:
    stats: list[tuple[str, object]] = []

    monkeypatch.setattr(label_postprocessor.du, "print_stat", lambda key, value: stats.append((str(key), value)))
    monkeypatch.setattr(label_postprocessor.du, "print_warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(label_postprocessor.du, "print_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(label_postprocessor.du, "print_table", lambda *_args, **_kwargs: None)

    df = pd.DataFrame(
        [
            {
                "sample_id": 1,
                "predicted_family": "other",
                "classification_label": "x",
                "confidence": 0.41,
                "override_tag": "low_confidence_family_abstain",
            },
            {
                "sample_id": 2,
                "predicted_family": "other",
                "classification_label": "y",
                "confidence": 0.52,
                "override_tag": "ambiguous_family_abstain",
            },
            {"sample_id": 3, "predicted_family": "SpyNote", "classification_label": "z", "confidence": 0.9},
        ]
    )

    label_postprocessor.summarize_prediction_results(df)

    assert ("False-Positive Guardrail Abstains", 2) in stats
