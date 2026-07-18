# SmsKey authority repair

## Research question

Can the existing inactive `smskey` family record be restored as current Android
family authority using its existing `SMS-Trojan` type, without adding aliases,
changing mappings, or broadening the taxonomy?

## Contemporaneous database evidence

Before application, family 274 (`Smskey`) was an inactive
`lamda_catalog_gap_bootstrap` record with the existing `SMS-Trojan` type, no
aliases, no normalization target, and no canonical source metadata. It had nine
exact-slug catalog-family mappings, all marked `family_under_review`; no active
family slug or alias collision for `smskey` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=274`

## Independent evidence

- [Argus Lab Android Malware Dataset: Trojan-SMS.SmsKey.1](https://amd.arguslab.org/families/SmsKey/variety1.html)
  identifies SmsKey as `Trojan-SMS.SmsKey.1` and preserves a Sophos threat
  reference. This supports the existing Android family identity and
  `SMS-Trojan` placement.
- [Android Malware Dataset research](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  independently lists SmsKey as an Android Trojan-SMS family. Neither source is
  used to assert behavior for every local mapped sample.

## Impact and conservative action

The repair activates the pre-existing record and adds source/review metadata
only. It retains family ID 274 and type ID 14; it creates no family or alias,
does not alter samples or mappings, does not change a normalization target, and
does not execute a benchmark. The expected direct effect is that nine existing
exact-slug mappings become visible through current family authority.

## Limitations

The evidence supports family identity and taxonomy placement only. This is a
narrow authority-governance repair, not a benchmark result or a claim about all
similarly named vendor labels.
