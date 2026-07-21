# Permission protection / governance lane contract

Durable reporting contract for live-corpus type-permission analyses.
Classification is **offline-only** from completed-run
`diagnostics/permission_feature_audit.csv` fields. No Permission Intel, Core,
or Erebus queries are performed by the composers.

## Contract version

| Field | Value |
| --- | --- |
| `protection_lane_contract_version` | `1.0.0` |

## Canonical headline lanes

Every governed permission token maps to **exactly one** of:

| Lane | Meaning |
| --- | --- |
| `aosp_normal` | `pi_bucket_source=AOSP` and `dangerous_bucket=normal` |
| `aosp_dangerous` | `pi_bucket_source=AOSP` and `dangerous_bucket=dangerous` |
| `aosp_protection_unresolved` | `pi_bucket_source=AOSP` with any other/empty `dangerous_bucket` (including `unknown`) |
| `oem_or_google` | OEM or GOOGLE namespace / oem_vendor / google buckets |
| `app_defined` | App-defined namespace or `app_defined` bucket |
| `unknown_unresolved` | UNKNOWN source or unmatched tokens |

### Conceptual brief → offline lane

| Research brief concept | Offline lane |
| --- | --- |
| AOSP normal | `aosp_normal` |
| AOSP dangerous | `aosp_dangerous` |
| AOSP signature / privileged | `aosp_protection_unresolved` (**not confirmed**; structured signature/privileged flags absent offline) |
| OEM or Google platform | `oem_or_google` |
| App-defined | `app_defined` |
| Unknown / unresolved | `unknown_unresolved` |

## Classification precedence

1. `UNKNOWN` source → `unknown_unresolved`
2. `APP_DEFINED` source or `app_defined` bucket → `app_defined`
3. `OEM` / `GOOGLE` source or `oem_vendor` / `google` bucket → `oem_or_google`
4. `AOSP` + `normal` → `aosp_normal`
5. `AOSP` + `dangerous` → `aosp_dangerous`
6. `AOSP` + other → `aosp_protection_unresolved`
7. else → `unknown_unresolved`

Do **not** force multi-flag Android protection strings into a single invented
category when those fields are absent. Base protection level and protection
flags are recorded as missing in the field-audit table.

## Reconciliation

```text
total governed permission tokens
  = sum(lane token counts)

type×permission prevalence observation rows
  = sum(matrix observation rows by lane)
```

## Reportability statuses

| Status | Meaning |
| --- | --- |
| `descriptive_common` | Common / non-discriminative |
| `descriptive_type_enriched` | Mild enrichment; not headline |
| `family_balanced_supported` | Passes sample, family, concentration, effect, and FDR gates |
| `single_family_dominated` | Visible but not broad type behavior |
| `insufficient_family_support` | Too few independent families |
| `insufficient_sample_support` | Too few positive samples |
| `protection_level_unresolved` | Unresolved / unconfirmed protection lane |
| `app_defined_high_cardinality` | App-defined identity lane |
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

Implementation: `obsidiandroid.reporting.permission_governance_lanes`.
