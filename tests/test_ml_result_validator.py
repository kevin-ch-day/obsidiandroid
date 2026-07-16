"""Result-payload alignment checks used by the modeling executor."""

import numpy as np

from obsidiandroid.modeling.ml_result_validator import validate_result_structure


def _valid_result() -> dict:
    return {
        "model": object(),
        "X_test": np.zeros((2, 1)),
        "y_test": np.array([0, 1]),
        "evaluation": {"accuracy": 1.0},
        "label_classes": ["a", "b"],
        "label_encoder": object(),
        "predictions": {101: 0, 102: 1},
        "true_labels": {101: 0, 102: 1},
        "metadata": {},
        "confidences": np.array([0.9, 0.8]),
    }


def test_result_validator_accepts_aligned_prediction_payload() -> None:
    assert validate_result_structure(_valid_result()) is True


def test_result_validator_rejects_truncated_labels_or_confidences() -> None:
    labels_truncated = _valid_result()
    labels_truncated["true_labels"] = {101: 0}
    assert validate_result_structure(labels_truncated) is False

    confidences_truncated = _valid_result()
    confidences_truncated["confidences"] = np.array([0.9])
    assert validate_result_structure(confidences_truncated) is False


def test_result_validator_rejects_mismatched_prediction_label_ids() -> None:
    result = _valid_result()
    result["true_labels"] = {101: 0, 999: 1}
    assert validate_result_structure(result) is False
