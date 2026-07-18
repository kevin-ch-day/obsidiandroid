# Geinimi authority repair

## Research question

Can the existing inactive `geinimi` record be restored as current Android family
authority after changing its placeholder `Unknown` type to broad `Trojan`,
without adding aliases, changing mappings, or assigning the retired `botnet`
category as a primary type?

## Contemporaneous database evidence

Before application, family 266 (`Geinimi`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical source metadata. It had nine
exact-slug catalog-family mappings, all marked `family_under_review`; no active
family slug or alias collision for `geinimi` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=266`

## Independent evidence and type choice

- [McAfee Threats Report Q4 2010](https://med.a51.nl/sites/default/files/pdf/rp_quarterly_threat_q4_2010.pdf)
  identifies Android/Geinimi as a trojan with botnet command-server behavior.
- [UCR malicious Android-app characterization](https://www.cs.ucr.edu/~neamtiu/pubs/MaliciousAppsTR.pdf)
  independently identifies Geinimi as an Android trojan.

The record uses broad `Trojan` because the database’s `botnet` type is retired
and the sources consistently support the broader family classification.

## Impact and limitations

The repair changes the placeholder type to broad `Trojan`, activates the
existing record, and adds source/review metadata only. It retains family ID 266,
creates no family or alias, changes no mapping or normalization target, and does
not execute a benchmark. It supports authority resolution for nine existing
mappings but does not establish every behavior of each local sample.
