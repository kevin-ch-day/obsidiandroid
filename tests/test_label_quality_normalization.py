from types import SimpleNamespace

from obsidiandroid.classification_builder import prediction_utils
from obsidiandroid.labeling.label_builder_wrapper import (
    apply_db_family_override,
    should_use_db_family,
)
from obsidiandroid.labeling.taxonomy import (
    canonicalize_family_label,
    is_known_family_name,
    normalize_family_name,
)
from obsidiandroid.labeling.label_builder_wrapper import _normalize_family_type_profile
from obsidiandroid.modeling import data_alignment
import pandas as pd


def test_family_alias_normalization():
    assert normalize_family_name("HQWar") == "trickmo"
    assert normalize_family_name("Flu-Bot") == "flubot"
    assert normalize_family_name("OTPStealer") == "otpstealer"
    assert normalize_family_name("otp-stealer") == "otpstealer"
    assert normalize_family_name("Arsink RAT") == "arsinkrat"
    assert normalize_family_name("ClayRat v3") == "clayrat"
    assert normalize_family_name("Carrier Billing Fraud") == "carrierbillingfraud"
    assert normalize_family_name("Sarang Trap") == "sarangtrap"
    assert normalize_family_name("Fantasy Hub") == "fantasyhub"
    assert normalize_family_name("Safer Rat") == "saferrat"
    assert normalize_family_name("Goat Rat") == "goatrat"
    assert normalize_family_name("Recruit Rat") == "recruitrat"
    assert normalize_family_name("Taxi Spy RAT") == "taxispyrat"
    assert normalize_family_name("Oblivion RAT") == "oblivionrat"
    assert normalize_family_name("Play Praetors") == "playpraetors"
    assert normalize_family_name("Droid Lock") == "droidlock"
    assert normalize_family_name(15) == "15"


def test_known_family_with_alias():
    assert is_known_family_name("hqwar")
    assert is_known_family_name("TrickMo")
    assert is_known_family_name("ToxicPanda")
    assert is_known_family_name("MaliBot")
    assert is_known_family_name("GravityRAT")
    assert is_known_family_name("OTPStealer")
    assert is_known_family_name("Arsink RAT")


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
    assert canonicalize_family_label("OTPStealer") == "OTPStealer"
    assert canonicalize_family_label("Arsink RAT") == "ArsinkRAT"
    assert canonicalize_family_label("ClayRat v3") == "ClayRat"
    assert canonicalize_family_label("Carrier Billing Fraud") == "CarrierBillingFraud"
    assert canonicalize_family_label("Sarang Trap") == "SarangTrap"
    assert canonicalize_family_label("Fantasy Hub") == "FantasyHub"
    assert canonicalize_family_label("Safer Rat") == "SaferRat"
    assert canonicalize_family_label("Goat Rat") == "GoatRat"
    assert canonicalize_family_label("Recruit Rat") == "RecruitRat"
    assert canonicalize_family_label("Taxi Spy RAT") == "TaxiSpyRat"
    assert canonicalize_family_label("Oblivion RAT") == "OblivionRAT"
    assert canonicalize_family_label("Play Praetors") == "PlayPraetors"
    assert canonicalize_family_label("Droid Lock") == "DroidLock"


def test_cabassous_canonicalizes_to_flubot_token_and_flubot_display():
    assert normalize_family_name("Cabassous") == "flubot"
    assert canonicalize_family_label("Cabassous") == "FluBot"


def test_metasploit_is_normalized_to_unknown():
    assert normalize_family_name("Metasploit") == "unknown"
    assert normalize_family_name("Trojan.MetaSploit") == "unknown"
    assert canonicalize_family_label("metasploit") == "unknown"
    assert canonicalize_family_label("Trojan.MetaSploit") == "unknown"


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
    labels = pd.Series(["FluBot", "Flubot", "Cabassous", "TeaBot", "teabot", "Trojan.MetaSploit"])
    merged = data_alignment.normalize_labels(labels, normalization_map={})
    assert list(merged) == ["FluBot", "FluBot", "FluBot", "TeaBot", "TeaBot", "unknown"]


