# Permission protection / governance lane contract

Durable reporting contract for live-corpus type-permission analyses.
Classification is **offline-only** from completed-run
`diagnostics/permission_feature_audit.csv` fields. No Permission Intel, Core,
or Erebus queries are performed by the composers.

## Contract version

| Field | Value |
| --- | --- |
| `protection_lane_contract_version` | `2.0.0` (artifact-only) |
| Enriched companion | `2.1.0` via [`PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md`](PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md) |
| `governance_field_contract_version` | `1.0.0` |

## Canonical headline lanes

Every governed permission token maps to **exactly one** of:

| Lane | Meaning |
| --- | --- |
| `aosp_normal` | `pi_bucket_source=AOSP` and `dangerous_bucket=normal` |
| `aosp_dangerous` | `pi_bucket_source=AOSP` and `dangerous_bucket=dangerous` |
| `aosp_signature` | AOSP with structured `base_protection_level=signature` (no privileged flag) |
| `aosp_signature_privileged` | AOSP signature + privileged protection flag |
| `oem_platform` | OEM namespace / `oem_vendor` bucket |
| `google_platform` | GOOGLE namespace / `google` bucket |
| `app_defined` | App-defined namespace / `app_defined` bucket |
| `unknown_unresolved` | UNKNOWN source, unmatched tokens, or AOSP without confirmed normal/dangerous/signature fields |

### Preserved fact columns (not collapsed away)

| Column | Meaning |
| --- | --- |
| `base_protection_level` | Structured Android base level when present |
| `protection_flags` | Structured flags when present |
| `governance_namespace` | From `pi_bucket_source` |
| `headline_lane` | Exactly one canonical lane |

A permission with base `signature` and flag `privileged` retains both facts
even when its headline lane is `aosp_signature_privileged`.

## Classification precedence

1. `UNKNOWN` source → `unknown_unresolved`
2. `APP_DEFINED` source or `app_defined` bucket → `app_defined`
3. `OEM` source or `oem_vendor` bucket → `oem_platform`
4. `GOOGLE` source or `google` bucket → `google_platform`
5. AOSP + structured signature (+ privileged) → `aosp_signature` / `aosp_signature_privileged`
6. `AOSP` + `normal` → `aosp_normal`
7. `AOSP` + `dangerous` → `aosp_dangerous`
8. else → `unknown_unresolved`

Do **not** invent signature/privileged lanes from permission-name heuristics.

## Reconciliation

```text
total normalized permission tokens
  = sum(lane token counts)

type×permission observation positives
  = sum(observation rows across headline lanes)

permission-bearing samples
  = 9,457   # counted once per sample, not once per permission
```

## Reportability statuses

| Status | Meaning |
| --- | --- |
| `descriptive_common` | Common / non-discriminative |
| `descriptive_type_enriched` | Mild enrichment; not headline |
| `family_balanced_supported` | Passes sample, family, concentration, effect, and FDR gates |
| `dominant_family_sensitive` | Supported globally but weakens under leave-dominant checks |
| `single_family_dominated` | Visible but not broad type behavior |
| `insufficient_family_support` | Too few independent families |
| `insufficient_sample_support` | Too few positive samples |
| `protection_level_unresolved` | Unresolved / unconfirmed protection lane |
| `app_defined_high_cardinality` | App-defined identity lane |
| `identity_risk` | Near-unique / single-family app-defined token |
| `not_significant_after_fdr` | Raw association fails FDR |
| `effect_too_small` | Effect or family-balanced prevalence below floor |
| `exploratory_only` | Thin / high-concentration type; exploratory |

## Default headline thresholds

Documented here and emitted in every composer manifest:

| Threshold | Default |
| --- | --- |
| `min_sample_support` | 30 |
| `min_family_support` | 3 |
| `min_family_size` | 3 |
| `min_family_balanced_prevalence` | 0.05 |
| `min_effect_odds` | 1.5 |
| `dominance_threshold` | 0.85 |
| `fdr_alpha` | 0.05 |
| `app_defined_max_global_support_for_identity` | 5 |
| `app_defined_min_families_for_headline` | 3 |
| `app_defined_max_family_concentration` | 0.85 |
| `headline_strength_moderate_fb` | 0.10 |
| `headline_strength_strong_fb` | 0.20 |
| `leave_dominant_spearman_sensitive` | 0.85 |
| `leave_dominant_jsd_sensitive` | 0.10 |
| `leave_dominant_max_shift_pp_sensitive` | 10.0 |

### Headline strength tiers

After a pair reaches `family_balanced_supported`, assign:

| Strength | Rule |
| --- | --- |
| `strong` | FB prevalence >= 0.20 |
| `moderate` | FB prevalence >= 0.10 |
| `marginal` | FB prevalence >= 0.05 |
| `not_headline` | not `family_balanced_supported` |

## v1.1 → v2.0 migration

| v1.1 lane | v2.0 |
| --- | --- |
| `aosp_protection_unresolved` | `unknown_unresolved` (when structured signature fields absent) |
| `oem_or_google` | split into `oem_platform` and `google_platform` |

Implementation: `obsidiandroid.reporting.permission_governance_lanes`.
Protection package: `obsidiandroid.reporting.type_permission_protection`.
Field inventory: [`PERMISSION_GOVERNANCE_FIELD_CONTRACT.md`](PERMISSION_GOVERNANCE_FIELD_CONTRACT.md).
