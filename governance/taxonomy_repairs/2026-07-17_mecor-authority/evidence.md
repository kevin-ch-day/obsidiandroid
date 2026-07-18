# Mecor authority repair

## Research question

Can the existing inactive `mecor` record be restored as current Android family
authority after changing its placeholder `Unknown` type to the policy-consistent
broad `Trojan` type, without adding aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 270 (`Mecor`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical source metadata. It had nine
exact-slug catalog-family mappings, all marked `family_under_review`; no active
family slug or alias collision for `mecor` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=270`

## Independent evidence and type policy

- [Argus Lab Android Malware Dataset: Mecor](https://amd.arguslab.org/families/Mecor.html)
  identifies Mecor as Android `Trojan-Spy` malware and references a Sophos
  threat analysis.
- [AMD2017 family/type survey](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf)
  independently lists Mecor as an Android Trojan-Spy family.
- The application’s parser policy maps `trojan-spy` to broad `trojan`
  ([parser defaults](/home/secadmin/Laughlin/GitHub/obsidiandroid/src/obsidiandroid/vendors/parsing/parser_defaults.py)).
  The repair follows that policy rather than inferring a narrower subtype.

## Impact and limitations

The repair changes the existing placeholder type to broad `Trojan`, activates
the pre-existing record, and adds source/review metadata only. It retains family
ID 270, creates no alias or family, alters no sample or mapping, changes no
normalization target, and executes no benchmark. It supports authority
resolution for nine existing mappings but does not establish every behavior of
each local sample.
