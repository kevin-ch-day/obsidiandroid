# Fadeb authority repair

## Research question

Can the existing inactive `fadeb` family record be restored as current
Android family authority using its existing `adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 383 (`Fadeb`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `adware`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `fadeb` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=383`

## Independent evidence

- [Kaspersky Taking Root](https://securelist.ru/taking-root/26769/) describes Trojan.AndroidOS.Fadeb as responsible for silent download/install of apps, often paired with rooting droppers.

## Impact and limitations

The repair activates family 383 and adds source/review metadata only. It does not alter mappings.
