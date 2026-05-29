# Android Authority Curation Packet

Date: `2026-05-26`

Scope:
- Read-only review packet for `android_full_vt_no_authority_family_worklist`
- No DB writes performed in this pass
- Focus:
  - the `59` recent `raw_hash_reservoir_20260520` Android/APK rows with full VT evidence and `authority_bucket='missing_resolved_family'`
  - repeated informative tokens requested for authority review

Current live baseline after prior bounded repair tranches:
- Android/APK rows: `3465`
- `authority_family_typed`: `2991`
- `resolved_but_no_authority_family`: `188`
- `missing_resolved_family`: `59`
- `resolved_unknown`: `188`

Important note:
- Several requested tokens are no longer unresolved. They were already repaired earlier and are included here as precedent rows only:
  - `frogblight`, `pjobrat`, `caprarat`, `actionspy`, `finspy`, `exodus`, `hydra`, `mysterybot`, `callerspy`
- Several requested local labels were already normalized through alias work:
  - `bankerspanish` -> `basbanke`
  - `camscannernecron` -> `necro`

## 1. Recent 59-Row Tranche

Definition:
- `platform='android'`
- `file_extension='apk'`
- full VT summary row
- wide vendor verdict row
- `authority_bucket='missing_resolved_family'`
- `source_batch_label='raw_hash_reservoir_20260520'`

### Cluster Summary

| cluster | rows | sample_ids | signal hints | PI coverage | likely action | confidence | notes |
|---|---:|---|---|---:|---|---|---|
| `<blank package>` | 22 | `30933,30939,30941,30950,30959,30987,30988,30992,31012,31021,31024,31030,31044,31046,31083,31106,31115,31118,31131,31144,31150,31196` | one `jiagu` signal (`31196`), otherwise blank | `0.00` avg | review-only; split out signal-bearing rows | low | mostly no package, no family, no vendor-family naming |
| `com.ubnt.easyunifi` | 16 | `30962,30980,30993,30997,31009,31011,31013,31029,31039,31040,31080,31088,31093,31094,31101,31121` | no VT family token, no suggested label, no popular threat name | `8.31` avg | review-only; likely legitimate/repackaged package cluster | medium | package matches public UniFi app package; 1123 normalized vendor verdict rows are all `undetected/type-unsupported/timeout` with `0` nonblank verdict labels |
| `com.frontrow.vlog` | 4 | `30976,31112,31114,31124` | none | `27.00` avg | review-only | low | repeated package cluster but no family signal |
| `net.telewebion` | 2 | `30948,31003` | none | `27.00` avg | review-only | low | repeated package cluster but no family signal |
| `com.app.pacotesinkinstall` | 1 | `28928` | `vt_family_token=fklz`, suggested `trojan.fklz`, confidence `high/promote` | `6` | needs external research | medium | strongest recent one-off banker candidate in this tranche |
| `com.dakls` | 1 | `32513` | popular threat `boogr`, suggested `trojan.boogr`, confidence `strong/promote_candidate` | `15` | needs external research | medium | useful single-row banker clue |
| `NULL package / jiagu` | 1 | `31196` | `vt_family_token=jiagu`, suggested `trojan.jiagu/...`, confidence `high/promote` | `0` | do not promote to family | high | `jiagu` is a packing/protection signal, not family truth |
| `com.antivirus.protectsecure` | 1 | `32461` | no family token, confidence `high/promote` | `4` | review-only | low | high confidence score without stable family evidence |
| `com.tencent.mobileqqq` | 1 | `32351` | no family token, confidence `strong/promote_candidate` | `192` | review-only | low | heavy PI surface but no family clue |
| `de.resolution.yf_androie` | 1 | `32521` | no family token, confidence `strong/promote_candidate` | `21` | review-only | low | no family signal |

### `com.ubnt.easyunifi` review

Observed facts:
- `16` rows in the recent backlog
- all `authority_bucket='missing_resolved_family'`
- all package name `com.ubnt.easyunifi`
- no `vt_family_token`
- no `vt_suggested_label`
- no `popular_threat_name`
- vendor-verdict distribution across all 16 samples:
  - `undetected`: `971`
  - `type-unsupported`: `150`
  - `timeout`: `2`
  - nonblank normalized vendor labels: `0`

