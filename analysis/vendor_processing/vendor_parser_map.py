# Filename: vendor_parser_map.py
# Description: Maps AV vendor names directly to parser functions using exact DataFrame column names

from typing import Dict, List, Optional
from utils import display_utils as du
from . import (
    ahnlab_v3_parser,
    alibaba_parser,
    avast_parser,
    avast_mobile_parser,
    bitdefender_parser,
    bitdefenderfalx_parser,
    ikarus_parser,
    kaspersky_parser,
    k7gw_parser,
    lionic_parser,
    microsoft_parser,
    tencent_parser,
    zonealarm_parser,
    generic_label_parser,
)

# Parser function entry definition
ParserEntry = Dict[str, object]  # keys: type, func, aliases (optional)

# ------------------------------------------------------------------------------
# Central Parser Map (keys MUST match exact DataFrame column names)
# ------------------------------------------------------------------------------
def get_vendor_parser_map() -> Dict[str, ParserEntry]:
    return {
        "AhnLab_V3": {
            "type": "label",
            "func": ahnlab_v3_parser.parse_ahnlab_v3_classification
        },
        "Alibaba": {
            "type": "label",
            "func": alibaba_parser.parse_alibaba_classification
        },
        "Avast": {
            "type": "label",
            "func": avast_parser.parse_avast_label
        },
        "Avast_Mobile": {
            "type": "label",
            "func": avast_mobile_parser.parse_avast_mobile_label,
            "aliases": ["Avast-Mobile"]
        },
        "BitDefenderFalx": {
            "type": "label",
            "func": bitdefenderfalx_parser.parse_bitdefenderfalx_classification
        },
        "BitDefender": {
            "type": "label",
            "func": bitdefender_parser.parse_bitdefender_classification
        },
        "Ikarus": {
            "type": "label",
            "func": ikarus_parser.parse_ikarus_classification
        },
        "K7GW": {
            "type": "label",
            "func": k7gw_parser.parse_k7gw_classification
        },
        "Kaspersky": {
            "type": "label",
            "func": kaspersky_parser.parse_kaspersky_classification
        },
        "Lionic": {
            "type": "label",
            "func": lionic_parser.parse_lionic_classification
        },
        "Microsoft": {
            "type": "label",
            "func": microsoft_parser.parse_microsoft_classification
        },
        "Tencent": {
            "type": "label",
            "func": tencent_parser.parse_tencent_classification
        },
        "ZoneAlarm": {
            "type": "label",
            "func": zonealarm_parser.parse_zonealarm_classification
        },
        # Generic parser onboarding for high-coverage vendors lacking custom parsers.
        "DrWeb": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "ESET_NOD32": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "F_Secure": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "Fortinet": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "Avira": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "Sophos": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "AVG": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "Google": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification,
            "aliases": ["Google_Android"]
        },
        "ALYac": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification,
            "aliases": ["Alyac"]
        },
        "Kingsoft": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification
        },
        "VirIT": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification,
            "aliases": ["Virit"]
        },
        "TEHTRIS": {
            "type": "label",
            "func": generic_label_parser.parse_generic_classification,
            "aliases": ["Tehtris"]
        }
    }

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------
def get_available_parsers() -> List[str]:
    """Returns a list of available vendor names with registered parsers."""
    return sorted(get_vendor_parser_map().keys())

def get_row_based_parsers() -> List[str]:
    """Returns vendor names for parsers that operate on row-type structures."""
    return sorted([v for v, meta in get_vendor_parser_map().items() if meta.get("type") == "row"])


def _normalize_vendor_column_name(name: str) -> str:
    """Normalize vendor/column names for robust matching."""
    return str(name).strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_parser_entry(vendor: str) -> ParserEntry:
    """Resolve parser entry by exact or normalized vendor key.

    Args:
        vendor: Vendor key to resolve.

    Returns:
        Matching parser map entry, or an empty mapping when not found.
    """
    parser_map = get_vendor_parser_map()
    direct = parser_map.get(vendor)
    if direct is not None:
        return direct

    normalized_vendor = _normalize_vendor_column_name(vendor)
    for key, entry in parser_map.items():
        if _normalize_vendor_column_name(key) == normalized_vendor:
            return entry
    return {}


def resolve_vendor_column_name(vendor: str, av_columns: List[str]) -> Optional[str]:
    """Resolve parser vendor key to an existing AV dataframe column name."""
    parser_meta = _resolve_parser_entry(vendor)
    candidate_names = [vendor] + list(parser_meta.get("aliases", []) or [])
    normalized_columns = {
        _normalize_vendor_column_name(column): column
        for column in av_columns
    }
    for candidate in candidate_names:
        resolved = normalized_columns.get(_normalize_vendor_column_name(candidate))
        if resolved:
            return resolved
    return None

def validate_vendor_parser_columns(av_columns: List[str], verbose: bool = True) -> List[str]:
    """Checks which parser vendors are matched or missing in the AV DataFrame.

    Returns:
        list[str]: Vendor parser keys missing from ``av_columns``.
    """
    parser_map = get_vendor_parser_map()
    found, missing = [], []

    for vendor in sorted(parser_map):
        if resolve_vendor_column_name(vendor, av_columns) is not None:
            found.append(vendor)
        else:
            missing.append(vendor)

    if verbose:
        du.print_section("Vendor Parser Column Validation")
        du.print_info(f"Total Parsers Defined : {len(parser_map)}")
        du.print_info(f"Matched Columns        : {len(found)}")
        du.print_info(f"Missing Columns        : {len(missing)}")
        if missing:
            du.print_warning(" -> Missing vendor columns: " + ", ".join(missing))

    return missing
