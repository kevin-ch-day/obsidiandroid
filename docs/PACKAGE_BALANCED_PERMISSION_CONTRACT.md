# Package-balanced permission evidence contract

Offline research contract for **package-balanced** and hierarchical permission
sensitivity on a **frozen completed run**. Uses run-local artifacts and the
frozen Permission Intel authority enrichment only.

## Contract versions

| Field | Value |
| --- | --- |
| `package_key_contract_version` | `1.0.0` |
| `weighting_contract_version` | `1.0.0` |
| `package_balanced_composer_version` | `1.0.0` |
| Pairwise threshold inheritance | existing pairwise protection contract |
| Authority enrichment input | frozen `permission_authority_enrichment` v1.0.0 / lanes 2.1.0 |

## Hard boundaries

- No pipeline execution, no DB / Core / Erebus / Permission Intel queries.
- Do not overwrite enrichment, protection-enriched, or family-context packages.
- Do not expose raw package names or sample hashes in headline Markdown.
- Do **not** call package identity “malware lineage” unless an explicit governed
  lineage field exists in run artifacts (it does not on this run).

## Package key

Preferred key: **normalized `package_name`** (trim + lowercase).

| State | Rule |
| --- | --- |
| Known package | non-empty normalized key |
| Missing package | empty/null package; **not** merged into one package |
| Synthetic accounting key | `__missing_package__:{sample_id}` for row accounting only |
| Diversity claims | known packages only; missing excluded |

Also record: original package value SHA-256, sample/SHA counts, families,
types, and source batches represented (counts only in headlines).

## Weighting schemes

| Scheme | Definition |
| --- | --- |
| `sample_weighted` | Equal weight per sample |
| `package_balanced` | Equal weight per **known** package; within-package sample prevalence first |
| `family_balanced` | Equal weight per governed family; within-family sample prevalence first |
| `package_within_family_balanced` | Within family: package-balanced prevalence, then equal weight across families |
| `lineage_balanced` | Only if explicit lineage field exists; else `lineage_balance_unavailable` |

Missing-package samples are never merged for package-balanced claims.

## Concentration interpretive states

| State | Default gate |
| --- | --- |
| `broad_package_diversity` | known packages ≥ 50 **and** package/sample ratio ≥ 0.70 **and** largest-package share < 0.10 |
| `moderate_package_concentration` | largest share < 0.50 **and** HHI < 0.25 |
| `high_package_concentration` | largest share ≥ 0.50 **or** HHI ≥ 0.25 |
| `single_package_dominated` | known packages ≤ 1 **or** largest share ≥ 0.85 |
| `insufficient_package_identity` | known-package sample share < 0.50 **or** known packages < 3 (when samples ≥ 30) |
| `package_identity_conflicted` | cross-family or cross-type package collisions present |

Thresholds are emitted in every package manifest.

## Collision classes

`same_family_multi_sample`, `cross_family_collision`, `cross_type_collision`,
`authority_conflict`, `unknown_identity`, `likely_repackaging`,
`unable_to_interpret`.

Cross-family / cross-type collisions are **not** auto-consolidated.

## Reportability statuses

`stable_across_weighting`, `package_balanced_supported`,
`family_balanced_supported`, `package_within_family_supported`,
`sample_duplication_sensitive`, `package_concentration_driven`,
`family_concentration_driven`, `package_and_family_sensitive`,
`single_package_dominated`, `insufficient_package_identity`,
`package_identity_conflicted`, `lineage_balance_unavailable`,
`exploratory_only`.

## Outputs

Under `diagnostics/package_balanced_permission_analysis/` only.
