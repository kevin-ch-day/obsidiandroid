# Robust type-contrast contract

Offline follow-on to
[`ENRICHED_PACKAGE_FAMILY_SENSITIVITY_CONTRACT.md`](ENRICHED_PACKAGE_FAMILY_SENSITIVITY_CONTRACT.md).

Answers whether permissions that **survive joint prevalence sensitivity** also
**discriminate malware types** under the same package / leave-family axes.

## Contract versions

| Field | Value |
| --- | --- |
| `robust_type_contrast_contract_version` | `1.0.0` |
| `composer_version` | `1.0.0` |
| Inputs | completed run + frozen enrichment + joint sensitivity package |

## Research questions

1. Among joint-surviving RAT headlines, which still separate RAT from banker / rest under package-within-family and leave-largest-family weighting?
2. Which additional lane-labeled permissions are robust discriminators even if they were prevalence-fragile?
3. When banker type identity is conflicted, does Godfather-scoped contrast preserve the same sign?

## Methods

For each candidate permission and contrast pair (`rat_vs_banker`, `rat_vs_rest`,
`banker_vs_rest`, `clayrat_vs_godfather`):

- prevalence under `sample_weighted`, `package_within_family_balanced`, and
  leave-largest-family package-within-family (type side);
- absolute delta (percentage points) and sign agreement across scenarios;
- classify as `robust_discriminator`, `contrast_fragile`, `shared_background`,
  `identity_gated`, or `exploratory_only`.

Lineage balancing remains `lineage_balance_unavailable`.

## Boundaries

- No pipeline, DB, Core, Erebus, or Permission Intel queries.
- Do not overwrite prior research packages.
- Package identity ≠ malware lineage.
- Devixor is governed banker, not RAT.

## Outputs

`diagnostics/robust_type_contrast/`
