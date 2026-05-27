import pytest
import pandas as pd

from obsidiandroid.classification_builder.classification_row_builder import build_classification_row
from obsidiandroid.classification_builder import sample_classification_builder
from obsidiandroid.inference.label_consensus_engine import resolve_consensus_label
from obsidiandroid.labeling import label_field_normalizer, label_format_generator
from config import app_config
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord


def test_build_row_handles_tuple_enrichment(monkeypatch):
    sample_id = 's1'
    record = VendorClassificationRecord(sample_id=sample_id, vendor_name='av', original_label='malware')
    records_by_vendor = {'av': [record]}
    label_decoder = {0: 'foo'}
    true_labels = {sample_id: 'foo'}
    metadata = {}

    monkeypatch.setattr(
        'obsidiandroid.classification_builder.classification_row_builder.vendor_record_selector.select_best_vendor_record',
        lambda *a, **k: record
    )
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_variant_from_trusted_vendors', lambda *a, **k: ('variant', 1.0, 'src', []))
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_threat_class_if_unknown', lambda *a, **k: ('threat', 1.0, 'src', []))
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.generate_label', lambda **kw: 'label')
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.prediction_utils.check_label_completeness', lambda *a, **k: True, raising=False)
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.prediction_utils.get_category_vector_string', lambda r: 'vect', raising=False)
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.prediction_utils.get_sample_confidence', lambda *a, **k: 0.5, raising=False)

    row = build_classification_row(sample_id, 0, label_decoder, true_labels, metadata, records_by_vendor, label_format='structured', include_confidence=False)
    assert row['classification_label'] == 'label'
    assert row['variant'] == 'variant'
    assert row['threat_class'] == 'threat'


def test_consensus_resolution_overrides_fields(monkeypatch):
    sample_id = 's1'
    rec1 = VendorClassificationRecord(sample_id=sample_id, vendor_name='v1', original_label='L1',
                                      family='fam', malware_type='trojan', threat_class='banker', platform='android', confidence_score=0.9)
    rec2 = VendorClassificationRecord(sample_id=sample_id, vendor_name='v2', original_label='L2',
                                      family='fam', malware_type='worm', threat_class='ransom', platform='android', confidence_score=0.1)
    records_by_vendor = {'v1': [rec1], 'v2': [rec2]}

    class LE:
        classes_ = ['fam']

    results = {
        'predictions': {sample_id: 0},
        'true_labels': {sample_id: 'fam'},
        'metadata': {sample_id: {'confidence': 0.8}},
        'label_encoder': LE(),
    }

    monkeypatch.setattr('obsidiandroid.classification_builder.vendor_record_selector.select_best_vendor_record',
                        lambda *a, **k: rec2)
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_variant_from_trusted_vendors',
                        lambda *a, **k: rec2.variant)
    monkeypatch.setattr('obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_threat_class_if_unknown',
                        lambda *a, **k: rec2.threat_class)

    df = sample_classification_builder.build_sample_classification_records(
        records_by_vendor=records_by_vendor,
        results=results,
        use_consensus=True,
        consensus_function=resolve_consensus_label,
        verbose=False,
        include_confidence=False,
    )

    row = df.iloc[0]
    assert row['threat_class'] == 'banker'
    assert row['malware_type'] == 'trojan'


def test_consensus_does_not_override_unknown(monkeypatch):
    sample_id = 's1'
    rec = VendorClassificationRecord(sample_id=sample_id, vendor_name='v1', original_label='L1',
                                     family='fam', malware_type='trojan', threat_class='banker', platform='android', confidence_score=0.9)
    records_by_vendor = {'v1': [rec]}

    class LE:
        classes_ = ['fam']

    results = {
        'predictions': {sample_id: 0},
        'true_labels': {sample_id: 'fam'},
        'metadata': {sample_id: {'confidence': 0.8}},
        'label_encoder': LE(),
    }

    def dummy_consensus(records):
        return {'threat_class': 'unknown', 'malware_type': 'unknown'}

    df = sample_classification_builder.build_sample_classification_records(
        records_by_vendor=records_by_vendor,
        results=results,
        use_consensus=True,
        consensus_function=dummy_consensus,
        verbose=False,
        include_confidence=False,
    )

    row = df.iloc[0]
    assert row['threat_class'] == 'banker'
    assert row['malware_type'] == 'trojan'


def test_build_row_prefers_runtime_type_slug_for_label_rendering(monkeypatch):
    sample_id = "1003"
    record = VendorClassificationRecord(
        sample_id=sample_id,
        vendor_name="av",
        original_label="Trojan.Android.Applite",
        family="applite",
        malware_type="trojan",
        threat_class="banker",
        platform="android",
    )
    records_by_vendor = {"av": [record]}
    label_decoder = {0: "applite"}
    true_labels = {sample_id: "applite"}
    metadata = {1003: {"confidence": 0.95, "type_slug": "dropper"}}

    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.vendor_record_selector.select_best_vendor_record",
        lambda *a, **k: record,
    )
    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_variant_from_trusted_vendors",
        lambda *a, **k: record.variant,
    )
    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_threat_class_if_unknown",
        lambda *a, **k: record.threat_class,
    )

    row = build_classification_row(
        sample_id,
        0,
        label_decoder,
        true_labels,
        metadata,
        label_name_map={"applite": "Applite"},
        records_by_vendor=records_by_vendor,
        label_format="structured",
        include_confidence=True,
    )

    assert row["threat_class"] == "dropper"
    assert row["classification_label"] == "trojan/android.dropper.applite"


