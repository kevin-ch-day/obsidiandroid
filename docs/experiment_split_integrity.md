# PI V2 outer experiment membership

The generic runner prepares one target-resolved experiment plan after sample
preparation and before learned feature construction. It reuses the generic
partition algorithms; the vocabulary builder and trainer no longer independently
choose training membership for a governed V2 run.

`obsidiandroid.modeling.experiment_split` records exact source IDs/SHA-256s,
eligible labels and exclusions, target, profile/configuration and evidence
digests, eligibility implementation bytes, split policy, seed, ordered training
and evaluation membership, and permission support. The immutable plan has
canonical JSON serialization and a SHA-256 identity. Restoring JSON does not
restore source authorization or the live verified vocabulary receipt.

Family, type and family-within-type eligibility are separate. Family authority
uses the maintained alignment rules; missing/unknown type labels are excluded
from type/composite targets. Support follows the resolved runtime policy. Sparse
label grouping is unsupported for this contract because it changes target
identity. Subsequent alignment verifies exact source identity and consumes the
plan; later support filtering cannot independently alter its population.

The trainer validates label/feature row alignment, exact eligible membership,
source approval, sealed permission vocabulary membership and values, split-cache
identity and feature-selection fit IDs before fitting. A heldout-only permission
token cannot enter the vocabulary. Missing coverage is never filled as absence.
SMOTE/ROS retains separate physical source IDs; appended training rows are not
catalog identities. The receipt records additional rows and resampling metadata,
and altered/reordered original rows fail validation before CV or estimator calls.
Mandatory group/temporal policies cannot silently downgrade in governed planning.
Legacy non-V2 training keeps its existing partition behavior.

## Current authorization limit

The installed PI V2 approval-v1 contract provides exact-export feature acceptance,
not a target-specific training scope. The production authorization adapter
therefore rejects governed training with an explicit diagnostic. There is no
configuration flag to bypass it. Existing export acceptance and its frozen
1,450/363 split remain unchanged. Synthetic tests replace that authority boundary
only for controlled fixtures; they do not approve a real experiment.

The all-catalog permission requirement and source-coverage gate remain intact.
Real target-specific V2 training requires a separately reviewed authority contract;
this change does not install one, expand coverage, or change evidence states.

## Limits and validation

This is outer-membership integrity, not a claim that every transform is nested
within inner CV. Existing CV selection scope, categorical vocabulary behavior,
label provenance, broad population coverage and evaluation policies remain
separate roadmap items. The frozen ABC contract is unchanged.

Offline tests: `tests/test_experiment_split_integrity.py` and the integration
lane `tests/test_experiment_runner_integration.py`. The latter keeps the real
runner, PI builder/fusion, alignment, classifier pipeline and generic trainer;
source acquisition, synthetic authority, model reporting and estimators are
controlled fixtures. Use isolated output/log directories and no live resources.

## Bounded retained-AV model comparison

`python -m obsidiandroid.modeling.av_only_experiment` accepts `--model`
`logistic_regression`, `random_forest`, or `xgboost`. Its default remains
plan-only; `--train` fits one model in a new external output directory.
Required arguments are `--snapshot`, `--snapshot-sha256`, and `--output`.
All three models consume the same validated lineage partition and train-only
feature selection. XGBoost early stopping is disabled for this fixed-parameter
comparison. No grid search, CV, SMOTE, permission features, or Core persistence
is enabled. A previously inspected split is development comparison evidence,
not an untouched final test set or an authorization to tune against its scores.

`permission_v2_export.describe_v2_occurrences` validates the independent export
anchor and exact occurrence identities, returning descriptive frequencies and
membership without a training vocabulary or training authorization. Missing
export coverage is unknown, never a zero-permission observation.

`vendors.retained_analysis.describe_retained_vendors` validates the retained
report snapshot before parsing vendor labels. It preserves verdict categories,
parser errors, known-family votes, and ties. Unweighted plurality and parser
quality are descriptive; neither establishes independent truth, vendor
accuracy, lifecycle eligibility, or a permissible semantic model predictor.

## Expanded AV development CV

`modeling.expanded_av_experiment.execute` accepts an exact retained snapshot
and its SHA-256, plus the consumed prior partition and its SHA-256. Default
execution is plan-only. It excludes every connected component containing a
prior holdout identity before admitting families with at least 20 records and
four lineage components. Its fixed three-fold grouped LR baseline requires
10 training and three validation records per class in every fold; infeasible
folds fail without fallback or seed search. This is development CV, not an
independent held-out evaluation. AV vocabulary, constant-feature removal and
scaling are fitted inside each training fold. Prediction probabilities are
uncalibrated. No parameter search or lifecycle-based engine filtering occurs.

