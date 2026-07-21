# Enriched package–family joint sensitivity contract

Offline synthesis pass combining:

1. frozen Permission Intel **authority-enriched** protection lanes;
2. **package / family / package-within-family** weighting;
3. **leave-largest-family** sensitivity.

Answers whether ClayRat/RAT and Godfather/banker headline findings survive when
both enrichment and package balancing are applied.

## Contract versions

| Field | Value |
| --- | --- |
| `joint_sensitivity_contract_version` | `1.0.0` |
| `composer_version` | `1.0.0` |
| Lane input | enrichment contract 1.0.0 / lanes 2.1.0 |
| Package input | package-balanced contract 1.0.0 |

## Boundaries

- No pipeline, DB, Core, Erebus, or Permission Intel queries.
- Do not overwrite prior research packages.
- Package identity ≠ malware lineage (`lineage_balance_unavailable`).
- Banker type rows gated when `package_identity_conflicted`.
- Devixor is governed **banker**, not RAT.

## Focus scope

Types: `rat`, `banker` (plus exploratory summary for adware/spyware if cheap).

Scenarios per type × lane profile:

- `full_sample_weighted`
- `package_balanced`
- `family_balanced`
- `package_within_family_balanced`
- `leave_largest_family_sample_weighted`
- `leave_largest_family_package_within_family`

## Survival vocabulary

| Status | Meaning |
| --- | --- |
| `survives_joint_sensitivity` | Stable under package-within-family and leave-largest family |
| `package_balance_fragile` | Collapses under package / hierarchical balancing |
| `dominant_family_fragile` | Collapses when largest family removed |
| `jointly_fragile` | Fragile on both axes |
| `identity_gated` | Suppressed by package-identity conflict |
| `exploratory_only` | Insufficient support |

## Outputs

`diagnostics/enriched_package_family_sensitivity/`
