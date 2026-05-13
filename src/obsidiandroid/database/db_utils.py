# Filename: src/obsidiandroid/database/db_utils.py
# db_utils.py
# Utility functions for AV engine column filtering and metadata lookups
#
# Canonical implementation; ``database.db_utils`` is an identity shim.

from database import db_engine
from database import schema_map
from obsidiandroid.cli.ui import display as du

# Columns to exclude from analysis in the vendor verdict table
AV_ENGINES_RESULTS_IGNORED_COLS = {
    "sample_id", "record_id", "updated_at", "timeout", "confirmed_timeout", "record_created_at",
    "type_unsupported", "malicious", "suspicious", "undetected", "total_engines"
}

# Get a list of usable AV engine detection columns from the wide verdict table
def get_valid_detection_columns(check_empty: bool = False, preview: int = 10) -> list:
    try:
        verdicts_table = schema_map.table("vendor_verdicts")
        du.print_debug(f"[db_utils] Fetching columns from {verdicts_table}...")
        all_columns = db_engine.get_table_columns(verdicts_table)

        valid_columns = [col for col in all_columns if col not in AV_ENGINES_RESULTS_IGNORED_COLS]
        du.print_debug(f"[db_utils] Found {len(valid_columns)} usable engine columns.")
        if preview:
            du.print_debug(f"[db_utils] Column preview: {valid_columns[:preview]}")

        if not valid_columns:
            du.print_warning("[db_utils] No valid AV detection columns found.")
            return []

        if check_empty:
            du.print_debug("[db_utils] Checking each column for at least 1 non-null value...")
            non_empty = []
            for col in valid_columns:
                try:
                    test_query = (
                        f"SELECT `{col}` FROM {verdicts_table} "
                        f"WHERE `{col}` IS NOT NULL LIMIT 1"
                    )
                    _, rows = db_engine.execute_query(test_query, fetch=True, return_columns=True)
                    if rows:
                        non_empty.append(col)
                except Exception as check_error:
                    du.print_warning(f"[db_utils] Error checking column '{col}': {check_error}")
            du.print_debug(f"[db_utils] Non-empty detection columns: {len(non_empty)}")
            return non_empty

        return valid_columns

    except Exception as e:
        du.print_error(f"[db_utils] Failed to get detection columns: {e}")
        return []

# Get trusted and active AV engine names from virustotal_vendor_engines
def get_trusted_active_engine_names(only_existing: bool = False, sort: bool = True) -> list:
    try:
        vendors_table = schema_map.table("vendor_engines")
        engine_col = schema_map.column("vendor_engines", "engine_name")
        trusted_col = schema_map.column("vendor_engines", "trusted_flag")
        active_col = schema_map.column("vendor_engines", "active_flag")
        query = """
            SELECT {engine_col} AS engine_name
            FROM {vendors_table}
            WHERE {trusted_col} = 1 AND {active_col} = 1
        """
        query = query.format(
            engine_col=engine_col,
            vendors_table=vendors_table,
            trusted_col=trusted_col,
            active_col=active_col,
        )
        _cols, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
        trusted = [row[0] for row in rows]

        if not trusted:
            du.print_warning("[db_utils] No trusted and active AV engines found.")
            return []

        du.print_debug(f"[db_utils] Retrieved {len(trusted)} trusted + active engines.")

        if only_existing:
            existing = get_valid_detection_columns()
            trusted = [e for e in trusted if e in existing]
            du.print_debug(f"[db_utils] Filtered to {len(trusted)} engines also present in results table.")

        if sort:
            trusted.sort()

        return trusted

    except Exception as e:
        du.print_error(f"[db_utils] Failed to retrieve trusted engine names: {e}")
        return []
