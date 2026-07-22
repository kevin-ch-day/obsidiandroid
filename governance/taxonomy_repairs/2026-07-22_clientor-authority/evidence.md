# Clientor authority repair

## Research question

Can the existing inactive `clientor` family record be restored as current
Android family authority with a researched `Backdoor` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 279 (`Clientor`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `Unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had eight catalog
mappings. No active family slug or alias collision for `clientor` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=279`

## Independent evidence

- [Avira: Clientor Android malware makes a proxy out of your phone](https://www.avira.com/en/blog/clientor-android-malware-makes-proxy)
  documents a Play Store voice-messaging lure that establishes an SSH tunnel
  and turns the device into an attacker-controlled proxy (detected as
  Android/Clientor.HIR.Gen).
- [Malpedia: apk.clientor](https://malpedia.caad.fkie.fraunhofer.de/details/apk.clientor)
  catalogs Clientor as an Android malware family with the Avira/Štefanko
  proxy-malware references.

## Impact and limitations

The repair activates family 279, remaps primary type from Unknown (8) to
Backdoor (6), and adds source/review metadata only. It does not alter mappings.