External context:
- Public Android package listings identify `com.ubnt.easyunifi` as the legitimate UniFi / Ubiquiti app package.
- Example sources:
  - `https://apkpure.com/unifi/com.ubnt.easyunifi`
  - `https://apkcombo.com/unifi/com.ubnt.easyunifi/`

Conclusion:
- Treat as a package-name cluster, not family evidence.
- Most likely categories:
  - legitimate app copies or benign/repackaged variants
  - low-context catalog/import noise
  - not enough evidence for family authority

Recommended action:
- keep review-only for now
- do not promote package name to family authority

## 2. Requested Candidate Tokens

### Open authority debt

| candidate token | samples | sample_ids | package names / clusters | source_batch_label | authority_bucket | gap reason | raw subtype | vt_family_token | vt_suggested_threat_label | top vendor labels (abridged) | PI coverage | existing family/alias | likely action | suggested canonical family | suggested type_slug | confidence | evidence notes |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `badpack` | 8 | `568,577,666,680,1619,1975,15067,15075` | `com.fjjbpqe...`, `com.gavv.tissm`, `com.haegdrb...`, `com.kazdahlus...`, `com.lsmrseigk...`, `com.native123456.app`, `com.yrxvryoag...`, `ggqhugd...` | `<blank>` | `resolved_but_no_authority_family` | `resolved_token_not_in_authority_taxonomy` | `Banker` | `badpack`, `fakecalls`, `triada`, blank | `trojan.badpack`, `trojan.badpack/bankbot`, `trojan.fakecalls/badpack`, `trojan.triada/click` | `Cynet: Malicious (7)`, `Google: Detected (6)`, `SymantecMobileInsight: AppRisk:Generisk (5)` | avg `15.63` | none | technique/packer/evasion token, do not promote | n/a | n/a | high | external evidence treats BadPack as tampered-APK / evasion technique, not stable family |
| `spybanker` | 4 | `14995,15081,15125,15159` | `com.devloadsystem.cntbnkmy`, `com.gfw.wzantwhscdfc`, `com.iuocnvpj.mxzsojlp`, `com.pzkq.anjzjemnyla` | `<blank>` | `resolved_but_no_authority_family` | `resolved_token_not_in_authority_taxonomy` | `Banker` | `spybanker` | `dropper.spybanker`, `trojan.spybanker` | `Microsoft: Trojan:AndroidOS/SpyBanker!MTB (4)`, `Avast-Mobile: APK:RepMalware [Trj] (4)` | avg `12.00` | none | generic/coarse token, do not promote | n/a | n/a | high | vendor/class-style banker token; not enough evidence of governed family distinct from class detection |
| `blackloan` | 3 | `257,307,374` | `com.loan.test1`, `com.sample.sample1` | `<blank>` | `resolved_but_no_authority_family` | `resolved_token_not_in_authority_taxonomy` | `<blank>` | blank | blank | `Avira: ANDROID/Banker.FOTK.Gen (3)`, `ESET-NOD32: Android/Spy.Banker.APJ (3)` | avg `16.00` | none | needs external research | maybe `BlackLoan` if corroborated | likely `banker` | medium | repeated local label but weak direct VT family support |
| `molerats` | 3 | `209,288,300` | `com.android.googlsevrcie.settings`, `google.googleplaystore.playstore.store`, `io.chato.mobile` | `<blank>` | `resolved_but_no_authority_family` | `resolved_token_not_in_authority_taxonomy` | `Spyware` | `molerats` | `trojan.molerats/spyagent` | `Antiy-AVL: Trojan[APT]/Android.Molerats (3)`, `CTX: apk.trojan.molerats (3)` | avg `20.33` | none | needs external research; likely campaign/group token | unclear | likely `spyware` if ever promoted | low | looks APT/campaign-like rather than mobile family-specific authority |
| `scarletmimic` | 3 | `553,559,565` | `com.pdf.google.vm`, `pw.nrt.photo.google` | `<blank>` | `resolved_but_no_authority_family` | `resolved_token_not_in_authority_taxonomy` | `Spyware` | `genericfca`, `handda` | `trojan.genericfca/andr`, `trojan.handda/andr` | `Antiy-AVL: Trojan[APT]/Android.Scarletmimic (3)` | avg `27.33` | none | needs external research; likely campaign/group token | unclear | likely `spyware` if ever promoted | low | strong APT-style naming, weak canonical mobile-family evidence |

