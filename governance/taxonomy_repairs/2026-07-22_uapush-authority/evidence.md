# UAPush authority repair

## Research question

Can the existing inactive `uapush` family record be restored as current
Android family authority with a researched `Spyware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 294 (`Uapush`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `Unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had five catalog
mappings. No active family slug or alias collision for `uapush` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=294`

## Independent evidence

- [ACM: A Data-driven Characterization of Modern Android Spyware](https://dl.acm.org/doi/10.1145/3382158)
  treats UaPush as a principal Android spyware family that steals IMEI,
  bookmarks, and call history (with some variants also sending premium SMS).
- [TimesLive / Nokia mobile threat reporting](https://www.timeslive.co.za/news/consumer-live/2016-09-05-rip-smstracker-and-uapush---be-alert-to-surging-mobile-device-infections/)
  listed Uapush among the top mobile infections in 2016 Nokia reporting.
- Supporting academic and analysis write-ups consistently describe Uapush as
  an adware-trojan / spyware hybrid dominated by personal-data exfiltration.

## Impact and limitations

The repair activates family 294, remaps primary type from Unknown (8) to
Spyware (2), and adds source/review metadata only. It does not alter mappings.
