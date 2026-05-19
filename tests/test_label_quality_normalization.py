from types import SimpleNamespace

from obsidiandroid.classification_builder import prediction_utils
from obsidiandroid.labeling.taxonomy import (
    canonicalize_family_label,
    is_known_family_name,
    normalize_family_name,
)
from obsidiandroid.modeling import data_alignment
import pandas as pd


def test_family_alias_normalization():
    assert normalize_family_name("HQWar") == "trickmo"
    assert normalize_family_name("Flu-Bot") == "flubot"
    assert normalize_family_name(15) == "15"


def test_known_family_with_alias():
    assert is_known_family_name("hqwar")
    assert is_known_family_name("TrickMo")
    assert is_known_family_name("ToxicPanda")
    assert is_known_family_name("MaliBot")
    assert is_known_family_name("GravityRAT")


def test_live_family_normalization_and_display_for_recent_android_families():
    assert normalize_family_name("Toxic Panda") == "toxicpanda"
    assert normalize_family_name("MaliBot") == "malibot"
    assert normalize_family_name("GravityRAT") == "gravityrat"
    assert normalize_family_name("Pix BankBot") == "pixbankbot"
    assert normalize_family_name("PixPirate") == "pixpirate"
    assert canonicalize_family_label("Toxic Panda") == "ToxicPanda"
    assert canonicalize_family_label("MaliBot") == "MaliBot"
    assert canonicalize_family_label("GravityRAT") == "GravityRAT"
    assert canonicalize_family_label("Pix BankBot") == "PixBankBot"
    assert canonicalize_family_label("PixPirate") == "PixPirate"
    assert canonicalize_family_label("BlankBot") == "BlankBot"
    assert canonicalize_family_label("BingoMod") == "BingoMod"
    assert canonicalize_family_label("Rafel") == "Rafel"


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
