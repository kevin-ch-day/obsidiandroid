"""Methodology artifacts, ablation controls, and results warehouse flags."""

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
# Deprecated: strictness is profile-driven via `evidence_mode`.
STRICT_EVIDENCE_MODE_FOR_NON_DEV = False
EVIDENCE_HARD_FAIL_MISSING_PACKAGE = True
ALLOW_VENDOR_FALLBACK_FOR_WIDTH = False
ANALYSIS_SCOPE = "all"  # one of: all, type, family, banker
FIGURE_MODE = "analysis"  # one of: analysis, paper
ENABLE_BANKER_CASE_STUDY_ARTIFACTS = False
ENABLE_LEGACY_CANONICAL_HEATMAP_EXPORT = False
ENABLE_PERMISSION_TRENDS_BUNDLE_ZIP = False
ENABLE_PERMISSION_TRENDS_LATEST_MIRROR = False
CANONICAL_TYPE_SLUGS = (
    "banker",
    "adware",
    "stealer",
    "sms-trojan",
    "rat",
    "spyware",
    "ransomware",
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
    # Data-driven aliases from taxonomy_noncanonical_type_tokens diagnostics.
    "trojan": "banker",
    "dropper": "adware",
    "generic": "banker",
    "backdoor": "banker",
    "pup": "banker",
    "botnet": "banker",
    "spoof": "banker",
}
TAXONOMY_NONCANONICAL_DOMINANCE_WARN_THRESHOLD = 0.60
TAXONOMY_NONCANONICAL_DOMINANCE_MIN_COUNT = 50
MAX_PERMISSIONS_HEATMAP = 16
PERMISSION_SELECTION_METHOD = "discriminability"  # one of: discriminability, prevalence, dangerous
MIN_FAMILY_SUPPORT_FOR_VISUAL = 20
MAX_FAMILY_VISUAL_COUNT = 12
MAX_FAMILY_HEATMAP_PERMISSIONS = 25
EXCLUDE_UNKNOWN_TYPE_IN_VISUALS = True
MAX_TIME_SERIES_LINES = 4
PAPER2_STRICT_EXPORT_PROFILE = True
