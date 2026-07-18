# FakeAngry authority repair

## Research question

Can the existing inactive `fakeangry` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `Backdoor` type, without adding aliases, changing mappings, or
asserting additional behavior?

## Contemporaneous database evidence

Before application, family 261 (`Fakeangry`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had ten
catalog mappings. No active family slug or alias collision for `fakeangry` was
found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=261`

## Independent evidence

- [Bitdefender: From China with Love: New Android Backdoor](https://www.bitdefender.com/en-gb/blog/hotforsecurity/from-china-with-love-new-android-backdoor-spreading-through-hacked-apps)
  identifies the FakeAngry family as an Android backdoor.
- [AMD 2017 Android malware dataset paper](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  independently lists FakeAngry as a Backdoor family with ten samples.

The two sources agree on the Android family identity and the local `Backdoor`
type. No alias, normalization, or sample-mapping decision is needed.

## Impact and conservative action

The repair replaces the existing placeholder type with `Backdoor`, activates
the existing family record, and adds source/review metadata. It retains family
ID 261; creates no family or alias; does not alter samples or mappings; does not
change a normalization target; and does not run a benchmark. The expected direct
effect is that ten existing catalog mappings become visible as typed family
authority.

## Limitations

The sources establish the historical Android family identity and broad local
type. This narrow authority-governance repair does not attribute every behavior
to every mapped sample, create a frozen benchmark artifact, or establish any
paper-result claim.
