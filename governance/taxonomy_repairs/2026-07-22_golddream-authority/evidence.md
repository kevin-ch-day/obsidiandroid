# GoldDream authority repair

## Research question

Can the existing inactive `golddream` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `Backdoor` type, without adding aliases, changing mappings, or
asserting additional behavior?

## Contemporaneous database evidence

Before application, family 267 (`Golddream`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
nine catalog mappings. No active family slug or alias collision for
`golddream` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=267`

## Independent evidence

- [F-Secure: Trojan:Android/GoldDream](https://www.f-secure.com/v-descs/trojan-android-golddream.shtml)
  documents SMS/call monitoring plus remote C2 command execution
  (install/uninstall apps, send SMS, place calls).
- [AMD 2017 Android malware dataset paper](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  classifies GoldDream as a Backdoor family.
- [NC State: Losing Sleep — GoldDream](https://news.ncsu.edu/2011/07/wms-golddream/)
  independently describes the Android GoldDream family and bot/C2 behavior.

The local `Backdoor` type matches the AMD ground-truth placement and the
remote command-execution surface documented by F-Secure and NC State.

## Impact and conservative action

The repair replaces the placeholder type with `Backdoor`, activates the
existing family record, and adds source/review metadata. It retains family
ID 267; creates no family or alias; does not alter samples or mappings; and
does not run a benchmark.

## Limitations

External sources support family identity and Backdoor placement. This repair
does not attribute every behavior to every mapped sample or create a frozen
benchmark artifact.
