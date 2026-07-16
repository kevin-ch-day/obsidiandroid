import obsidiandroid.classification_builder.prediction_utils as pu
import obsidiandroid.classification_builder.sample_classification_builder as sb
import pandas as pd
from obsidiandroid.modeling import prediction_builder


class DummyRecord:
    def __init__(self):
        self.category_vector = ["banker", "sms"]
        self.family = "foo"
        self.malware_type = "trojan"
        self.threat_class = "banker"

    def validate_record_completeness(self):
        return "complete"


def test_get_category_vector_string():
    rec = DummyRecord()
    assert pu.get_category_vector_string(rec) == "banker;sms"


def test_check_label_completeness():
    rec = DummyRecord()
    assert pu.check_label_completeness(rec, "s1") == "complete"


def test_extract_prediction_components_uses_label_encoder():
    class Enc:
        classes_ = ["a", "b"]

    results = {
        "predictions": {"x": 1},
        "true_labels": {"x": "a"},
        "prediction_metadata": {"x": {"confidence": 0.8}},
        "label_encoder": Enc(),
    }

    preds, decoder, trues, meta = pu.extract_prediction_components(results)
    assert decoder == {0: "a", 1: "b"}


def test_get_sample_confidence_handles_numeric_values():
    metadata = {'s1': 0.9, 's2': {'confidence': 0.7}}
    assert pu.get_sample_confidence(metadata, 's1', True) == 0.9
    assert pu.get_sample_confidence(metadata, 's2', True) == 0.7


def test_builder_uses_prediction_metadata_confidence(monkeypatch):
    results = {
        'predictions': {'s1': 0},
        'true_labels': {'s1': 'foo'},
        'label_decoder': {0: 'foo'},
        'prediction_metadata': {'s1': {'confidence': 0.6}}
    }

    def stub_build_row(sample_id, pred_index, label_decoder, true_labels, metadata,
                       records_by_vendor, label_format, include_confidence,
                       debug=False, consensus_data=None):
        return {
            'sample_id': sample_id,
            'confidence': pu.get_sample_confidence(metadata, sample_id, include_confidence)
        }

    monkeypatch.setattr(sb, 'build_classification_row', stub_build_row, raising=False)
    df = sb.build_sample_classification_records({}, results, include_confidence=True, verbose=False)
    assert not df.empty
    assert df.loc[0, 'confidence'] == 0.6


def test_export_model_backfills_named_feature_importances_into_result_metadata(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        prediction_builder.model_exporter,
        "export_model_to_file",
        lambda **_kwargs: tmp_path / "dummy.joblib",
    )
    result = {
        "metadata": {
            "feature_importances": [(1, 0.7), (0, 0.3)],
        },
        "label_classes": ["fam_a"],
        "label_name_map": {},
    }
    features_df = pd.DataFrame({"perm__internet": [1], "parsed_family_vendor": [0]})

    prediction_builder.export_model(
        result,
        "random_forest",
        features_df,
        {"accuracy": 1.0},
        tmp_path,
    )

    named = result["metadata"]["feature_importances_named"]
    assert named[0]["feature_name"] == "parsed_family_vendor"
    assert named[1]["feature_name"] == "perm__internet"


def test_full_prediction_rejects_incomplete_model_output(monkeypatch) -> None:
    """A model-prediction failure must not become a later indexing error."""
    monkeypatch.setattr(
        prediction_builder.model_prediction,
        "predict_all_samples",
        lambda **_kwargs: ([], [], [], pd.Series(dtype=float).to_numpy(), []),
    )

    class _Model:
        feature_names_in_ = ["feature"]

    result = prediction_builder.run_predictions_and_compile_result(
        "random_forest",
        {"model": _Model(), "label_encoder": object()},
        pd.DataFrame({"feature": [1, 0]}, index=[10, 11]),
        pd.Series([0, 1], index=[10, 11]),
    )

    assert result == {}


def test_builder_accepts_nested_prediction_metadata(monkeypatch):
    results = {
        'predictions': {'s1': 0},
        'true_labels': {'s1': 'foo'},
        'label_decoder': {0: 'foo'},
        'metadata': {'prediction_metadata': {'s1': {'confidence': 0.8}}}
    }

    def stub_build_row(sample_id, pred_index, label_decoder, true_labels, metadata,
                       records_by_vendor, label_format, include_confidence,
                       debug=False, consensus_data=None):
        return {
            'sample_id': sample_id,
            'confidence': pu.get_sample_confidence(metadata, sample_id, include_confidence)
        }

    monkeypatch.setattr(sb, 'build_classification_row', stub_build_row, raising=False)
    df = sb.build_sample_classification_records({}, results, include_confidence=True, verbose=False)
    assert df.loc[0, 'confidence'] == 0.8


def test_extract_prediction_components_falls_back_to_metadata():
    results = {
        "predictions": {"x": 1},
        "true_labels": {"x": "a"},
        "metadata": {"x": {"confidence": 0.6}},
    }
    _, _, _, meta = pu.extract_prediction_components(results)
    assert meta == {"x": {"confidence": 0.6}}


def test_get_sample_confidence_prefers_prediction_metadata():
    results = {
        "prediction_metadata": {"s1": {"confidence": 0.4}},
        "metadata": {"s1": {"confidence": 0.1}},
    }
    assert pu.get_sample_confidence(results, "s1", True) == 0.4


def test_extract_prediction_components_handles_invalid_input():
    results = {
        "predictions": None,
        "true_labels": "oops",
        "prediction_metadata": ["bad"],
        "label_encoder": 123,
    }
    preds, decoder, trues, meta = pu.extract_prediction_components(results)
    assert preds == {}
    assert decoder == {}
    assert trues == {}
    assert meta == {}


def test_get_sample_confidence_results_metadata_fallback():
    results = {"metadata": {"s1": {"confidence": 0.2}}}
    assert pu.get_sample_confidence(results, "s1", True) == 0.2


def test_get_sample_confidence_invalid_values():
    assert pu.get_sample_confidence("bad", "s1", True) == 0.0
    assert pu.get_sample_confidence({"s1": "n/a"}, "s1", True) == 0.0
    assert pu.get_sample_confidence({"s1": {"not_conf": 1}}, "s1", True) == 0.0
    assert pu.get_sample_confidence({"s1": 0.5}, "s1", False) is None
