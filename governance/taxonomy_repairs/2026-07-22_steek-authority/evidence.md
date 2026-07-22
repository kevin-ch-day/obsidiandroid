# Steek authority repair

## Research question

Can the existing inactive `steek` family record be restored as current
Android family authority with a researched `trojan` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 313 (`Steek`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had 2 catalog
mapping(s). No active family slug or alias collision for `steek` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=313`

## Independent evidence

- [FortiGuard: Android/Steek.A!tr](https://fortiguard.fortinet.com/encyclopedia/virus/3458224) documents an Android Trojan that spoofs popular games and phishes personal details via redirect sites.

## Impact and limitations

The repair activates family 313 , remaps primary type from unknown (8) to trojan (1), adds source/review metadata only. It does not alter mappings.
