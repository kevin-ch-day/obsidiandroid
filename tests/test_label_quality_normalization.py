from types import SimpleNamespace
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ml_classification.builder import prediction_utils
from ml_classification.common.malware_family_constants import (
    canonicalize_family_label,
    is_known_family_name,
    normalize_family_name,
)
from ml_classification.training import data_alignment
import pandas as pd


def test_family_alias_normalization():
    assert normalize_family_name("HQWar") == "trickmo"
    assert normalize_family_name("Flu-Bot") == "flubot"
    assert normalize_family_name(15) == "15"


def test_known_family_with_alias():
    assert is_known_family_name("hqwar")
    assert is_known_family_name("TrickMo")


def test_cabassous_canonicalizes_to_flubot_token_and_flubot_display():
    assert normalize_family_name("Cabassous") == "flubot"
    assert canonicalize_family_label("Cabassous") == "FluBot"


def test_completeness_uses_predicted_family_fallback():
    record = SimpleNamespace(
        family="unknown",
        malware_type="trojan",
        threat_class="banker",
        _predicted_family_fallback="TrickMo",
        validate_record_completeness=lambda: "incomplete (family)",
    )
    result = prediction_utils.check_label_completeness(record, sample_id="1001")
    assert result == "complete"


def test_category_vector_family_alias_normalized():
    record = SimpleNamespace(category_vector=["family:hqwar", "type:trojan"])
    vector = prediction_utils.get_category_vector_string(record)
    assert "family:trickmo" in vector


def test_training_label_normalization_merges_variants():
    labels = pd.Series(["FluBot", "Flubot", "Cabassous", "TeaBot", "teabot"])
    merged = data_alignment.normalize_labels(labels, normalization_map={})
    assert list(merged) == ["FluBot", "FluBot", "FluBot", "TeaBot", "TeaBot"]
