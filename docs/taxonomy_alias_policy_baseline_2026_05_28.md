# Taxonomy Alias Policy Baseline (2026-05-28)

This baseline captures the active alias-classification policy enforced by
`android_malware_family_alias` triggers and recent curation decisions.

## Alias-Type Classification Contract

| alias_type | trust_tier | review_status | intent |
|---|---|---|---|
| `canonical` | `curated_alias` | `accepted` | canonical family token |
| `public_report_name` | `curated_alias` | `accepted` | source-backed public family label |
| `vendor_label` | `curated_alias` | `accepted` | vendor family label approved for mapping |
| `vendor_alias` | `curated_alias` | `accepted` | vendor shorthand alias approved for mapping |
| `lineage_name` | `contextual_lineage` | `context_only` | lineage context, not auto-canonical |
| `research_alias` | `contextual_lineage` | `context_only` | research-context naming bridge |
| `variant_label` | `contextual_variant` | `context_only` | variant context token |
| `variant_token` | `contextual_variant` | `context_only` | version/variant token |
| `misspelling` | `contextual_variant` | `context_only` | normalized spelling bridge |
| `catalog_label` | `contextual_variant` | `context_only` | catalog-only contextual token |
| `vt_family_alias` | `contextual_variant` | `context_only` | VT-only contextual token |
| `raw_alias` | `raw_observed_alias` | `matching_only` | ungoverned observed token |

## Canonical Family Rule

- Canonical family identity is stored in `android_malware_family.family_slug`.
- Version strings should remain aliases and/or variant metadata unless there is an explicit governance decision to split a family.

## Hook Family Decision (Applied)

- Canonical family: `hook`
- Accepted aliases: `hookv3`, `hookbot`, `hook v3`, `hook3`
- Queue family text normalized from `Hookv3` to `Hook`.

## Operational Guardrail

- Run `python scripts/diagnostics/report_alias_policy_drift.py` after alias policy or curation changes.
- Target state is `Drift rows: 0`.

