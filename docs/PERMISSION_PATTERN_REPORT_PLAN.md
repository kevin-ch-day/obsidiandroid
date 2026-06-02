# Permission Pattern Report Plan

This plan promotes permission-pattern analysis from a side bundle into a first-class reporting lane alongside family and type benchmarking.

## Goals

- Preserve the current broad-corpus value proposition:
  - permission prevalence by `type_slug`
  - permission prevalence by family
  - distinguishing permissions by type and family
  - family-within-type similarity
  - rare or high-signal permissions
  - later ATT&CK-Mobile enrichment
- Keep permission-pattern reporting additive:
  - broad current-corpus diagnostics should include generic/coarse and unresolved residue
  - supervised family benchmark filtering must not remove rows from permission-pattern reports
- Make the outputs usable for operator review, research summaries, and later paper figures.

## Report Lanes

### 1. Broad Corpus Permission Lane

Primary audience: operator diagnostics and corpus characterization.

Scope:
- all prepared Android malware rows in the selected profile
- includes major, minor, generic/coarse, and unresolved buckets

Core outputs:
- permission prevalence by `type_slug`
- permission prevalence by `family_canonical`
- rare/high-signal permission inventory
- top capability-bundle prevalence by type and family
- ATT&CK-Mobile hypotheses with confidence labels

Key interpretation:
- this lane explains behavior patterns in the full current corpus
- it is not restricted to benchmark-trainable family rows

### 2. Benchmark Family Permission Lane

Primary audience: family benchmark interpretation.

Scope:
- rows that are both:
  - authority-eligible for family supervision
  - benchmark-eligible under the family support rule

Core outputs:
- permission prevalence by benchmark-eligible family
- distinguishing permissions among benchmark families
- family-within-type similarity for benchmark families
- grouped views:
  - major benchmark families
  - minor benchmark families
  - benchmark-excluded families kept out of the benchmark but visible in diagnostics

Key interpretation:
- this lane explains the behavior structure of the actual supervised family benchmark surface
- it should not hide which families were excluded by `n >= 3`

### 3. Type-Level Permission Lane

Primary audience: coarse-taxonomy and capability analysis.

Scope:
- type-target-eligible rows regardless of family benchmark status

Core outputs:
- permission prevalence by `type_slug`
- distinguishing permissions by type
- intra-type family similarity
- type-specific capability bundles
- type-level ATT&CK-Mobile hypotheses

Key interpretation:
- this lane remains useful even when family taxonomy is noisy or long-tailed

## Required Contract Fields

The permission-pattern report family should carry these row-scope distinctions explicitly:

- `authority_tier`
- `family_target_eligible`
- `benchmark_eligible`
- `benchmark_exclusion_reason`
- `type_target_eligible`
- `support_floor_mode`
- `benchmark_min_support`

This prevents permission outputs from drifting away from the family-tier and benchmark-eligibility contracts.

## Short-Term Implementation Steps

1. Add benchmark-eligibility metadata into permission-trends bundle metadata.
2. Add benchmark-vs-broad cohort counts to the permission one-pager.
3. Split permission prevalence tables into:
   - broad corpus
   - benchmark-eligible family surface
   - type-level surface
4. Add an explicit benchmark exclusion appendix:
   - families excluded due to support `<3`
   - sample counts affected
5. Promote the capability-bundle and ATT&CK-Mobile sections into the run one-pager and evaluation summaries.

## Medium-Term Additions

- family-within-type similarity heatmaps for benchmark-eligible families
- rare/high-signal permission watchlist with source-batch context
- ATT&CK-Mobile confidence calibration:
  - `direct`
  - `strong_inference`
  - `weak_inference`
- paper-ready permission figures for:
  - major-family benchmark
  - type-level benchmark

## Non-Goals

- do not use permission-pattern reporting to silently redefine family authority
- do not use benchmark support rules to remove rows from broad corpus-health reporting
- do not force generic/coarse or unresolved rows into family benchmark training just to simplify visuals
