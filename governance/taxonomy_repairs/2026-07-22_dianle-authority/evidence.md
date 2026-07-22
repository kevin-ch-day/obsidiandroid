# Dianle authority repair

## Research question

Can the existing inactive `dianle` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `Adware` type, without adding aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 287 (`Dianle`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
seven catalog mappings. No active family slug or alias collision for
`dianle` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=287`

## Independent evidence

- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists
  Dianle under the Adware category.
- [Understanding Android Malware Families: Adware and Backdoor](https://docslib.org/doc/6753271/understanding-android-malware-families-adware-and-backdoor-articl)
  independently discusses Dianle among adware families that block/delete apps
  or root devices as part of adware activity.

## Impact and limitations

The repair remaps to `Adware`, activates family 287, and adds source/review
metadata only. It does not alter mappings or assert every sample behavior.