### Already-curated precedent

These rows are no longer open authority debt, but they are useful as examples of what “safe to promote” looked like.

| candidate token | samples | sample_ids | current status | type_slug | evidence summary | source URLs |
|---|---:|---|---|---|---|---|
| `frogblight` | 6 | `9251,9252,9253,9254,9255,9256` | `authority_family_typed` | `banker` | direct family labels + VT `frogblight` signal, banker subtype | `https://securelist.com/frogblight-banker/118440/` |
| `pjobrat` | 3 | `440,460,474` | `authority_family_typed` | `rat` | direct family labels + VT `pjobrat` signal | `https://news.sophos.com/en-us/2025/03/27/pjobrat-makes-a-comeback-takes-another-crack-at-chat-apps/` |
| `caprarat` | 3 | `302,547,557` | `authority_family_typed` | `rat` | direct family label; VT labels drift through `androrat`, but RAT fit remained clean | `https://www.scworld.com/news/caprarat-malware-targeting-android-users-with-fake-apps` |
| `actionspy` | 3 | `218,261,373` | `authority_family_typed` | `spyware` | direct family label + repeated `axespy/actionspy` VT signals | external source already used in prior tranche |
| `finspy` | 3 | `27,133,178` | `authority_family_typed` | `spyware` | direct family labels + stable `finspy` VT signals | `https://usa.kaspersky.com/blog/finspy-commercial-spyware/18053/` |
| `exodus` | 3 | `11,28,70` | `authority_family_typed` | `spyware` | direct family labels + `exod/exodus` VT signals | `https://botherder.org/blog/2019/03/29/exodus.html` |
| `hydra` | 3 | `91,785,1010` | `authority_family_typed` | `banker` | direct family labels; banker subtype; stable enough despite some `bian` drift | `https://cyble.com/blog/hydra-android-malware-distributed-via-play-store/` |
| `mysterybot` | 3 | `98,244,911` | `authority_family_typed` | `banker` | direct family label, banker subtype, stable family history | `https://www.threatfabric.com/blogs/mysterybot__a_new_android_banking_trojan_ready_for_android_7_and_8` |
| `callerspy` | 3 | `10,44,46` | `authority_family_typed` | `spyware` | direct family labels + stable vendor naming | external source already used in prior tranche |

### Alias precedent

| local token | current canonical family | type_slug | rationale |
|---|---|---|---|
| `bankerspanish` | `basbanke` | `banker` | local label drift, but VT signal and external reporting aligned to BasBanke |
| `camscannernecron` | `necro` | `dropper` | composite local label over a downloader/dropper family |

## 3. Candidate Review CSV Schema

Recommended CSV columns:
- `review_rank`
- `candidate_kind`
- `candidate_token`
- `sample_count`
- `sample_ids`
- `sha256_first_10`
- `package_names`
- `package_prefix_clusters`
- `source_batch_label`
- `analysis_lane`
- `authority_bucket`
- `authority_gap_reason`
- `raw_classification_primary`
- `raw_classification_subtype`
- `vt_family_token`
- `vt_suggested_threat_label`
- `popular_threat_name`
- `popular_threat_category`
- `top_nonblank_vendor_labels`
- `pi_rows_with_coverage`
- `avg_pi_observation_count`
- `existing_family_match`
- `existing_alias_match`
- `likely_action`
- `suggested_canonical_family_name`
- `suggested_type_slug`
- `confidence`
- `evidence_notes`
- `external_sources`

## 4. Top 20 Ranked Candidate Rows / Groups

Ranked by practical repair value, not just raw row count.

