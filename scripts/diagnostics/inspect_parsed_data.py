# Filename: scripts/diagnostics/inspect_parsed_data.py
# Purpose  : Inspect and validate parsed vendor classification data and diagnose failure causes

from obsidiandroid.cli.ui import display as du
import pandas as pd

# Entry point to inspect parsed vendor data
def inspect(parsed_data: dict, verbose: bool = False, interactive: bool = False) -> bool:
    # Show top-level section header
    du.print_section("Parsed Vendor Data Inspection")

    # Check if the parsed_data is a valid dictionary
    if not isinstance(parsed_data, dict):
        du.print_error("[INSPECT] Parsed data must be a dictionary.")
        return False

    if not parsed_data:
        du.print_warning("[INSPECT] Parsed data dictionary is empty.")
        return False

    # Count vendor keys and total records across all vendor results
    total_vendors = len(parsed_data)
    total_records = _count_total_records(parsed_data)

    du.print_stat("Vendors Parsed", total_vendors)
    du.print_stat("Total Parsed Records", total_records)

    # Warn and exit if no valid records were found
    if total_records == 0:
        du.print_warning("[INSPECT] No sample records were found across vendors.")
        _print_zero_record_diagnostics(parsed_data)
        return False

    # Loop through and display per-vendor diagnostics
    if verbose:
        for vendor, records in parsed_data.items():
            _inspect_vendor_records(vendor, records, interactive)

    return True

# Count total sample records across all vendors
def _count_total_records(parsed_data: dict) -> int:
    count = 0
    for v in parsed_data.values():
        if isinstance(v, (list, tuple, set)):
            count += len(v)
        elif isinstance(v, pd.DataFrame):
            count += len(v)
        elif isinstance(v, dict):
            count += 1  # May represent one record or an unwrapped container
    return count

# Provide detailed vendor-level diagnostics if no records were found
def _print_zero_record_diagnostics(parsed_data: dict):
    du.print_subheader("[INSPECT] Zero Record Diagnostics")
    for vendor, records in parsed_data.items():
        if records is None:
            du.print_warning(f"[INSPECT] Vendor {vendor} returned None.")
        elif isinstance(records, (list, tuple, set)) and len(records) == 0:
            du.print_warning(f"[INSPECT] Vendor {vendor} returned an empty list.")
        elif isinstance(records, pd.DataFrame) and records.empty:
            du.print_warning(f"[INSPECT] Vendor {vendor} returned an empty DataFrame.")
        elif isinstance(records, dict):
            du.print_info(f"[INSPECT] Vendor {vendor} returned a dict object with keys: {list(records.keys())[:5]}")
        else:
            du.print_info(f"[INSPECT] Vendor {vendor} returned type: {type(records).__name__}")

# Inspect one vendor's parsed record list, dict, or dataframe
def _inspect_vendor_records(vendor: str, records, interactive: bool):
    if records is None:
        du.print_warning(f"[INSPECT] Vendor {vendor} has no records (None).")
        return

    # If list-like, inspect structure and show preview
    if isinstance(records, (list, tuple, set)):
        count = len(records)
        du.print_info(f"\n→ Vendor: {vendor} | Records: {count}")
        if count == 0:
            du.print_warning(f"[INSPECT] Vendor {vendor} has an empty list.")
            return

        sample = next(iter(records), None)
        if hasattr(sample, '__dict__'):
            du.print_debug(f"First record fields: {list(vars(sample).keys())[:5]}")
        elif isinstance(sample, dict):
            du.print_debug(f"First record keys: {list(sample.keys())[:5]}")
        else:
            du.print_warning(f"[INSPECT] Unexpected record type for {vendor}: {type(sample).__name__}")

        if interactive:
            _print_interactive_preview(vendor, records)

    # If dataframe, summarize and optionally preview first few rows
    elif isinstance(records, pd.DataFrame):
        du.print_info(f"\n→ Vendor: {vendor} | DataFrame shape: {records.shape}")
        if records.empty:
            du.print_warning(f"[INSPECT] Vendor {vendor} returned an empty DataFrame.")
        elif interactive:
            _print_interactive_preview(vendor, records.head(3).to_dict(orient="records"))

    # If dict or other type, just log what we know
    elif isinstance(records, dict):
        du.print_info(f"\n→ Vendor: {vendor} | Dict record keys: {list(records.keys())[:5]}")
    else:
        du.print_warning(f"[INSPECT] Vendor {vendor} returned unsupported type: {type(records).__name__}")

# Preview selected samples from the record list or dicts
def _print_interactive_preview(vendor: str, records: list):
    du.print_section(f"Preview for {vendor}")
    for i, r in enumerate(records[:3]):
        du.print_note(f"Sample #{i + 1}")
        if hasattr(r, '__dict__'):
            for k, v in vars(r).items():
                du.print_info(f"  {k}: {v}")
        elif isinstance(r, dict):
            for k, v in r.items():
                du.print_info(f"  {k}: {v}")
        else:
            du.print_info(str(r))
