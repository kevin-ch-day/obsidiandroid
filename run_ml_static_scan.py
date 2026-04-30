# Filename : run_ml_static_scan.py
# Purpose  : Launch static scan for ML .predict()/.predict_proba() misuse in ObsidianDroid

import sys
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from testing import scan_ml_predict_misuse

# --- Paths ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "ml_predict_misuse_warnings.log")

# Set timezone to Central Time (Minneapolis)
CENTRAL_TZ = ZoneInfo("America/Chicago")


def ensure_log_directory(path: str):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"[INFO] Created log directory: {path}")


def clear_log_file(path: str):
    """Clears the existing log file content."""
    with open(path, "w", encoding="utf-8") as f:
        f.truncate(0)
    print(f"[INFO] Cleared previous log at: {path}")


def print_banner():
    print("\n" + "=" * 80)
    print(" ObsidianDroid Static ML Predict() Misuse Scanner")
    print("=" * 80)


def main():
    print_banner()
    ensure_log_directory(LOG_DIR)
    clear_log_file(LOG_FILE)

    start_time = datetime.now(CENTRAL_TZ)
    print(f"[INFO] Scan started at        : {start_time.isoformat()}")
    print(f"[INFO] Scanning source path   : {BASE_DIR}")
    print(f"[INFO] Output log destination : {LOG_FILE}\n")

    try:
        file_count, warning_count = scan_ml_predict_misuse.run_static_predict_scan(
            base_dir=BASE_DIR,
            log_file=LOG_FILE
        )
    except Exception as e:
        print(f"[ERROR] Static scan failed: {e}")
        sys.exit(1)

    end_time = datetime.now(CENTRAL_TZ)
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 80)
    print(f"[SUMMARY] Files scanned       : {file_count}")
    print(f"[SUMMARY] Warnings generated  : {warning_count}")
    print(f"[SUMMARY] Elapsed time (sec)  : {duration:.2f}")
    print(f"[SUMMARY] Scan completed at   : {end_time.isoformat()}")
    print("=" * 80 + "\n")

    sys.exit(warning_count)


if __name__ == "__main__":
    main()
