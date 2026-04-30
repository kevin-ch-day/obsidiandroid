# Filename: analysis/evaluation/vendor_parser_matching.py
# Purpose : Matches AV vendor parser definitions to available columns in input data

import difflib
from utils import display_utils as du


def resolve_valid_vendor_columns(
    vendor_map: dict,
    av_columns: list[str],
    verbose: bool = False
) -> dict:
    """
    Resolves which AV vendors in the parser map can be matched to columns in the dataset.
    Returns a filtered vendor map with only compatible parsers.
    """
    matched = {}
    skipped = {}
    normalized_columns = _normalize_column_names(av_columns)

    for vendor_key, metadata in vendor_map.items():
        is_row_based = metadata.get("type") == "row"
        aliases = [vendor_key] + metadata.get("aliases", [])

        alias_match = _find_matching_alias(aliases, normalized_columns)
        if alias_match:
            resolved_column = _resolve_column_name(alias_match, normalized_columns)
            updated_meta = dict(metadata)
            updated_meta["column_name"] = resolved_column
            matched[vendor_key] = updated_meta
        elif not is_row_based:
            skipped[vendor_key] = aliases

    if verbose:
        _print_matching_summary(vendor_map, matched, skipped, av_columns, normalized_columns)

    return matched


# === Helper: Normalize AV column names ===
def _normalize_column_names(columns: list[str]) -> dict:
    return {
        col: col.lower().replace("-", "").replace("_", "") for col in columns
    }


# === Helper: Match a vendor alias to any normalized AV column ===
def _find_matching_alias(aliases: list[str], normalized_columns: dict) -> str | None:
    for alias in aliases:
        normalized_alias = alias.lower().replace("-", "").replace("_", "")
        if normalized_alias in normalized_columns.values():
            return alias
    return None


def _resolve_column_name(alias: str, normalized_columns: dict) -> str:
    normalized_alias = alias.lower().replace("-", "").replace("_", "")
    for col, norm_col in normalized_columns.items():
        if norm_col == normalized_alias:
            return col
    return alias


# === Helper: Print debug summary of matched and skipped parsers ===
def _print_matching_summary(
    vendor_map: dict,
    matched: dict,
    skipped: dict,
    av_columns: list[str],
    normalized_columns: dict
):
    du.print_section("[PARSER] Vendor Parser Matching Summary")
    du.print_info(f"Total Parsers Available     : {len(vendor_map)}")
    du.print_success(f"Matched Parsers             : {len(matched)}")
    du.print_warning(f"Skipped/Unresolved Parsers  : {len(skipped)}")

    for vendor_key, aliases in skipped.items():
        du.print_warning(f"  - Skipped: {vendor_key}")
        for alias in aliases:
            _suggest_close_column_matches(alias, av_columns, normalized_columns)


# === Helper: Suggest fuzzy or partial AV column matches for an alias ===
def _suggest_close_column_matches(alias: str, av_columns: list[str], normalized_columns: dict):
    close_matches = difflib.get_close_matches(alias, av_columns, n=1, cutoff=0.8)
    if close_matches:
        du.print_debug(f"    -> Close match: {close_matches[0]}")
        return

    normalized_alias = alias.lower().replace("-", "").replace("_", "")
    loose_matches = [
        col for col, norm_col in normalized_columns.items()
        if normalized_alias in norm_col
    ]
    for match in loose_matches:
        du.print_debug(f"    -> Loose match: {match}")
