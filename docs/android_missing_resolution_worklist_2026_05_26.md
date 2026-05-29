# Android Missing-Resolution Worklist

Current posture:

- `authority_family_typed`: `3065`
- `resolved_unknown`: `188`
- `resolved_but_no_authority_family`: `116`
- `missing_resolved_family`: `59`
- `generic_label_candidate`: `37`

## What Is Still Missing

The remaining truly missing lane is now:

- `59` Android/APK rows
- all `59` from `source_batch_label='raw_hash_reservoir_20260520'`
- almost all in `analysis_lane='unknown_sparse'`
- mostly no `vt_family_token`
- mostly no useful `vt_suggested_label`

This is no longer a family-token repair problem.
It is a package-cluster / low-context-backlog review problem.

## Dominant Clusters

- `<blank>` package name: `22`
- `com.ubnt.easyunifi`: `16`
- `com.frontrow.vlog`: `4`
- `net.telewebion`: `2`

Singleton package tails:

- `com.app.pacotesinkinstall`
- `com.dakls`
- `com.goyal.website2apk`
- `com.growmainwkmm`
- `com.learn.toppr`
- `com.mindsoonvfk`
- `com.stilldifferv`
- `com.tencent.mobileqqq`
- `com.theporter.android.driverapp`
- `com.upwardlyapp.android`
- `de.resolution.yf_androie`
- `fc.admin.fcexpressadmin`
- `app.scrigc.com`
- `by.lsdsl.hdrezka`
- `com.antivirus.protectsecure`

## VT Tail Residue

Only three rows in this bucket have any VT tail at all:

- `fklz`
- `jiagu`
- `boogr`

Disposition:

- `jiagu`: packer/evasion hold, not family
- `fklz`: generic-family hold, not safe family hint
- `boogr`: generic-family hold, too noisy across many governed families

## What To Fix Next

1. Keep this lane out of family-authority curation by default.
2. Review repeated package clusters first:
   - `com.ubnt.easyunifi`
   - `com.frontrow.vlog`
   - `net.telewebion`
   - `<blank>` package rows
3. Treat singleton package rows as low-confidence backlog artifacts unless stronger VT or external evidence appears.
4. Do not create new families from `fklz`, `jiagu`, or `boogr`.

## SQL

Use:

- [android_missing_resolution_worklist.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/android_missing_resolution_worklist.sql)

This separates package-cluster review from family/taxonomy repair so low-context generic backlog rows do not distort Android authority governance.
