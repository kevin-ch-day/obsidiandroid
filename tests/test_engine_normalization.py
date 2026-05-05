"""Tests for engine canonicalization logic."""

from obsidiandroid.pipeline import engine_normalization


def test_canonicalize_engine_name_basic_rules() -> None:
    """Normalization should collapse casing/punctuation/version suffix."""
    aliases = {}
    assert engine_normalization.canonicalize_engine_name("Avast-Mobile", aliases) == "avast_mobile"
    assert engine_normalization.canonicalize_engine_name("AVAST mobile", aliases) == "avast_mobile"
    assert engine_normalization.canonicalize_engine_name("kaspersky 2", aliases) == "kaspersky"


def test_engine_hash_is_stable() -> None:
    """Engine hash must be deterministic for canonical slug."""
    h1 = engine_normalization.compute_engine_hash("kaspersky")
    h2 = engine_normalization.compute_engine_hash("kaspersky")
    assert h1 == h2
    assert len(h1) == 12


def test_alias_can_preserve_numeric_vendor_key() -> None:
    """Alias targets that include numeric tokens should not be stripped."""
    aliases = {"qihoo": "qihoo_360"}
    assert engine_normalization.canonicalize_engine_name("qihoo", aliases) == "qihoo_360"


def test_legitimate_numeric_suffix_is_preserved() -> None:
    """Numeric vendor keys with meaningful suffixes should remain intact."""
    assert engine_normalization.canonicalize_engine_name("qihoo_360", {}) == "qihoo_360"
