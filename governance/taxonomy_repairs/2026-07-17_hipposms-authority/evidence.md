# HippoSMS authority repair

## Research question

Can the existing inactive family 257 (`Hipposms`) be restored as current
Android family authority while retaining its established `SMS-Trojan` type and
without broadening the taxonomy?

## Contemporaneous database evidence

Before application, family 257 was an inactive `needs_review` bootstrap row
with `primary_type_id=14` (`sms-trojan`), no aliases, no normalization target,
and no canonical source metadata. It had 23 exact-slug mappings, representing
23 distinct samples, all marked `family_under_review`; it had no authority-view
rows and no active slug or alias collision for `hipposms`.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=257`

## Independent evidence

- [F-Secure Threat Descriptions: Trojan:Android/HippoSms](https://www.f-secure.com/v-descs/trojan-android-hipposms)
  identifies HippoSms as Android malware/Trojan and documents SMS sending and
  deletion behavior. This supports the existing Android and SMS-Trojan
  taxonomy placement.
- [CCCS-CIC-AndMal-2020](https://www.unb.ca/cic/datasets/andmal2020.html)
  lists `hipposms` within its `Trojan-SMS` family table. It independently
  supports the family-to-type relationship; it is not used to assert that the
  local mapped samples originate from that dataset.

## Impact and conservative action

The repair activates the pre-existing family record and fills source/review
metadata only. It retains family ID 257 and type ID 14. It does not create a
family or alias, alter samples or mappings, change a normalization target,
modify models, or execute a benchmark. The expected direct effect is that the
23 existing mapped samples become visible through current family authority.

## Rejected alternatives

- Creating a second HippoSMS family would duplicate an existing identity.
- Adding aliases would broaden the change without a demonstrated need.
- Reclassifying historical mappings is unnecessary because their exact-slug
  family mapping already exists.

## Limitations

The evidence supports the family identity and taxonomy placement, not every
behavioral property of every local sample. The authority-view increase is a
taxonomy-governance effect, not a benchmark result.
