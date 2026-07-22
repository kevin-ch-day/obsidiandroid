# Xynyin authority repair

## Research question

Can the existing inactive `xynyin` family record be restored as current
Android family authority with a researched `Adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 744 (`Xynyin`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `Unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `xynyin` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=744`

## Independent evidence

- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists Xynyin among Android adware families.

## Impact and limitations

The repair activates family 744, remaps primary type from unknown (8) to adware (3), and adds source/review metadata only. It does not alter mappings.
