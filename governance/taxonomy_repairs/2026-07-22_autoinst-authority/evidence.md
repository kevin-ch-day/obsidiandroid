# Autoinst authority repair

## Research question

Can the existing inactive `autoinst` family record be restored as current
Android family authority with a researched `riskware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 339 (`Autoinst`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `autoinst` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=339`

## Independent evidence

- [AWAKE/Malwarebytes Autoins](https://awakewiki.org/malware/families/autoins/) documents a preinstalled firmware auto-installer (`Android/PUP.Riskware.Autoins.Fota`) that silently installs apps and can deliver further unwanted payloads.

## Impact and limitations

The repair activates family 339 , remaps primary type from unknown (8) to riskware (7), adds source/review metadata only. It does not alter mappings.
