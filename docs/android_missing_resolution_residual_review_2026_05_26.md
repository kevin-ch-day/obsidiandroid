# Android Missing-Resolution Residual Review

After token policy cleanup and package/sample false-positive suppression, the
`missing_resolved_family` bucket is mostly reduced to a small residue of rows
that still need real analyst review.

## Current Shape

- total `missing_resolved_family` rows: `59`
- rows already covered by package/sample FP suppression: `50`
- residual unsuppressed rows after latest pass: expected `8`

## Residual Review Queue

These are the rows that should stay unsuppressed for now because they still
carry nontrivial VT signal or suspicious packaging:

- `28928` `com.app.pacotesinkinstall`
  - `vt_malicious_count=34`
  - `vt_family_token=fklz`
  - held out of family authority, but clearly not benign-review noise
- `32461` `com.antivirus.protectsecure`
  - `vt_malicious_count=27`
  - strong suspicious signal, no suppression
- `31196` `<blank>`
  - `vt_malicious_count=20`
  - `vt_family_token=jiagu`
  - packer-style evidence, still suspicious
- `32513` `com.dakls`
  - `vt_malicious_count=9`
  - `vt_suggested_label=trojan.boogr`
- `31044` `<blank>`
  - `vt_malicious_count=6`
- `32351` `com.tencent.mobileqqq`
  - `vt_malicious_count=5`
- `32521` `de.resolution.yf_androie`
  - `vt_malicious_count=5`
- `31128` `com.goyal.website2apk`
  - `vt_malicious_count=3`
  - package appears unstable/reused across unrelated APK pages, so not safe for suppression

## What Not To Do

- do not turn these rows into family authority just to close the bucket
- do not blanket-suppress suspicious singleton packages with real VT signal
- do not treat reused/distribution-style package IDs as legitimacy evidence

## Next Action

The remaining lane is now small enough for manual analyst review or a dedicated
“suspicious unknown_sparse Android backlog” queue. That is the right surface for
the final residue, not family taxonomy repair.
