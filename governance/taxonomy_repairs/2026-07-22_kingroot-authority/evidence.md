# Kingroot authority repair

## Research question

Can the existing inactive `kingroot` family record be restored as current
Android family authority with a researched `riskware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 452 (`Kingroot`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `kingroot` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=452`

## Independent evidence

- [Malwarebytes: Android/PUP.Rooter.Kingroot](https://www.malwarebytes.com/blog/detections/android-pup-rooter-kingroot) classifies Kingroot as a rooting PUP that can be abused for privilege escalation.

## Impact and limitations

The repair activates family 452 , remaps primary type from unknown (8) to riskware (7), adds source/review metadata only. It does not alter mappings.
