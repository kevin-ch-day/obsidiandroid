# Package-balance attribution contract

Offline follow-on to [`PACKAGE_BALANCED_PERMISSION_CONTRACT.md`](PACKAGE_BALANCED_PERMISSION_CONTRACT.md).

Answers open questions from the package-balanced pass using **frozen run
artifacts only** (no DB, Core, taxonomy, or pipeline).

## Contract versions

| Field | Value |
| --- | --- |
| `package_balance_attribution_contract_version` | `1.0.0` |
| `composer_version` | `1.0.0` |
| Inputs | completed run + frozen package-balanced + enrichment packages |

## Research questions

1. Which RAT families drive the type-level package-balanced / package-within-family shifts?
2. What do the banker cross-family package collisions look like (hashed keys only)?
3. How do source batches couple to package concentration for major families?

## Methods

### RAT family leave-out attribution

Compare the RAT type permission profile under:

- full sample-weighted
- package-balanced
- package-within-family balanced
- leave ClayRat
- leave ArsinkRAT
- leave single-package-dominated RAT families
- leave top package-concentrated RAT families (by largest-package share / HHI)

Report Spearman, JSD, and max absolute prevalence shift (pp).

### Banker collision deep dive

From frozen `package_identity_collision_audit.csv` plus membership:

- collision class counts involving banker types/families
- multi-family package groups (hashed keys only)
- sample and batch support
- whether collisions are same-type multi-family or cross-type

Do **not** auto-merge or repair labels.

### Source-batch × package coupling

For major families/types:

- largest batch share
- package count within largest batch
- whether one batch dominates packages as well as samples

## Outputs

`diagnostics/package_balance_attribution/` only. Do not overwrite prior packages.

## Boundaries

No pipeline, no database queries, no Core, no taxonomy mutation, no lineage
inferences from package names.
