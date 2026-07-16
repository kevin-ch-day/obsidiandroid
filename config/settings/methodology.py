"""Methodology artifacts, ablation controls, and results warehouse flags."""

import os

ENABLE_FEATURE_CONTRACT_EXPORT = True
ENABLE_FEATURE_BUILD_COVERAGE_EXPORT = True
ENABLE_LEAKAGE_ASSESSMENT_EXPORT = True
ENABLE_ABLATION_EXPERIMENTS = True
ENABLE_PERMISSION_TRENDS_REPORT = True
ENABLE_LABEL_RESOLUTION_STAGE = True
ENABLE_ENGINE_WEIGHT_DB_SUMMARY = True
ENABLE_FAMILY_DISTRIBUTION_REPORT = True
ENABLE_RESULTS_WAREHOUSE_EXPORT = True
CONSENSUS_MIN_VENDOR_COUNT = 5
GENERIC_MIN_SUPPORT = 30
BANKER_PATTERN_CLUSTER_K = 3
CONSENSUS_BOOTSTRAP_RESAMPLES = 2000
ABLATION_MODEL_LIST = []
# When True, ablations are suppressed if training model_list resolves to exactly one trainer.
SKIP_ABLATIONS_FOR_SINGLE_MODEL = True
# When False, methodology ablations only evaluate the canonical family-canonical headline target (faster).
ENABLE_ABLATION_MULTI_LABEL_TARGETS = True
ABLATION_REQUIRE_FROZEN_UNIVERSE = True
ABLATION_MAX_MISMATCH_RATIO = 0.01

# When True (default), ablation feature matrices are reindexed to the frozen label cohort
# with zero-fill for missing vendor/permission rows so cohort size is identical across
# feature sets (paper-safe). Set False to use legacy intersection-only alignment.
ABLATION_COHORT_REINDEX_ZERO_FILL = True
ENABLE_ABLATION_CROSS_VALIDATION = False
ENABLE_ABLATION_MODEL_EXPORT = False
PAPER_HEATMAP_TOP_K = 35
PAPER_DANGEROUS_HEATMAP_TOP_K = 25
FAIL_FAST_PIPELINE_EXCEPTIONS_IN_PAPER_MODE = True
FAIL_FAST_TRAINING_EXCEPTIONS_IN_PAPER_MODE = True
# A failed full-prediction/result checkpoint invalidates a model run.  Stop the
# headline training stage before spending time on remaining models or reports.
# Ablation cells deliberately bypass this guard so their resilience policy can
# record individual unavailable cells.
FAIL_FAST_TRAINING_MODEL_FAILURES = True
EVIDENCE_HARD_FAIL_MISSING_PACKAGE = True
ALLOW_VENDOR_FALLBACK_FOR_WIDTH = False
ANALYSIS_SCOPE = "all"  # one of: all, type, family, banker
FIGURE_MODE = "analysis"  # one of: analysis, paper
ENABLE_BANKER_CASE_STUDY_ARTIFACTS = False
ENABLE_LEGACY_CANONICAL_HEATMAP_EXPORT = False
ENABLE_PERMISSION_TRENDS_BUNDLE_ZIP = False
ENABLE_PERMISSION_TRENDS_LATEST_MIRROR = False
# When True, permission-trends bundle writers also emit run_id-suffixed CSV/JSON/TXT/PNG
# alongside ``*.latest.*`` peers. Default False; the pipeline runner sets True in
# effective evidence mode unless the profile sets ``runtime_overrides`` for this key.
WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS = False
CANONICAL_TYPE_SLUGS = (
    "banker",
    "adware",
    "backdoor",
    "cryptojacking",
    "downloader",
    "dropper",
    "miner",
    "ransomware",
    "rat",
    "riskware",
    "rootkit",
    "sms-trojan",
    "spyware",
    "stalkerware",
    "stealer",
    "subscription-fraud",
    "trojan",
)
TYPE_LABEL_ALIAS_MAP = {
    "spy": "spyware",
    "bank": "banker",
    "banking": "banker",
    "sms": "sms-trojan",
    "sms_trojan": "sms-trojan",
    "remote_access_trojan": "rat",
    "remote-access-trojan": "rat",
    "ransom": "ransomware",
    # Do not coerce broad labels such as ``trojan`` or ``dropper`` into banker
    # or adware.  Those are distinct taxonomy types; generic tokens remain
    # auditable rather than becoming fabricated type evidence.
}
TAXONOMY_NONCANONICAL_DOMINANCE_WARN_THRESHOLD = 0.60
TAXONOMY_NONCANONICAL_DOMINANCE_MIN_COUNT = 50
# When True alongside paper mode, taxonomy mismatches beyond max allowed raise on finalize.
STRICT_TAXONOMY_MISMATCH_BLOCKING = False
TAXONOMY_MISMATCH_STRICT_MAX_ALLOWED = 0
ENABLE_FEATURE_COLUMN_SURVIVAL_EXPORT = True
# Evidence-mode guard for permission-trend JSD degenerate skips (pairwise probability vectors).
PERMISSION_JSD_DEGENERATE_EVIDENCE_MAX_SKIPS = 10**9
MAX_PERMISSIONS_HEATMAP = 16
PERMISSION_SELECTION_METHOD = "discriminability"  # one of: discriminability, prevalence, dangerous
MIN_FAMILY_SUPPORT_FOR_VISUAL = 20
MAX_FAMILY_VISUAL_COUNT = 12
MAX_FAMILY_HEATMAP_PERMISSIONS = 25
EXCLUDE_UNKNOWN_TYPE_IN_VISUALS = True
MAX_TIME_SERIES_LINES = 4
PAPER2_STRICT_EXPORT_PROFILE = True

# Evidence/publication runs default to no-SMOTE for stricter reproducibility.
# Operators can opt back in with `OBSIDIAN_ENABLE_SMOTE_IN_EVIDENCE_MODE=1`, or
# continue to force-disable with the older `OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1`.
_DISABLE_SMOTE_EV_RAW = os.getenv("OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE", "")
_ENABLE_SMOTE_EV_RAW = os.getenv("OBSIDIAN_ENABLE_SMOTE_IN_EVIDENCE_MODE", "")
_TRUTHY_ENV = {"1", "true", "yes", "on"}
_FALSEY_ENV = {"0", "false", "no", "off"}

if str(_ENABLE_SMOTE_EV_RAW).strip().lower() in _TRUTHY_ENV:
    DISABLE_SMOTE_IN_EVIDENCE_MODE = False
elif str(_DISABLE_SMOTE_EV_RAW).strip().lower() in _TRUTHY_ENV:
    DISABLE_SMOTE_IN_EVIDENCE_MODE = True
elif str(_DISABLE_SMOTE_EV_RAW).strip().lower() in _FALSEY_ENV:
    DISABLE_SMOTE_IN_EVIDENCE_MODE = False
else:
    DISABLE_SMOTE_IN_EVIDENCE_MODE = True
