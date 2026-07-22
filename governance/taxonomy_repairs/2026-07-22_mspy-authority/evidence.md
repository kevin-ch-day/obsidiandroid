# Mspy authority repair

## Research question

Can the existing inactive `mspy` family record be restored as current
Android family authority with a researched `stalkerware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 488 (`Mspy`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `spyware`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `mspy` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=488`

## Independent evidence

- [Kaspersky: Beware of stalkerware](https://securelist.com/beware-of-stalkerware/90264/) catalogs mSpy as commercial consumer stalkerware marketed for covert device monitoring.

## Impact and limitations

The repair activates family 488 , remaps primary type from spyware (2) to stalkerware (17), adds source/review metadata only. It does not alter mappings.
