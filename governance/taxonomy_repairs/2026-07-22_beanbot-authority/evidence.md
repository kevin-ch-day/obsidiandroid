# BeanBot authority repair

## Research question

Can the existing inactive `beanbot` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `SMS-Trojan` type, without adding aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 300 (`Beanbot`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
three catalog mappings. No active family slug or alias collision for
`beanbot` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=300`

## Independent evidence

- [Spreitzenbarth Current Android Malware](https://forensics.spreitzenbarth.de/android-malware/)
  describes BeanBot as an SMS-capable Trojan controlled by a C&C server.
- [SCIRP Android malware families analysis](https://www.scirp.org/journal/paperinformation?paperid=36799)
  cites the Jiang BeanBot SMS Trojan security alert as primary literature.

## Impact and limitations

The repair remaps to `SMS-Trojan`, activates family 300, and adds
source/review metadata only. It does not alter mappings or assert every
sample behavior.
