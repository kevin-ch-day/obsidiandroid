# Android Missing Data Research Pass - 2026-05-28

## Current State

- Raw missing primary labels: 33 after tranche `android_missing_primary_label_backfill_tranche_2026_05_28_w.sql`.
- Active/actionable missing-primary debt: 0; all remaining raw-missing rows are currently sample-suppressed.
- Active missing-resolution queue: 2 rows after making `v_android_missing_resolution_triage` suppression-aware and applying tranche `vt_false_positive_suppression_tranche_2026_05_28_f.sql`.
- Suppressed missing-resolution noise: 57 rows moved out of the active family-repair queue because they are reviewed provenance, low-context, or coarse non-family taxonomy rows.
- Remaining active queue split: 2 VT-tail generic rows (`fklz`, `boogr`).

## Applied Repair

Tranche `android_missing_primary_label_backfill_tranche_2026_05_28_w.sql` backfilled only coarse type labels:

- `33603` -> `Trojan / Banker`
- `33604` -> `Trojan / Banker`
- `35267` -> `Trojan / Banker`

Family labels remain blank because local VT evidence mixes `Android/Spy.Banker.AZQ`, `BankBot.Coper`, and `Marcher`. That is enough for coarse banker typing, not enough for governed family authority.

## Queue Reduction Repair

The missing-resolution triage view now joins `vt_false_positive_suppression_rule` and excludes active sample/package suppressions from the active family-repair queue. This prevents already-reviewed public-package, low-context, and non-family taxonomy rows from repeatedly appearing as family authority blockers.

Tranche `vt_false_positive_suppression_tranche_2026_05_28_f.sql` suppresses six coarse non-family rows from the active family-resolution queue:

- `31044`: packed/riskware/PUA class signal.
- `31196`: Jiagu/packer class signal.
- `31128`: DebugKey/MobiDash/PUA class signal.
- `32351`: TestKey/FakeClone/riskware class signal.
- `32461`: HiddenApp/PUP/CoinMiner-style class signal.
- `32521`: TestKey/AdLibrary/FakeClone/riskware class signal.

These suppressions do not declare the samples benign and do not change family authority. They only keep non-family class labels out of family curation.

## Web-Researched Package Identity Findings

These look like public app identity/provenance cleanup candidates, not malware-family repair candidates:

- `com.frontrow.vlog`: Google Play lists this as `VN - AI Video Editor`, by Ubiquiti Labs, with 100M+ downloads.
  Source: https://play.google.com/store/apps/details?id=com.frontrow.vlog
- `net.telewebion`: Google Play indexes Telewebion under this package.
  Source: https://play.google.com/store/apps/details?id=net.telewebion
- `com.ubnt.easyunifi`: app-indexing sites identify this as UniFi / UniFi EasySetup by Ubiquiti.
  Source: https://apkgk.com/com.ubnt.easyunifi
- `com.learn.toppr`: APKFab identifies this as `Toppr Learn - JEE Main, NEET`, package `com.learn.toppr`.
  Source: https://apkfab.com/toppr-learn-jee-main-neet/com.learn.toppr
- `fc.admin.fcexpressadmin`: APKFab identifies this as FirstCry India - Baby & Kids.
  Source: https://apkfab.com/firstcry-baby-kids-shopping-fashion-parenting/fc.admin.fcexpressadmin
- `com.theporter.android.driverapp`: APK indexes identify this as Porter Partner / driver app.
  Source: https://apkshub.com/app/com.theporter.android.driverapp

Recommended handling: create a reviewed-provenance or benign/public-app suppression lane for these exact sample IDs/packages. Do not set malware family labels.

## Malware-Family Research Findings

- `trojan.boogr` is ambiguous: one public article describes a malicious fake AEMET smishing APK with `trojan.boogr`, but F-Droid community evidence also shows `Boogr` can be noisy/false-positive-like in some contexts.
  Sources:
  - https://www.elprogreso.es/articulo/tecnologia/alerta-falsa-app-aemet/202411141159581804409.html
  - https://forum.f-droid.org/t/virustotal-finds-a-virus-in-some-applications-boogr-gsh-fase-positives/10478?page=2
- `fklz` and `boogr` should stay policy-held/generic until stronger family authority exists.
- `Android/Spy.Banker.AZQ`, `BankBot.Coper`, and `Marcher` can support coarse banker typing, but not a single canonical family without more evidence.

## Highest-ROI Next Work

1. Research `sample_id=28928` (`fklz`, `com.app.pacotesinkinstall`) for a real governed family target; current safe state is generic policy hold.
2. Research `sample_id=32513` (`trojan.boogr`, `com.dakls`) carefully because public evidence shows `boogr` can be both malicious in specific campaigns and noisy in other contexts.
3. Keep public/no-signal app packages out of family curation unless new malicious evidence appears.
4. Keep blank-package `classes*.dex` rows out of family curation unless VT or provenance evidence improves.
5. Do not promote `boogr`, `fklz`, `jiagu`, `testkey`, or `debugkey` into family authority.
