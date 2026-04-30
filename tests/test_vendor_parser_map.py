"""Tests for vendor parser map helper utilities."""

from analysis.vendor_processing import vendor_parser_map


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
