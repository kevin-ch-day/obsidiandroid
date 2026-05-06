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

FEATURE_TOP_K = 8
FEATURE_SCORE_FIELD = "Final ML Score"
FEATURE_EXCLUDE_VENDOR_CATEGORIES = []
FEATURE_MIN_VENDOR_SCORE = 0.0
FEATURE_MIN_SELECTED_VENDORS = 4
FEATURE_FAIL_ON_LOW_VENDOR_COUNT = False
FEATURE_ENFORCE_TRUSTED_VENDOR = False
ENABLE_LEAKAGE_SAFE_VENDOR_SCORING = True
LEAKAGE_SAFE_SCORE_FIELD = "Leakage Safe Score"

ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS = False
DYNAMIC_GENERIC_MIN_COVERAGE_PCT = 5.0
DYNAMIC_GENERIC_MAX_COLUMNS = 40
PARSER_ONBOARDING_CANDIDATE_MIN_COVERAGE_PCT = 80.0
PARSER_ONBOARDING_CANDIDATE_MAX_ROWS = 16

ENABLE_SAMPLE_METADATA_FEATURES = True
ENABLE_PERMISSION_FEATURES = True
PERMISSION_MIN_SUPPORT = 2
PERMISSION_MAX_FEATURES = 0
