# Mobtes authority repair

## Research question

Can the existing inactive `mobtes` family record be restored as current
Android family authority with a researched `Spyware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 297 (`Mobtes`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `Unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had four catalog
mappings. No active family slug or alias collision for `mobtes` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=297`

## Independent evidence

- [Kaspersky: Trojan.AndroidOS.Mobtes](https://threats.kaspersky.com/en/threat/Trojan.AndroidOS.Mobtes/)
  documents an AndroidOS Trojan family whose published class description
  emphasizes electronic surveillance (keystroke/screenshot/app monitoring)
  and exfiltration of collected information over HTTP/FTP/email.

## Impact and limitations

The repair activates family 297, remaps primary type from Unknown (8) to
Spyware (2), and adds source/review metadata only. It does not alter mappings.
Kaspersky names the detection Trojan; local typing prefers the documented
spyware behavior over a coarse Trojan bucket.
