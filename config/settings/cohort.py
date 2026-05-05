"""Dataset cohort filters and split controls."""

ENABLE_TAXONOMY_COHORT = True
COHORT_TYPE_SLUG = "banker"
COHORT_MIN_SAMPLES_PER_FAMILY = 3
COHORT_REQUIRE_MAPPED_FAMILY = True
COHORT_REQUIRE_SHA256 = True
COHORT_ALLOW_MISSING_PACKAGE_NAME = True
COHORT_LIMIT = None

TRAIN_TEST_SPLIT = 0.25
RANDOM_STATE = 42
AUTO_ADJUST_TRAIN_TEST_SPLIT = True
MIN_TEST_SAMPLES_PER_CLASS = 2

# Prefer ``sklearn.model_selection.GroupShuffleSplit`` when runtime metadata exposes
# package_name / sha256 lineage (train/test shards never share a lineage group).
# Headline-only: ablations keep stratified label splits for comparability tooling.
ENABLE_GROUP_AWARE_TRAIN_TEST_SPLIT = False

