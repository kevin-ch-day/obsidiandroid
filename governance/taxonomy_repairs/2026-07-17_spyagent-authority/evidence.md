# SpyAgent authority repair

## Research question

Can the existing inactive `spyagent` family record be restored as current
Android family authority using its already assigned `Spyware` type, without
adding aliases, changing mappings, or broadening the taxonomy?

## Contemporaneous database evidence

Before application, family 691 (`Spyagent`) was an inactive
`lamda_catalog_gap_bootstrap` row with the existing `Spyware` type, no aliases,
no normalization target, and no canonical source metadata. It had one
exact-slug catalog-family mapping marked `family_under_review`; no active family
slug or alias collision for `spyagent` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=691`

## Independent evidence

- [MITRE ATT&CK: Android/SpyAgent](https://attack.mitre.org/software/S1214/)
  identifies Android/SpyAgent as Android malware and describes it as a spyware
  variant. This supports the existing Android family identity and `Spyware`
  taxonomy placement. It does not establish every behavior of the local mapped
  sample.
- [Microsoft Security Intelligence: Trojan:AndroidOS/SpyAgent.K](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan%3AAndroidOS%2FSpyAgent.K)
  independently provides an Android-targeted SpyAgent threat surface. It is
  supporting evidence for the family identity, not a source for sample-level
  attribution.

## Impact and conservative action

The repair activates the pre-existing family record and adds source/review
metadata only. It keeps family ID 691 and type ID 2. It does not create a
family or alias, alter samples or mappings, change a normalization target,
modify a model, or execute a benchmark. The expected direct effect is that the
one existing exact-slug mapping becomes visible through current family
authority.

## Rejected alternatives

- Creating a second SpyAgent family would duplicate an existing identity.
- Adding aliases would broaden a one-mapping repair without a demonstrated need.
- Assigning a different type would contradict the existing, independently
  supported spyware classification.

## Limitations

The external sources support family identity and taxonomy placement only. This
repair is a narrow authority-governance change, not a benchmark result or a
claim about all samples labelled similarly by vendors.
