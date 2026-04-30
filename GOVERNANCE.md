# ObsidianDroid Governance Specification v1

This document defines mandatory governance behavior for ObsidianDroid runtime, diagnostics, and reproducibility.

## Scope
- Research-neutral Android security framework behavior.
- Deterministic lifecycle accounting for AV engines.
- Profile-driven execution using version-controlled YAML files.

## Required Policies
- No implicit cohort profile; profile must be supplied explicitly.
- Quality gates default to continue with exclusion and diagnostics.
- Fail-closed on structural integrity violations:
  - `included_engines == 0`
  - missing required supervised label columns
  - unreconciled lifecycle counts
  - corrupt feature/label matrix shape mismatch
  - duplicate canonical engine slugs
  - run manifest write failure

## Profile Contract
Profiles are YAML files under `profiles/`.

Required keys:
- `profile_id`
- `type_slug_filter`
- `cohort_gates`
- `model_list`

Supported keys:
- `description`
- `parser_overrides`
- `feature_flags`
- `threshold_overrides`
- `dataset_filters`

## Engine Canonicalization
Rules:
1. lowercase
2. trim whitespace
3. replace hyphen/space/underscore with single underscore
4. remove punctuation except underscore
5. collapse repeated underscores
6. remove trailing numeric version token

Alias source: `engine_aliases.yaml`.

## Lifecycle Stages
Per engine lifecycle flags:
- `observed_flag`
- `canonicalized_flag`
- `scored_flag`
- `included_in_model_flag`

Exclusion stages:
- `excluded_precanonical`
- `excluded_prescore`
- `excluded_postscore`

Reconciliation equations:
- `observed = canonicalized + excluded_precanonical`
- `canonicalized = scored + excluded_prescore`
- `scored = included + excluded_postscore`

## Required Artifacts
- `output/diagnostics/engine_lifecycle.latest.csv`
- `output/diagnostics/run_manifest.latest.json`
- workbook sheet: `__manifest__`

## Manifest Schema
`manifest_schema_version` is required and follows semantic versioning.
Current schema version: `1.0.0`.
