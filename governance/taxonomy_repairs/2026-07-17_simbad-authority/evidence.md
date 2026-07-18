# SimBad authority repair

## Research question

Can the existing inactive `simbad` family record be restored as current Android
family authority using its existing `Adware` type, without adding aliases,
changing mappings, or broadening the taxonomy?

## Contemporaneous database evidence

Before application, family 290 (`Simbad`) was an inactive
`lamda_catalog_gap_bootstrap` record with the existing `Adware` type, no
aliases, no normalization target, and no canonical source metadata. It had
seven exact-slug catalog-family mappings, all marked `family_under_review`; no
active family slug or alias collision for `simbad` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=290`

## Independent evidence

- [Check Point Research: SimBad](https://research.checkpoint.com/2019/simbad-a-rogue-adware-campaign-on-google-play/)
  identifies SimBad as a rogue Android adware campaign on Google Play. This
  supports the existing Android family identity and `Adware` taxonomy placement.
- [MITRE ATT&CK: SimBad](https://attack.mitre.org/software/S0419/)
  identifies SimBad as Android malware. It independently supports the Android
  family surface; neither source is used to claim that every local mapped sample
  has every documented capability.

## Impact and conservative action

The repair activates the pre-existing family record and adds source/review
metadata only. It keeps family ID 290 and type ID 3. It does not create a
family or alias, alter samples or mappings, change a normalization target,
modify a model, or execute a benchmark. The expected direct effect is that the
seven existing exact-slug mappings become visible through current family
authority.

## Limitations

The external sources support family identity and taxonomy placement only. This
is a narrow authority-governance repair, not a benchmark result or a claim
about all samples bearing a similar vendor label.