| rank | candidate | rows | current state | likely action | why this rank |
|---:|---|---:|---|---|---|
| 1 | `com.ubnt.easyunifi` recent cluster | 16 | open | keep review-only | biggest coherent recent cluster; likely legitimate/repackaged app namespace; should be separated from malware authority work |
| 2 | recent blank-package tranche | 22 | open | keep review-only | largest recent unresolved mass; needs evidence enrichment, not authority promotion |
| 3 | `badpack` | 8 | open | do not promote | biggest repeated unresolved token; strong evidence it is technique/evasion, not family |
| 4 | `spybanker` | 4 | open | do not promote | repeated but looks like generic vendor banker token |
| 5 | `blackloan` | 3 | open | needs external research | repeated local label with banker-ish vendor detections but weak family evidence |
| 6 | `molerats` | 3 | open | needs external research | repeated token but likely campaign/group naming rather than governed family |
| 7 | `scarletmimic` | 3 | open | needs external research | same issue as `molerats`; likely APT/campaign naming |
| 8 | `fklz` recent one-off | 1 | open | needs external research | strongest recent 59-row one-off family clue |
| 9 | `boogr` recent one-off | 1 | open | needs external research | useful banker clue in recent 59-row tranche |
| 10 | `jiagu` recent one-off | 1 | open | do not promote | packer/protector evidence, not family |
| 11 | `frogblight` | 6 | closed | no change | precedent for safe new-family promotion |
| 12 | `pjobrat` | 3 | closed | no change | precedent for safe RAT-family promotion |
| 13 | `caprarat` | 3 | closed | no change | precedent for safe RAT-family promotion |
| 14 | `actionspy` | 3 | closed | no change | precedent for alias-backed spyware promotion |
| 15 | `finspy` | 3 | closed | no change | precedent for stable spyware-family promotion |
| 16 | `exodus` | 3 | closed | no change | precedent for stable spyware-family promotion |
| 17 | `hydra` | 3 | closed | no change | precedent for stable banker-family promotion |
| 18 | `mysterybot` | 3 | closed | no change | precedent for stable banker-family promotion |
| 19 | `callerspy` | 3 | closed | no change | precedent for stable spyware-family promotion |
| 20 | `bankerspanish` / `camscannernecron` | 8 combined | closed via alias | no change | precedent for alias-over-local-label normalization |

## 5. Do-Not-Promote List

| token / cluster | reason |
|---|---|
| `badpack` | APK tampering / evasion / malformed-package technique, not family |
| `spybanker` | generic vendor/class-style banker detection; weak evidence of canonical family |
| `jiagu` | packer/protector signal, not family |
| `com.ubnt.easyunifi` | package-name cluster for a legitimate public app; no family evidence |
| blank / unlabeled recent rows | evidence-free import/catalog backlog, not taxonomy truth |

## 6. Proposed Authority Actions

Open queue:
- `blackloan`
  - likely action: `needs external research`
  - suggested type if later confirmed: `banker`
  - confidence: `medium`
- `molerats`
  - likely action: `review-only / needs external research`
  - suggested type if ever promoted: `spyware`
  - confidence: `low`
- `scarletmimic`
  - likely action: `review-only / needs external research`
  - suggested type if ever promoted: `spyware`
  - confidence: `low`
- recent one-off signals `fklz`, `boogr`
  - likely action: `needs external research`
  - confidence: `medium`

Closed / no-action precedent:
- `frogblight`, `pjobrat`, `caprarat`, `actionspy`, `finspy`, `exodus`, `hydra`, `mysterybot`, `callerspy`

## 7. Final Recommendation

The first actual DB change after this read-only packet should **not** be a blind batch of new family rows.

Recommended order:
1. Add aliases to existing families where the evidence already points to a known governed family.
   - already proven effective with `bankerspanish -> basbanke` and `camscannernecron -> necro`
2. Add new family authority rows only for tokens with:
   - repeated rows
   - consistent Android subtype
   - stable non-generic VT signal
   - external source support stronger than one vendor label
3. Mark tokens as generic/coarse or technique-level where appropriate.
   - `badpack`, `spybanker`, `jiagu`
4. Keep recent evidence-poor backlog rows as review-only until they gain stable family signal.
   - especially `com.ubnt.easyunifi` and the 22 blank-package rows

Conservative conclusion:
- the next write tranche should probably be **small alias / mark-as-non-family work**, not another large family-creation pass
- the remaining unresolved bucket is now more about taxonomy policy and evidence quality than raw missing-family coverage