def test_build_row_uses_runtime_split_sample_metadata_when_prediction_metadata_lacks_type_slug(monkeypatch):
    sample_id = "1003"
    record = VendorClassificationRecord(
        sample_id=sample_id,
        vendor_name="av",
        original_label="Trojan.Android.Applite",
        family="applite",
        malware_type="trojan",
        threat_class="banker",
        platform="android",
    )
    records_by_vendor = {"av": [record]}
    label_decoder = {0: "applite"}
    true_labels = {sample_id: "applite"}
    metadata = {1003: {"confidence": 0.95}}
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(
            [
                {
                    "sample_id": 1003,
                    "type_slug": "adware",
                    "family_canonical": "applite",
                }
            ]
        ),
        raising=False,
    )

    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.vendor_record_selector.select_best_vendor_record",
        lambda *a, **k: record,
    )
    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_variant_from_trusted_vendors",
        lambda *a, **k: record.variant,
    )
    monkeypatch.setattr(
        "obsidiandroid.classification_builder.classification_row_builder.record_enrichment.enrich_threat_class_if_unknown",
        lambda *a, **k: record.threat_class,
    )

    row = build_classification_row(
        sample_id,
        0,
        label_decoder,
        true_labels,
        metadata,
        label_name_map={"applite": "Applite"},
        records_by_vendor=records_by_vendor,
        label_format="structured",
        include_confidence=True,
    )

    assert row["threat_class"] == "adware"
    assert row["classification_label"] == "trojan/android.adware.applite"


def test_generate_structured_label_retains_type_when_matching():
    record = VendorClassificationRecord(
        sample_id='s1',
        vendor_name='av',
        original_label='Trojan.Android.Foo',
        family='foo',
        malware_type='trojan',
        threat_class='trojan',
        platform='android',
        variant='unknown'
    )
    label = label_format_generator.generate_label(record.family, record, format='structured')
    assert label == 'trojan/android.trojan.foo'


def test_generate_structured_label_defaults_on_numeric_type():
    record = VendorClassificationRecord(
        sample_id='s2',
        vendor_name='av',
        original_label='Trojan.Android.Bar',
        family='bar',
        malware_type='12345',
        threat_class='trojan',
        platform='android',
        variant='v1'
    )
    from obsidiandroid.labeling.label_field_normalizer import DEFAULT_TYPE
    label = label_format_generator.generate_label(record.family, record, format='structured')
    assert label == f'{DEFAULT_TYPE}/android.trojan.bar[v1]'


def test_structured_label_keeps_type_when_matching_threat():
    record = VendorClassificationRecord(
        sample_id='s2',
        vendor_name='av',
        original_label='banker',
        malware_type='banker',
        threat_class='banker',
        platform='android',
        family='foo',
    )
    fields = label_field_normalizer.generate_structured_fields(record.family, record)
    label = label_format_generator.generate_structured_label(fields)
    assert fields['mtype'] == 'banker'
    assert label.startswith('banker/android.banker')


@pytest.mark.parametrize(
    "threat,mtype,exp_threat,exp_type",
    [
        ("banker", "banker", "banker", "banker"),
        ("banker", "malware", "banker", "banker"),
        ("generic", "malware", "generic", "malware"),
        ("spyware", "trojan", "spyware", "trojan"),
    ],
)
def test_deduplicate_fields_various(threat, mtype, exp_threat, exp_type):
    t, mt = label_field_normalizer._deduplicate_fields(threat, mtype)
    assert t == exp_threat
    assert mt == exp_type


@pytest.mark.parametrize(
    "label,family,threat_class,malware_type,exp_threat,exp_type",
    [
        ("Android.Bank.Foo", "foo", "", "", "banker", "banker"),
        ("Spy.Note", "bar", "", "", "spyware", "spyware"),
        ("Generic.Malware", "baz", "", "", "generic", "malware"),
    ],
)
def test_generate_structured_fields_infers_values(label, family, threat_class, malware_type, exp_threat, exp_type):
    record = VendorClassificationRecord(
        sample_id='edge',
        vendor_name='av',
        original_label=label,
        malware_type=malware_type,
        threat_class=threat_class,
        platform='android',
        family=family,
    )
    fields = label_field_normalizer.generate_structured_fields(record.family, record)
    assert fields['family'] == family
    assert fields['threat'] == exp_threat
    assert fields['mtype'] == exp_type
