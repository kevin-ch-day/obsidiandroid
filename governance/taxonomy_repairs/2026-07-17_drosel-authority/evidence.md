# Drosel authority repair

## Research question

Can the existing inactive `drosel` family record be restored as current Android
family authority after replacing its placeholder `Unknown` type with the
supported broad `Trojan` type, without adding aliases, changing mappings, or
asserting an unsupported narrower subtype?

## Contemporaneous database evidence

Before application, family 280 (`Drosel`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had nine
catalog mappings. No active family slug or alias collision for `drosel` was
found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=280`

## Independent evidence

- [Canadian Institute for Cybersecurity Android malware dataset](https://www.ahlashkari.com/Datasets-Android-Malware-Static-Analysis.asp)
  lists `drosel` in its Android Trojan family category.
- [Understanding Android Malware Families taxonomy](https://www.cs.unb.ca/~alashkar/PDFs/Understanding%20Android%20Malware%20Families%20%28UAMF%29%20%E2%80%93%20The%20Trojan%20An%20impersonator%20in%20the%20background%20%28Article%202%29.pdf)
  independently lists Drosel among common Android Trojan families.

## Impact and conservative action

The repair replaces the existing placeholder type with broad `Trojan`, activates
the existing family record, and adds source/review metadata. It retains family
ID 280; creates no family or alias; does not alter samples or mappings; does not
change a normalization target; and does not run a benchmark. The expected direct
effect is that nine existing catalog mappings become visible as typed family
authority.

## Limitations

This narrow authority-governance repair establishes the broad local type only.
It does not attribute every behavior to every mapped sample, create a frozen
benchmark artifact, or establish a paper-result claim.
