# Adrd authority repair

## Research question

Can the existing inactive `adrd` family record be restored as current
Android family authority using its existing `adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 321 (`Adrd`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `adware`, with no aliases, no
normalization target, and no canonical-source metadata. It had 1 catalog
mapping(s). No active family slug or alias collision for `adrd` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=321`

## Independent evidence

- [Antiy: Android Trojan Adrd](https://www.antiy.net/p/android-trojan-adrd/) and contemporaneous F-Secure/Lookout reporting describe Adrd/HongTouTou as an Android Trojan-Clicker that performs background search/click fraud and secondary downloads.

## Impact and limitations

The repair activates family 321 and adds source/review metadata only. It does not alter mappings.
