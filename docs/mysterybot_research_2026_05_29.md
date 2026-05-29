# MysteryBot Research Notes

Date: 2026-05-29

## Summary

`MysteryBot` should remain a distinct canonical Android banker family.

It is best modeled as a descendant of `LokiBot`, not as a synonym of `LokiBot`
or a generic `BankBot` relabel.

## Source-backed findings

- ThreatFabric describes `MysteryBot` as a new Android banking trojan targeting
  Android 7 and 8 with novel overlay, keylogging, and ransomware
  functionality:
  https://www.threatfabric.com/blogs/mysterybot__a_new_android_banking_trojan_ready_for_android_7_and_8
- SecurityWeek's coverage of the ThreatFabric report says the malware used the
  same C2 server as `LokiBot`, indicating actor/lineage linkage rather than a
  simple rename:
  https://www.securityweek.com/new-lokibot-linked-android-trojan-emerges/
- Avira summarizes the same strain as a combined banking trojan, keylogger, and
  ransomware family and notes it was considered based on `LokiBot` but
  significantly improved:
  https://www.avira.com/en/blog/mysterybot-the-android-malware-thats-keylogger-ransomware-and-trojan/amp
- Zimperium's glossary keeps `MysteryBot` as its own Android malware family and
  emphasizes the banker + keylogger + ransomware combination:
  https://zimperium.com/glossary/mysterybot
- ThreatFabric's later `BlackRock` lineage write-up places `MysteryBot` in the
  `LokiBot` descent line and identifies `Parasite` as the direct successor of
  `MysteryBot`:
  https://www.threatfabric.com/blogs/blackrock_the_trojan_that_wanted_to_get_them_all

## Taxonomy implications

- Keep `MysteryBot` as its own canonical family.
- Keep the structural lineage edge `MysteryBot -> LokiBot`.
- Do not alias `MysteryBot` into `LokiBot`.
- Do not collapse `MysteryBot` into generic `BankBot`-style token handling.
- Treat `Parasite` as the likely next upstream/downstream lineage research gap.

## Local data check

Live catalog state on 2026-05-29:

- governed family exists: `family_id=114`, `family_slug='mysterybot'`
- live catalog rows: `3`
- all `3` are typed `Trojan / Banker`
- all `3` have `family_label = MysteryBot`
- all `3` have `sample_label = MysteryBot`
- only one row has residual VT text drift:
  - sample `911` has `vt_suggested_label = trojan.andr/bankbot`

Interpretation:

- the local `MysteryBot` slice is already clean at the family-label level
- the remaining `bankbot` VT text on one row is generic vendor drift, not
  evidence that `MysteryBot` should be merged into `BankBot`
