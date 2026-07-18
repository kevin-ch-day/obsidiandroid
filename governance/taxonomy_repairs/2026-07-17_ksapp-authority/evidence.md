# Ksapp authority repair

## Research question

Can the existing inactive `ksapp` record be restored as current Android family
authority with the broad supported `Trojan` type, without changing mappings or
creating an identity duplicate?

## Contemporaneous database evidence

Family 296 (`Ksapp`) was an inactive `lamda_catalog_gap_bootstrap` record with
placeholder `Unknown`, no aliases, no normalization target, no source metadata,
and four catalog mappings. There was no active `ksapp` slug or alias collision.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=296`

## Independent evidence

- [Microsoft Security Intelligence: Trojan:AndroidOS/Ksapp](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan%3AAndroidOS%2FKsapp%21rfn)
  identifies the Android Ksapp threat as a Trojan.
- [AMD 2017 Android malware dataset paper](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  independently lists Ksapp as an Android Trojan family.

## Impact and limitation

This one-row repair changes only the family state, broad type, and source/review
metadata. It preserves family ID 296, aliases, mappings, and normalization; it
does not run a benchmark. The direct effect is that four existing mappings become
typed authority. It does not establish a claim about every mapped sample.
