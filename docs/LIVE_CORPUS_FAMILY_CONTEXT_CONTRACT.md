# Live-corpus family context contract

Offline research contract for governed live-corpus **family context**,
**external-evidence separation**, **type-assignment audit**, **static hypothesis
validation**, and **dominant-family permission robustness**.

Composers read completed-run artifacts only. They do **not** query Core,
Erebus, or Permission Intel; do **not** write taxonomy or warehouse state; do
**not** run the pipeline; and do **not** treat external family writeups as
local ground truth or model features.

## Contract version

| Field | Value |
| --- | --- |
| `live_corpus_family_context_contract_version` | `1.0.0` |

## Evidence states

Every durable claim row carries an explicit evidence state:

| State | Meaning |
| --- | --- |
| `LOCAL_OBSERVED` | Fact measured from run-local artifacts (counts, prevalences, years, batches). |
| `LOCAL_AUTHORITY` | Governed identity from local authority/label surfaces present in the run (family_id, type_slug, canonicalization path). |
| `EXTERNAL_REPORTED` | Concise paraphrase of public reporting; not local truth. |
| `HYPOTHESIS` | Testable expectation derived from external reporting or research questions. |
| `LOCALLY_SUPPORTED` | Hypothesis with local static-permission support under stated thresholds. |
| `LOCALLY_MIXED` | Local static evidence partially agrees / partially disagrees. |
| `NOT_OBSERVED` | Expected static signal absent in local declarations (does **not** falsify runtime-only public claims). |
| `NOT_TESTABLE_STATICALLY` | Capability cannot be validated from static permission declarations alone. |
| `IDENTITY_UNCERTAIN` | Family slug / public identity mapping is ambiguous in this corpus. |

### Separation rules

1. Do not promote `EXTERNAL_REPORTED` into `LOCAL_OBSERVED` or `LOCAL_AUTHORITY`.
2. Do not label `NOT_OBSERVED` as proof that public reporting is wrong.
3. Do not infer runtime behavior, dual roles, or campaign geography from names alone.
4. Do not import external text as training features or taxonomy repairs.
5. Headline reports must not expose sample hashes or package names.

## Source identity gate

Before analysis, composers verify:

- slot path run ID matches the requested run ID;
- `run_manifest.json` `run_id` agrees;
- `.COMPLETE` present and `.RUNNING` absent when claiming a completed run.

Mismatch → hard failure (no partial inventory).

## Generated artifacts (run-scoped, not committed)

Under `diagnostics/live_corpus_family_context/`:

| File | Role |
| --- | --- |
| `family_context_inventory.csv` | Top-family local inventory |
| `family_external_context_matrix.csv` | External ↔ local evidence matrix |
| `dominant_family_robustness.csv` | Type-level leave-dominant profile sensitivity |
| `family_type_assignment_audit.csv` | Governed type audit for named families |
| `hypothesis_validation.csv` | Static-permission hypothesis tests |
| `live_corpus_family_context.md` | Concise corpus-context document |
| `manifest.json` + SHA-256 | Reproducibility |

## Dominant-family type robustness classes

Type-level profile comparison (full / family-balanced / exclude largest /
exclude second-largest / exclude both when support remains):

| Class | Meaning |
| --- | --- |
| `robust_across_families` | Rank correlation high and prevalence shifts small after removals |
| `moderately_family_sensitive` | Material but non-collapsing shifts |
| `dominant_family_driven` | Large JSD / rank break / headline loss after removing top family(ies) |
| `insufficient_family_support` | Too few independent families |
| `insufficient_sample_support` | Too few samples after exclusion |

## Hypothesis static tests

Only permission-declaration hypotheses are tested. Overlay/virtualization/
cloud-C2/runtime ATS claims are `NOT_TESTABLE_STATICALLY` unless a concrete
manifest permission set is specified.

## Implementation

Type-level leave-dominant profile metrics are implemented in
`obsidiandroid.reporting.dominant_family_profile_sensitivity` and emitted as
`dominant_family_robustness.csv` by the live-corpus family-context composer.

## Related contracts

- [`PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](PERMISSION_GOVERNANCE_LANE_CONTRACT.md)
- [`TYPE_PERMISSION_PATTERN_REPORT.md`](TYPE_PERMISSION_PATTERN_REPORT.md)
- [`COHORT_COUNT_CONTRACT.md`](COHORT_COUNT_CONTRACT.md)
