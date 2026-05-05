"""Output/export behavior and workbook controls."""

DEFAULT_OUTPUT_DIR = "output"
OUTPUT_RUNS_SUBDIR = "runs"
OUTPUT_BUNDLES_SUBDIR = "bundles"
OUTPUT_REPORTS_SUBDIR = "reports"
OUTPUT_DIAGNOSTICS_SUBDIR = "diagnostics"
OUTPUT_LATEST_SUBDIR = "latest"
OUTPUT_PROMOTED_SUBDIR = "promoted"

# When True, ``runs/<id>/diagnostics`` keeps run-id/timestamped names only; ``*.latest.*``
# mirrors live under global ``output/diagnostics`` (see obsidiandroid.common.output_hygiene).
SUPPRESS_LATEST_DUPLICATES_IN_RUN_DIRS = True

ENABLE_EXCEL_EXPORT = True
ENABLE_HTML_REPORTS = False
ENABLE_CONSOLIDATED_EXCEL_WORKBOOK = True
CONSOLIDATED_EXCEL_FILENAME = "obsidiandroid_outputs.xlsx"
CONSOLIDATED_EXCEL_INCLUDE_SOURCE_PREFIX = True
CONSOLIDATED_EXCEL_REPLACE_SHEETS = True
CONSOLIDATED_EXCEL_LOCK_TIMEOUT_SEC = 20.0
EXPORT_SHEET_LOG_EVERY_N = 10
EXPORT_VERBOSE_SHEET_LOGS = False
ENABLE_AV_PIPELINE_EXCEL_EXPORT = False

EXPORT_VENDOR_RAW_SHEETS_TO_EXCEL = False
EXPORT_VENDOR_RAW_ARTIFACTS = False
EXPORT_VENDOR_RAW_ARTIFACT_FORMATS = ["csv"]

# Confusion matrix artifact policy.
# one of: all, primary_only, primary_plus_ablation
CONFUSION_MATRIX_MODE = "primary_only"