Retained report validation now permits up to 3,000 exact identities, allowing
lineage construction across the 2,249 reviewed expansion candidates. Source
files remain bounded to 128 MiB by experiment entrypoints. Expanding this
validation bound does not relax source hashes, label authority, grouping,
feature identity, or split support. New outputs must be outside the repository
and must not already exist.

## Full-catalog AV-only workflow

`modeling.full_catalog_av.run` consumes a SHA-256-bound complete source manifest
and bounded compressed retained-report chunks. It validates every catalog
identity, records missing or invalid reports, and runs descriptive vendor
analysis across the full selected catalog. It has no database/provider adapter.
Single-record report chunks are accepted for description; training support
requirements remain unchanged. The original permission-required full-catalog
profile is unchanged.

Lineage components are recomputed across the entire catalog, including unknown
and unreviewed records that can bridge reviewed samples. Only agreeing reviewed
labels with validated reports and package identity may enter training. Consumed
holdout components are excluded. Family and per-fold support checks must pass;
there is no random split fallback. Fixed LR/RF/XGBoost development comparisons
share three grouped folds with fold-local AV vocabulary and preprocessing.
Unknown samples receive coverage/semantic reports, not closed-set family
predictions. No permission features, canonical writes, parameter search or
independent-test claim is part of this workflow. Output must be a new directory
outside the checkout; full-catalog source collection is a separate read-only
operation. Resource limits belong to the explicit execution wrapper.

## Retained lineage policy v2 and the 1,000-sample gate

`features.av_lineage` is the shared grouping implementation. V2 corrects missing
package values that were stringified as `none` in retained-report metadata.
Missing and placeholder identifiers never create graph edges. It also excludes
standalone signer edges for the exact public AOSP test certificate SHA-1
`61ed377e85d386a8dfee6b864bd85b0bfaa5af81`, independently matched to the certificate
at AOSP build revision `695b28f`; its DER SHA-256 is
`a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc`.
Public test signing cannot establish common author identity. The certificate
remains recorded; valid package, other signer and similarity constraints remain.
See [AOSP signing guidance](https://source.android.com/docs/core/ota/sign_builds).

Vhash is a structural similarity identifier, not an exact file identity (see
[VirusTotal file attributes](https://docs.virustotal.com/reference/files)). In the intermediate v2 audit, equality edges remained conservative contamination
constraints pending review. V3 below supersedes that runtime policy. High degree
alone does not authorize deleting an edge. Historical packets remain immutable
and retain their original policy/results; new experiment manifests record v2.

`modeling.scale_admission.preview_scale` is a plan-only admission check for a
1,000-sample final fit. It records exact candidate and fold IDs, class support,
consumed-evaluation exclusion, and every blocker. Over 1,000 candidate records
cannot override inadequate class support inside grouped folds. A feasible plan
still reports zero fitted records. No model is fitted or promoted by this helper.


## V3: no standalone structural-hash lineage

The v2 audit confirmed that vhash-only transitive links caused the remaining
scale blocker. V3 retains vhash values and exact cross-fold relationship receipts,
but a structural-hash match alone no longer asserts a lineage component.
Package, non-public certificate and exact TLSH/ssdeep relationships remain
constraints. A vhash match corroborated by those relationships stays connected
through them. This policy is based on the documented meaning of vhash, not on
classifier scores or a chosen model. It does not prove independence of every
remaining component; similar-file leakage remains an explicitly audited risk.

The expanded experiment may support exploratory grouped CV and final fixed
baseline refits; it does not establish an untouched independent benchmark.
Previously reported v1/v2 membership and metrics remain historical evidence and
must not be silently described as v3 results. Source manifests record
`retained_lineage_v3_no_standalone_vhash`.

`modeling.av_representations` keeps detection-only missingness as NaN, requiring
train-fitted imputation. Observation-only retains completed-verdict bits.
Combined features preserve both bits, so an unavailable detection placeholder
is distinguishable from a completed negative verdict. Semantic family/type
strings are rejected as feature columns. Nested tuning still requires adequate
class support in every inner grouped fold; a feasible outer split is insufficient.