def test_should_use_db_family_blocks_non_family_tokens():
    assert not should_use_db_family({"family_name": "Metasploit"}, "Teabot")
    assert not should_use_db_family({"family_name": "Trojan.MetaSploit"}, "Teabot")
    assert not should_use_db_family({"family_name": "unknown"}, "Teabot")


def test_should_not_override_with_generic_db_family_tokens():
    assert not should_use_db_family({"family_name": "metasploit"}, "FluBot")
    assert not should_use_db_family({"family_name": "generic"}, "FluBot")
    assert not should_use_db_family({"family_name": ""}, "FluBot")
    assert not should_use_db_family({}, "FluBot")


def test_should_use_db_family_blocks_cross_type_override():
    profile = {"teabot": {"banker"}, "spybot": {"rat"}}
    sample_metadata = {"family_name": "Teabot", "type_slug": "rat"}
    assert not should_use_db_family(sample_metadata, "SharkBot", profile)


def test_should_use_db_family_allows_cross_type_override_when_type_profile_unknown():
    profile = {"teabot": {"banker"}, "spybot": {"rat"}}
    sample_metadata = {"family_name": "Cabassous", "type_slug": "rat"}
    assert should_use_db_family(sample_metadata, "SharkBot", profile)


def test_apply_db_family_override_respects_type_profile(monkeypatch):
    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "family_name": "Teabot",
                "type_slug": "banker",
            },
            {
                "sample_id": 1002,
                "family_name": "SharkBot",
                "type_slug": "rat",
            },
        ]
    )
    monkeypatch.setattr("obsidiandroid.labeling.label_builder_wrapper.app_config.RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)

    model_output = {
        "predictions": {
            "1001": "SharkBot",
            "1002": "SharkBot",
        },
        "metadata": {
            "1001": {"family_name": "Teabot", "type_slug": "banker"},
            "1002": {"family_name": "Teabot", "type_slug": "rat"},
        },
    }

    updated = apply_db_family_override(model_output)
    assert updated["predictions"]["1001"] == "Teabot"
    assert updated["predictions"]["1002"] == "SharkBot"
    assert updated["metadata"]["1002"].get("override_tag") is None
    assert updated["metadata"]["1001"]["override_tag"] == "db_family_override"


def test_apply_db_family_override_type_profile_from_runtime_metadata(monkeypatch):
    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 2001,
                "family_canonical": "Teabot",
                "type_slug": "banker",
            }
        ]
    )
    monkeypatch.setattr("obsidiandroid.labeling.label_builder_wrapper.app_config.RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    profile = _normalize_family_type_profile()
    assert profile["teabot"] == {"banker"}


def test_apply_db_family_override_prefers_known_family_only():
    model_output = {
        "predictions": {
            "1001": "FluBot",
            "1002": "Unknown",
            "1003": "SharkBot",
            "1004": "Anubis",
        },
        "metadata": {
            "1001": {"family_name": "metasploit"},
            "1002": {"family_name": "Teabot"},
            "1003": {"family_name": "generic"},
            "1004": {"family_name": "Teabot"},
        },
    }

    updated = apply_db_family_override(model_output)
    predictions = updated["predictions"]
    metadata = updated["metadata"]

    assert predictions["1001"] == "FluBot"
    assert metadata["1001"].get("override_tag") is None
    assert predictions["1002"] == "Teabot"
    assert metadata["1002"]["override_tag"] == "db_family_override"
    assert predictions["1003"] == "SharkBot"
    assert metadata["1003"].get("override_tag") is None
    assert predictions["1004"] == "Teabot"
    assert metadata["1004"]["override_tag"] == "db_family_override"
