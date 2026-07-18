# Fictus authority repair

## Research question

Can the existing inactive `fictus` family record be restored as current Android
family authority after replacing its placeholder `Unknown` type with the
supported `Adware` type, without adding aliases, changing mappings, or
asserting behavior beyond the sources?

## Contemporaneous database evidence

Before application, family 265 (`Fictus`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had nine
catalog mappings. No active family slug or alias collision for `fictus` was
found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=265`

## Independent evidence

- [FortiGuard Labs: Adware/Fictus!Android](https://www.fortiguard.com/encyclopedia/virus/6669669)
  directly classifies Fictus on Android as adware.
- [Microsoft Security Intelligence: PUA:AndroidOS/Fictus](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=PUA%3AAndroidOS%2FFictus&threatId=404025)
  independently identifies Fictus as an Android potentially unwanted application.

The sources support an Android unwanted-software identity; `Adware` is the
specific active local type explicitly supplied by FortiGuard.

## Impact and conservative action

The repair replaces the existing placeholder type with `Adware`, activates the
existing family record, and adds source/review metadata. It retains family ID
265; creates no family or alias; does not alter samples or mappings; does not
change a normalization target; and does not run a benchmark. The expected direct
effect is that nine existing catalog mappings become visible as typed family
authority.

## Limitations

This narrow authority-governance repair is based on the stated sources and does
not attribute every behavior to every mapped sample, create a frozen benchmark
artifact, or establish a paper-result claim.
