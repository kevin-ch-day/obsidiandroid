# Adend authority repair

## Research question

Can the existing inactive `adend` family record be restored as current
Android family authority using its existing `adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 318 (`Adend`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `adware`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `adend` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=318`

## Independent evidence

- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists Adend among Android adware families (301 samples in the published capture).

## Impact and limitations

The repair activates family 318 and adds source/review metadata only. It does not alter mappings.
