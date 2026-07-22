# Loki authority repair

## Research question

Can the existing inactive `loki` family record be restored as current
Android family authority with a researched `adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 461 (`Loki`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `loki` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=461`

## Independent evidence

- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists Loki among Android adware families (46 samples).

## Impact and limitations

The repair activates family 461 , remaps primary type from unknown (8) to adware (3), adds source/review metadata only. It does not alter mappings.
