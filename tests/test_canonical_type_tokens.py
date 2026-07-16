"""Regression tests for canonical Android malware type-token handling."""

from config import app_config
from obsidiandroid.diagnostics import family_label_confidence_audit
from obsidiandroid.governance import family_tier_authority
from obsidiandroid.labeling import classification_label_resolver


def test_all_live_active_type_tokens_are_canonical_across_audit_surfaces() -> None:
    """Configured taxonomy must cover the live active type vocabulary.

    `unknown` is deliberately excluded: it denotes absent/insufficient type
    evidence rather than a semantic malware class.
    """
    expected = {
        "adware",
        "backdoor",
        "banker",
        "cryptojacking",
        "downloader",
        "dropper",
        "miner",
        "ransomware",
        "rat",
        "riskware",
        "rootkit",
        "sms-trojan",
        "spyware",
        "stalkerware",
        "stealer",
        "subscription-fraud",
        "trojan",
    }
    assert expected <= set(app_config.CANONICAL_TYPE_SLUGS)
    assert expected <= set(family_tier_authority.CANONICAL_TYPE_TOKENS)
    assert expected <= family_label_confidence_audit._CANONICAL_TYPE_TOKENS  # pylint: disable=protected-access


def test_subscription_fraud_is_a_canonical_type_across_audit_surfaces() -> None:
    """Premium-subscription malware must not be misreported as a noncanonical type."""
    assert "subscription-fraud" in app_config.CANONICAL_TYPE_SLUGS
    assert "subscription-fraud" in family_tier_authority.CANONICAL_TYPE_TOKENS
    assert family_label_confidence_audit._infer_raw_type(  # pylint: disable=protected-access
        "trojan",
        "subscription-fraud",
    ) == "subscription-fraud"


def test_explicit_dropper_and_trojan_labels_are_not_coerced_into_other_types() -> None:
    """Broad labels remain auditable instead of being silently relabeled as banker/adware."""
    assert classification_label_resolver._extract_type_slug_from_label(  # pylint: disable=protected-access
        "trojan/android.dropper.clast82"
    ) == "dropper"
    assert classification_label_resolver._extract_type_slug_from_label(  # pylint: disable=protected-access
        "trojan/android.trojan.boogr"
    ) == "trojan"
    assert classification_label_resolver._extract_type_slug_from_label(  # pylint: disable=protected-access
        "trojan/android.backdoor.triada"
    ) == "backdoor"
