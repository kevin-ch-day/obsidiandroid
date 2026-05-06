from ml_classification.builder import sample_classification_builder as sb
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord


def test_builder_includes_confidence():
    rec = VendorClassificationRecord(
        sample_id="s1", vendor_name="av", original_label="x"
    )
    records_by_vendor = {"s1": [rec]}
    results = {
        "predictions": {"s1": 0},
        "true_labels": {"s1": "foo"},
        "prediction_metadata": {"s1": {"confidence": 0.88}},
        "label_decoder": {0: "foo"},
    }
    df = sb.build_sample_classification_records(
        records_by_vendor,
        results,
        include_confidence=True,
        verbose=False,
        use_consensus=False,
    )
    assert not df.empty
    assert df.loc[0, "confidence"] == 0.88


def test_builder_handles_bad_predictions():
    df = sb.build_sample_classification_records({}, {"predictions": []}, verbose=False)
    assert df.empty
