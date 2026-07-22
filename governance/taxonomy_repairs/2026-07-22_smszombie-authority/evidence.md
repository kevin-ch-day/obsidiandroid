# Smszombie authority repair

## Research question

Can the existing inactive `smszombie` family record be restored as current
Android family authority using its existing `sms-trojan` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 688 (`Smszombie`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `sms-trojan`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `smszombie` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=688`

## Independent evidence

- [Antiy: SMSZombie](https://www.antiy.net/p/android-smszombie/) documents device-admin persistence and interception/forwarding of banking-keyword SMS messages.

## Impact and limitations

The repair activates family 688 and adds source/review metadata only. It does not alter mappings.
