# LokiBot Lineage Research Note

## Summary

The local authority now has the core LokiBot branch partly encoded:

- `LokiBot`
- `Xerxes`
- `BlackRock`
- `MysteryBot`

The main remaining structural gap was that `MysteryBot` existed as a governed family but had no explicit lineage edge to `LokiBot`.

## Source-backed findings

- ThreatFabric's LokiBot Android report identifies `LokiBot` as an early Android banking family and provides the Android sample set used for the new queue tranche.
- ThreatFabric's MysteryBot report says `MysteryBot` and `LokiBot` were observed on the same C2 server.
- Secondary reporting on ThreatFabric's MysteryBot analysis says ThreatFabric assessed `MysteryBot` as based on the LokiBot bot code, while still treating it as a distinct family rather than a simple rename.

That supports the following taxonomy policy:

- keep `LokiBot` canonical
- keep `MysteryBot` canonical
- encode `MysteryBot -> LokiBot` as lineage
- do not alias `MysteryBot` into `LokiBot`

## Local data gaps fixed in this pass

- `android_malware_family_lineage` was missing `MysteryBot -> LokiBot`
- `malware_sample_catalog` still had stale mixed-case labels:
  - `Lokibot`
  - `Mysterybot`
  - `mysteryBot`

Those rows should use the governed canonical labels:

- `LokiBot`
- `MysteryBot`

## Remaining upstream context

- `BlackRock -> Xerxes` is already encoded.
- `Xerxes -> LokiBot` is already encoded.
- `Parasite` is still not a governed family node in the local DB, so that step remains research context only until it is explicitly added.

## Sources

- ThreatFabric, *LokiBot - The first hybrid Android malware*:
  https://www.threatfabric.com/blogs/lokibot_the_first_hybrid_android_malware
- ThreatFabric, *MysteryBot; a new Android banking trojan ready for Android 7 and 8*:
  https://www.threatfabric.com/blogs/mysterybot__a_new_android_banking_trojan_ready_for_android_7_and_8
- BleepingComputer summary of ThreatFabric's MysteryBot analysis:
  https://www.bleepingcomputer.com/news/security/new-mysterybot-android-malware-packs-a-banking-trojan-keylogger-and-ransomware/
