# Android Typed Rows Without Permission Intel

## QA Finding

`79` Android rows are already `authority_family_typed` but still have no
Permission Intel observations.

Additional QA clarification from the live DB:

- total typed rows: `3065`
- typed rows with blank package name: `79`
- typed rows with nonblank package name: `2986`
- rows without PI and blank package: `79`
- rows without PI and nonblank package: `0`
- PI coverage on all typed rows: `0.9742`
- PI coverage on typed rows with nonblank package: `1.0000`
- PI coverage on typed rows with blank package: `0.0000`

This is a real QA surface because it affects downstream feature completeness,
but it is not spread uniformly across the corpus.

## Concentration

The gap is concentrated in:

- `analysis_lane='android_artifact'` only
- mostly banker families
- especially:
  - `fatboypanel` (`18`)
  - `golddigger` (`8`)
  - `frogblight` (`5`)
  - `trickmo` (`5`)
  - `vultur` (`5`)
  - `zanubis` (`5`)

## Pattern

The detailed rows show a strong completeness pattern:

- package name is often blank
- VT family token is often weak or absent
- VT suggested labels are frequently coarse

In fact, the current gap is fully explained by blank-package rows:

- there are no typed rows with a nonblank package name that are missing PI

That suggests many of these rows may be typed correctly at the family layer
while still lacking the APK-derived/permission-derived substrate needed for PI.

## Why This Matters

This is likely not a family-taxonomy error.
It is more likely:

- APK extraction / parse incompleteness
- missing permission ingest for otherwise typed Android rows
- or typed rows that were curated from VT/vendor context without full APK-level PI enrichment

Operationally, this lowers the severity of the PI gap:

- it does **not** look like a broad PI processing regression
- it looks like a metadata-thin typed cohort that never exposed package/permission substrate to PI

## SQL

Use:

- [android_typed_without_pi_audit.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/android_typed_without_pi_audit.sql)
