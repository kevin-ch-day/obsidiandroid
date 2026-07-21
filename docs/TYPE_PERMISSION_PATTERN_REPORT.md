# Type permission pattern report (composer contract)

Read-only post-hoc composer for **live-corpus malware-type permission patterns**.
It does not query production databases, does not enable Core persistence, and does
not write to the legacy Erebus warehouse.

## Entrypoint

```bash
python scripts/diagnostics/generate_type_permission_pattern_report.py \
  --run-root output/runs/allcurrent_diagnostic \
  --run-id <run_id>
```

Implementation: `obsidiandroid.reporting.type_permission_pattern_report`.

## Schema versions

| Field | Value |
| --- | --- |
| `composer_version` | `1.1.0` |
| `report_schema_version` | `type_permission_pattern_report_v2` |
| `protection_lane_contract_version` | `1.0.0` (see [`PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](PERMISSION_GOVERNANCE_LANE_CONTRACT.md)) |

## Report status

| Status | Meaning |
| --- | --- |
| `PROVISIONAL` | Source run has `.RUNNING`, or terminal status is not complete |
| `FINAL_FROM_COMPLETED_RUN` | No `.RUNNING` and manifest `run_status=complete` |

Never treat provisional output as final manuscript evidence. Regenerate after the run finishes and compare `input_sha256` / `output_sha256`.

## Required inputs (run-scoped)

Under `<run_root>/bundles/permission_trends/tables/`:

- `permission_coverage_report_<run_id>.csv`
- `permission_prevalence_by_type_<run_id>.csv`
- `permission_type_enrichment_<run_id>.csv`
- `type_capability_bundle_prevalence_<run_id>.csv`
- `type_permission_similarity_<run_id>.csv`
- `family_support_distribution_<run_id>.csv`
- `permission_prevalence_by_family_<run_id>.csv`
- `dangerous_distribution_by_type_<run_id>.csv`

Plus:

- `<run_root>/diagnostics/analysis_snapshot_<run_id>.csv` (**required** for complete type accounting)
- `<run_root>/diagnostics/permission_feature_audit.csv` (**required** for protection/governance lanes)

## Protection / governance lanes

Type reports emit lane-stratified tables:

- `protection_lane_token_inventory_*.csv`
- `type_lane_coverage_matrix_*.csv`
- `lane_stratified_type_permissions_*.csv`
- `lane_leaders_*_*.csv` (normal / dangerous / unresolved / OEM-Google / app-defined / unknown)

See [`PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](PERMISSION_GOVERNANCE_LANE_CONTRACT.md) for
precedence, reconciliation, reportability statuses, and default thresholds.

## Derived outputs (not for Git)

Written under `<run_root>/diagnostics/type_permission_pattern_report/`:

- `type_inventory_*.csv` — every `type_slug`, samples, families, inclusion/suppression reason
- `type_census_*.csv` — main table view
- `overall_permission_prevalence_*.csv`
- `permission_role_annotations_*.csv` — high-prevalence / enriched role labels
- `family_balanced_type_prevalence_*.csv`
- `type_lift_leaders_*.csv`
- `banker_dropper_comparison_*.csv` — sample-weighted + family-balanced + family distribution
- `type_permission_pattern_report_*.md`
- `type_permission_pattern_report_manifest_*.json` + `.sha256`

## Type accounting contract

```text
sum(type_inventory.sample_count) == prepared_sample_count
```

Main-comparison inclusion requires candidate type membership plus sample/family
support gates. Suppressed rows keep an explicit `suppression_or_inclusion_reason`
(`unknown_or_unresolved_type`, `insufficient_sample_support`,
`insufficient_family_support`, `single_family_dominated`, …).

Blank-family samples count toward type totals but are absent from
`family_support_distribution` (mapped-family tables only).

## Manifest provenance

The manifest records:

- run id / report status / source run status
- repository commit
- composer + schema versions
- prepared and permission-evidence sample counts
- complete type count + reconciliation block
- SHA-256 for every input table and derived output

## Phase 2: pairwise co-occurrence

Entrypoint:

```bash
python scripts/diagnostics/generate_type_permission_pairwise_report.py \
  --run-root output/runs/allcurrent_diagnostic \
  --run-id <run_id>
```

Implementation: `obsidiandroid.reporting.type_permission_pairwise`.

| Field | Value |
| --- | --- |
| `composer_version` | `1.2.0` |
| `report_schema_version` | `type_permission_pairwise_v3` |
| `protection_lane_contract_version` | `1.1.0` |

Inputs (no database access):

- `diagnostics/aligned_features_<run_id>.csv.gz`
- `diagnostics/aligned_labels_<run_id>.csv`
- `diagnostics/permission_feature_audit.csv`

Headline vocabulary defaults to governed **AOSP / OEM / GOOGLE** tokens with configurable
`min_global_support`. App-defined tokens are optional (`--include-app-defined-lane`).
Unknown tokens are inventoried but excluded from headline claims.

Each pair row includes `permission_a_lane`, `permission_b_lane`, `lane_pair_class`
(`within_lane` / `cross_lane`), and `lane_pair_ordered`.

Pair measures include sample-weighted and family-balanced prevalence, supporting-family
count, largest-family contribution, Jaccard, independence lift, type-vs-rest odds ratio,
Wilson CI, Fisher p-values, and BH-FDR q-values.

Reportability statuses are explicit (`family_balanced_supported`,
`single_family_dominated`, `insufficient_*`, `not_significant_after_fdr`,
`effect_too_small`, `descriptive_*`, `exploratory_only`, `protection_level_unresolved`,
`app_defined_high_cardinality`). Three-way mining is intentionally disabled.

Interpretation entrypoint:

```bash
python scripts/diagnostics/generate_type_permission_interpretation.py \
  --run-root output/runs/allcurrent_diagnostic \
  --run-id <run_id>
```

Main-type differential (high-ROI):

```bash
python scripts/diagnostics/generate_type_permission_main_comparison.py \
  --run-root output/runs/allcurrent_diagnostic \
  --run-id <run_id>
```

Headline pairs are tiered `strong` / `moderate` / `marginal` by family-balanced
prevalence (see governance lane contract). Prefer strong/moderate for claims.

Dominant-family robustness (leave-largest-family):

```bash
python scripts/diagnostics/generate_dominant_family_robustness.py \
  --run-root output/runs/allcurrent_diagnostic \
  --run-id <run_id>
```

Use this before treating banker/RAT dangerous discriminators as broad type behavior,
especially when ClayRat or Godfather dominate sample mass.