"""Tests for vendor parser map helper utilities."""

import pandas as pd

from obsidiandroid.vendors import vendor_parser_map
from obsidiandroid.vendors.parsing.lionic_parser import parse_lionic_classification
from obsidiandroid.evaluation import vendor_parser_utils as vpu
from config import app_config


def test_validate_vendor_parser_columns_returns_missing_keys() -> None:
    """Function should return parser keys missing from provided columns."""
    missing = vendor_parser_map.validate_vendor_parser_columns(
        av_columns=["AhnLab_V3", "Alibaba"],
        verbose=False,
    )
    assert isinstance(missing, list)
    assert "AhnLab_V3" not in missing
    assert "Alibaba" not in missing
    assert "Kaspersky" in missing


def test_validate_vendor_parser_columns_all_present_returns_empty() -> None:
    """No missing parser keys should return an empty list."""
    all_cols = vendor_parser_map.get_available_parsers()
    missing = vendor_parser_map.validate_vendor_parser_columns(
        av_columns=all_cols,
        verbose=False,
    )
    assert missing == []


def test_validate_vendor_parser_columns_supports_canonical_lowercase_columns() -> None:
    """Validation should match parser keys against canonical lowercase AV columns."""
    canonical_cols = [
        "ahnlab_v3",
        "alibaba",
        "avast",
        "avast_mobile",
        "bitdefender",
        "bitdefenderfalx",
        "ikarus",
        "k7gw",
        "kaspersky",
        "lionic",
        "microsoft",
        "tencent",
        "zonealarm",
        "drweb",
        "eset_nod32",
        "f_secure",
        "fortinet",
        "avira",
        "sophos",
        "avg",
        "google",
        "alyac",
        "kingsoft",
        "virit",
        "tehtris",
    ]
    missing = vendor_parser_map.validate_vendor_parser_columns(
        av_columns=canonical_cols,
        verbose=False,
    )
    assert missing == []


def test_resolve_vendor_column_name_supports_new_aliases() -> None:
    """Alias mapping should resolve high-coverage vendor name variants."""
    columns = ["Google_Android", "Tehtris", "Alyac", "Virit"]
    assert vendor_parser_map.resolve_vendor_column_name("Google", columns) == "Google_Android"
    assert vendor_parser_map.resolve_vendor_column_name("TEHTRIS", columns) == "Tehtris"
    assert vendor_parser_map.resolve_vendor_column_name("ALYac", columns) == "Alyac"
    assert vendor_parser_map.resolve_vendor_column_name("VirIT", columns) == "Virit"



def test_resolve_vendor_column_name_is_case_insensitive_for_vendor_keys() -> None:
    """Vendor-key lookup should support case-insensitive parser names."""
    columns = ["Google_Android", "avg"]
    assert vendor_parser_map.resolve_vendor_column_name("google", columns) == "Google_Android"
    assert vendor_parser_map.resolve_vendor_column_name("AVG", columns) == "avg"


def test_lionic_preserves_banbra_family_token() -> None:
    """BanBra should remain a family token instead of being coerced."""
    parsed = parse_lionic_classification("Trojan.AndroidOS.BanBra.C!c")
    assert parsed["family"] == "Banbra"
    assert parsed["threat_class"] == "banker"


def test_lionic_preserves_basbanke_family_token() -> None:
    """Basbanke should remain explicit so downstream authority can adjudicate it."""
    parsed = parse_lionic_classification("Trojan.AndroidOS.Basbanke.A!c")
    assert parsed["family"] == "Basbanke"
    assert parsed["threat_class"] == "banker"


def test_lionic_preserves_smsspy_family_token() -> None:
    """SMSSpy should not be coerced into SpyNote at parser time."""
    parsed = parse_lionic_classification("Trojan.AndroidOS.SMSSpy.A!c")
    assert parsed["family"] == "Smsspy"
    assert parsed["threat_class"] == "spy"


def test_lionic_preserves_hiddenad_family_token() -> None:
    """HiddenAd-style tokens should survive parser normalization."""
    parsed = parse_lionic_classification("Trojan.AndroidOS.HiddenAd.A!c")
    assert parsed["family"] == "Hiddenad"
    assert parsed["threat_class"] == "adware"


def test_dynamic_generic_onboarding_respects_coverage_threshold(monkeypatch) -> None:
    """Columns meeting minimum coverage should be onboarded."""
    monkeypatch.setattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True, raising=False)
    av_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "KnownVendor": ["a", "b", None, ""],
            "SparseVendor": [None, None, None, "x"],
        }
    )
    existing = {
        "KnownVendor": {
            "type": "label",
            "func": lambda x, *_: x,
            "column_name": "KnownVendor",
        }
    }
    dynamic = vpu._build_dynamic_generic_parser_map(  # pylint: disable=protected-access
        av_df=av_df,
        existing_map=existing,
        verbose=False,
    )
    assert "SparseVendor__generic" in dynamic
    assert dynamic["SparseVendor__generic"]["column_name"] == "SparseVendor"


def test_dynamic_generic_onboarding_excludes_non_vendor_columns() -> None:
    """Non-vendor bookkeeping fields should not be onboarded."""
    av_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_name": ["a", "b"],
            "family_id": [10, 11],
        }
    )
    dynamic = vpu._build_dynamic_generic_parser_map(  # pylint: disable=protected-access
        av_df=av_df,
        existing_map={},
        verbose=False,
    )
    assert dynamic == {}
