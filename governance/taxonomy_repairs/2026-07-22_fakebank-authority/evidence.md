# Fakebank authority repair

## Research question

Can the existing inactive `fakebank` family record be restored as current
Android family authority using its existing `banker` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 385 (`Fakebank`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `banker`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `fakebank` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=385`

## Independent evidence

- [GBHackers summarizing Trend Micro FakeBank](https://gbhackers.com/fakebank-malware-layered-obfuscation-technique/) documents FakeBank replacing the default SMS app to intercept banking OTPs and financial notifications.

## Impact and limitations

The repair activates family 385 and adds source/review metadata only. It does not alter mappings.
