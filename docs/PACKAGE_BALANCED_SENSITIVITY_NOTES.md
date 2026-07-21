# Package and family concentration sensitivity notes

Companion notes for dominant-package and hierarchical weighting sensitivity
under [`PACKAGE_BALANCED_PERMISSION_CONTRACT.md`](PACKAGE_BALANCED_PERMISSION_CONTRACT.md).

## Sensitivity scenarios

- `full_sample_weighted`
- `exclude_largest_package`
- `exclude_top3_packages`
- `package_balanced`
- `package_within_family_balanced`

Skipped when concentration state is `insufficient_package_identity`,
`package_identity_conflicted`, or `single_package_dominated`.

## Robustness classes

- `baseline`
- `stable_across_weighting`
- `sample_duplication_sensitive`
- `package_concentration_driven`
- plus explicit skip states mirrored from concentration contract

## Interpretation reminder

Package identity is not malware lineage. Source-batch concentration is not
lineage. Static permissions remain descriptive manifest evidence.
