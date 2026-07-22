# Ztorg authority repair

## Research question

Can the existing inactive `ztorg` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `Dropper` type, without adding aliases, changing mappings, or
asserting every modular capability?

## Contemporaneous database evidence

Before application, family 286 (`Ztorg`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
eight catalog mappings. No active family slug or alias collision for `ztorg`
was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=286`

## Independent evidence

- [Kaspersky Securelist: Ztorg money for infecting your smartphone](https://securelist.com/ztorg-money-for-infecting-your-smartphone/78325/)
  documents modular Ztorg infection chains that download/drop secondary
  modules and rooting components.
- [Fortinet: Teardown of Android/Ztorg (Part 1)](https://www.fortinet.com/blog/threat-research/teardown-of-a-recent-variant-of-android-ztorg-part-1)
  independently confirms remote APK download/install behavior.
- [AMD 2017 Android malware dataset paper](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  classifies Ztorg as Trojan-Dropper.

The local `Dropper` type matches the AMD ground-truth placement and the
download/drop module behavior documented by Kaspersky and Fortinet.

## Impact and conservative action

The repair replaces the placeholder type with `Dropper`, activates the
existing family record, and adds source/review metadata. It retains family
ID 286; creates no family or alias; does not alter samples or mappings; and
does not run a benchmark.

## Limitations

External sources support family identity and Dropper placement. Later Ztorg
modules include adware/SMS behaviors; this repair does not assert those as
the primary type for every mapped sample.
