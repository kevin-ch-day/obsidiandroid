"""Engine scoring, vendor selection, parser onboarding, and feature toggles."""

ENABLE_ABSOLUTE_ENGINE_TIERING = True
AV_VERDICT_QUERY_CHUNK_SIZE = 500
ENABLE_AV_VERDICT_QUERY_CACHE = True
AV_VERDICT_QUERY_CACHE_SIZE = 2
ENGINE_TIER_THRESHOLDS = {
    "high": 80.0,
    "moderate": 60.0,
    "low": 40.0,
    "weak": 20.0,
}

# Composite ``ML Readiness Score`` weights (applied after per-field normalization in
# ``obsidiandroid.evaluation.engine_scoring_summary``). Values are renormalized to sum to 1.
# Default shifts mass away from ``threat_signal_score`` when the DB column has little spread
# (min–max normalization then adds almost no discriminative signal).
ENGINE_READINESS_SCORE_WEIGHTS = {
    "malicious_pct": 0.45,
    "coverage_pct": 0.40,
    "threat_signal_score": 0.15,
}

# Fields to normalize with percentile rank in [0, 1] instead of min–max (better when the
# raw range is extremely narrow across engines).
ENGINE_READINESS_PERCENTILE_RANK_FIELDS: tuple[str, ...] = ("threat_signal_score",)

# Tukey fence multiplier for readiness-score IQR outlier tagging in summaries.
ENGINE_READINESS_IQR_MULTIPLIER = 1.5
ENGINE_MIN_SAMPLES_SCANNED = 10
ENGINE_MIN_COVERAGE_PCT = 20.0
ENGINE_MIN_POSITIVE_FLAGS = 5
ENGINE_MIN_DETECTION_PCT = 1.0
ENGINE_EXCLUDE_ZERO_DETECTION = True

# Defines which binary AV-verdict columns enter the headline feature matrix.
# ``all_observed`` preserves the established baseline: every observed engine is
# available, subject to train-only low-information pruning.  ``lifecycle_included``
# is an explicitly scoped experimental surface that retains only engines passing
# the readiness lifecycle gate.  Do not change this default to optimise a result;
# compare the two scopes on a frozen cohort and split first.
AV_BINARY_FEATURE_ENGINE_SCOPE = "all_observed"

FEATURE_TOP_K = 8
FEATURE_SCORE_FIELD = "Final ML Score"
FEATURE_EXCLUDE_VENDOR_CATEGORIES = []
FEATURE_MIN_VENDOR_SCORE = 0.0
FEATURE_MIN_SELECTED_VENDORS = 4
FEATURE_FAIL_ON_LOW_VENDOR_COUNT = False
FEATURE_ENFORCE_TRUSTED_VENDOR = False
ENABLE_LEAKAGE_SAFE_VENDOR_SCORING = True
LEAKAGE_SAFE_SCORE_FIELD = "Leakage Safe Score"
# Parsed vendor family/type strings are label-adjacent evidence.  They are not
# part of the headline family-classification feature contract unless an
# explicitly scoped experimental profile opts in.
ENABLE_LABEL_DERIVED_VENDOR_FEATURES = False
# The primary family-classification benchmark must use only label-independent
# predictive signals. Enabling parser semantics creates a separately named
# AV-assisted attribution experiment and is forbidden in publication mode.
PRIMARY_FEATURE_CONTRACT_ID = "family_classification_label_independent_v1"
AV_ASSISTED_FEATURE_CONTRACT_ID = "av_assisted_family_attribution_v1"

ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS = False
DYNAMIC_GENERIC_MIN_COVERAGE_PCT = 5.0
DYNAMIC_GENERIC_MAX_COLUMNS = 40
PARSER_ONBOARDING_CANDIDATE_MIN_COVERAGE_PCT = 80.0
PARSER_ONBOARDING_CANDIDATE_MAX_ROWS = 16

ENABLE_SAMPLE_METADATA_FEATURES = True
ENABLE_PERMISSION_FEATURES = True
PERMISSION_MIN_SUPPORT = 2
PERMISSION_MAX_FEATURES = 0
