"""Reproducibility snapshot, cohort lock, and cache controls."""

ENABLE_SNAPSHOT_LOCK = False
SNAPSHOT_LOCK_FILE = "output/diagnostics/analysis_snapshot.lock.csv"
REQUIRE_SNAPSHOT_LOCK_IN_EVIDENCE_MODE = True
EXPORT_ANALYSIS_SNAPSHOT = True
# Bootstrap defaults only; pipeline runtime overrides with run-scoped names under output/runs/<id>/diagnostics.
ANALYSIS_SNAPSHOT_FILE = "output/diagnostics/analysis_snapshot.latest.csv"
ANALYSIS_SNAPSHOT_META_FILE = "output/diagnostics/analysis_snapshot.latest.meta.txt"
ANALYSIS_SNAPSHOT_CONFLICT_FILE = (
    "output/diagnostics/analysis_snapshot_label_conflicts.latest.csv"
)
ANALYSIS_SELECTION_RULE_VERSION = "snapshot_v1_android_apk_mapped_quality"
ENABLE_PAPER_TIME_WINDOW = True
PAPER_TIME_WINDOW_START_UTC = "2020-01-01T00:00:00Z"
PAPER_TIME_WINDOW_END_MODE = "run_date_eod_utc"
DATASET_TIME_CONTRACT_FILE = "output/diagnostics/dataset_time_contract.latest.json"
PAPER_COHORT_SAMPLE_IDS_FILE = "output/diagnostics/paper_cohort_sample_ids.csv"

# Backward-compatible aliases.
ENABLE_COHORT_LOCK = ENABLE_SNAPSHOT_LOCK
COHORT_LOCK_FILE = SNAPSHOT_LOCK_FILE
EXPORT_COHORT_SNAPSHOT = EXPORT_ANALYSIS_SNAPSHOT
COHORT_SNAPSHOT_FILE = ANALYSIS_SNAPSHOT_FILE
COHORT_SNAPSHOT_META_FILE = ANALYSIS_SNAPSHOT_META_FILE

EXPORT_ALIGNED_TRAINING_CACHE = True
ALIGNED_FEATURE_CACHE_FILE = "output/diagnostics/aligned_features.latest.csv.gz"
ALIGNED_LABEL_CACHE_FILE = "output/diagnostics/aligned_labels.latest.csv"
