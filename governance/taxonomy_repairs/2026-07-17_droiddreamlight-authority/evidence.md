# DroidDreamLight authority repair

## Research question

Can the existing inactive `droiddreamlight` family record be restored as
current Android family authority after changing its placeholder `Unknown` type
to the supported broad `Trojan` type, without adding aliases, changing mappings,
or asserting a narrower subtype?

## Contemporaneous database evidence

Before application, family 260 (`Droiddreamlight`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical source metadata. It had ten
exact-slug catalog-family mappings, all marked `family_under_review`; no active
family slug or alias collision for `droiddreamlight` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=260`

## Independent evidence

- [K7 Labs: DroidDreamLight](https://labs.k7computing.com/index.php/paranoid-android-part-2/)
  identifies DroidDreamLight as `Trojan-Downloader.AndroidOS.DorDrae.b` and an
  Android-market threat.
- [UCR malicious Android-app characterization](https://www.cs.ucr.edu/~neamtiu/pubs/MaliciousAppsTR.pdf)
  independently characterizes DroidDreamLight as a trojan family operating on
  Android devices. The broad `Trojan` type is retained because sources describe
  differing capabilities and do not justify a narrower local primary type.

## Impact and conservative action

The repair changes the existing placeholder type from `Unknown` to the broad
`Trojan` type, activates the existing family record, and adds source/review
metadata. It retains family ID 260; creates no family or alias; does not alter
samples or mappings; does not change a normalization target; and does not run a
benchmark. The expected direct effect is that ten exact-slug mappings become
visible as typed family authority.

## Limitations

The sources support the Android family identity and broad type only. This is a
narrow authority-governance repair, not a benchmark result or an attribution of
all documented behaviors to each local mapped sample.
