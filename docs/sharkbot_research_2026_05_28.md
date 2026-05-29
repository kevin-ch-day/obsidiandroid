# SharkBot research pass — 2026-05-28

## Source-backed conclusions

- `SharkBot` should stay a distinct canonical Android banker family.
- It should **not** be merged into `Octo`, `Coper`, `TeaBot`, or `FluBot`.
- The strongest differentiator is not just banking behavior, but the family-specific
  development and distribution history documented by primary sources.

## Primary sources

- Cleafy introduced `SharkBot` as a newly discovered Android banking trojan in late
  October 2021 and explicitly states that the team found no references tying it to
  a known family at discovery time. The family name comes from strings embedded in
  the binaries. Cleafy also documents ATS, overlays, SMS interception, accessibility
  abuse, DGA, and anti-analysis behavior.  
  Source: <https://www.cleafy.com/cleafy-labs/sharkbot-a-new-generation-of-android-trojan-is-targeting-banks-in-europe>

- NCC Group / Fox-IT documented Google Play droppers distributing SharkBot in 2022.
  Those reports reinforce SharkBot as a distinct banker family and discuss the fake
  antivirus / cleaner delivery chain rather than lineage to Octo/Coper.  
  Source: <https://www.nccgroup.com/research-blog/sharkbot-a-new-generation-android-banking-trojan-being-distributed-on-google-play-store/>  
  Source: <https://www.nccgroup.com/dk/research-blog/sharkbot-is-back-in-google-play/>

- ThreatFabric documents `Octo` as the rebranding / descendant line of
  `ExobotCompact`, and notes that some AV vendors dubbed this family `Coper`.
  That supports an `Octo`/`Coper` lineage/renaming discussion, but it does not
  support merging `SharkBot` into that branch.  
  Source: <https://www.threatfabric.com/blogs/octo-new-odf-banking-trojan>

## Local data observations

- Current Android rows tied to the SharkBot slice:
  - `family_label = SharkBot`: 13
  - `family_label = Octo` with `sample_label = SharkBot`: 1
- `vt_family_token = sharkbot` appears on 9 rows.
- The one `Octo` row with raw `sample_label = SharkBot` also has:
  - `vt_family_token = coper`
  - `vt_suggested_label = trojan.coper/andr`
  - accepted resolved family = `octo`

## Hash coverage from added 2026-05-28 source bundle

User-supplied SharkBot hashes were checked against the local catalog and ingest queue.
Hash type was verified first by token length:

- `32` hex chars => `md5`
- `40` hex chars => `sha1`
- `64` hex chars => `sha256`

Current local catalog dedupe is only authoritative for `sha256`, because
`malware_sample_catalog` currently stores `sha256` but not parallel `md5` / `sha1`
columns. Queue dedupe still applies to all supported hash types via
`artifact_hash_norm`.

- Already present in `malware_sample_catalog`:
  - `187b9f5de09d82d2afbad9e139600617685095c26c4304aaf67a440338e0a9b6`
    - local sample `711`
    - `family_label = SharkBot`
    - `android_package_name = com.pagnotto28.sellsourcecode.alpha`
  - `20e8688726e843e9119b33be88ef642cb646f1163dce4109b8b8a2c792b5f9fc`
    - local sample `768`
    - `family_label = SharkBot`
    - `android_package_name = com.abbondioendrizzi.tools.supercleaner`

- Missing from both catalog and ingest queue, staged for ingestion:
  - `a56dacc093823dc1d266d68ddfba04b2265e613dcc4b69f350873b485b9e1f1c`
  - `9701bef2231ecd20d52f8fd2defa4374bffc35a721e4be4519bda8f5f353e27a`

- Excluded as malformed / incomplete:
  - `e5b96e80935ca83bbe895f6239eabca1337dc575a066bb6ae2b56faacd29dd`
    - only 62 hex characters, so it should not be ingested until re-verified from a primary source

## Practical taxonomy policy

- Keep `SharkBot` distinct.
- Keep `Octo` and `Coper` distinct from `SharkBot`.
- Treat the singleton `Octo` row carrying raw `sample_label = SharkBot` as
  analyst-review debt, not a synonym signal.
- Safe hygiene repairs are limited to casing / exact raw-label cleanup on already
  governed `SharkBot` rows.
