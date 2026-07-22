# Mseg authority repair

## Research question

Can the existing inactive `mseg` family record be restored as current Android
family authority after replacing its placeholder `Unknown` type with the
supported `SMS-Trojan` type, without adding aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 304 (`Mseg`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
three catalog mappings. No active family slug or alias collision for `mseg`
was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=304`

## Independent evidence

- [F-Secure: Trojan:Android/Mseg](https://www.f-secure.com/v-descs/trojan-android-mseg.shtml)
  documents silent premium-rate SMS sending plus device-data exfiltration.
- [AMD 2017](https://www.cs.bgsu.edu/sanroy/Files/papers/amd2017.pdf) lists
  Mseg as a Trojan family; premium-SMS behavior supports the local
  `sms-trojan` type used for peer SMS malware families.

## Impact and limitations

The repair remaps to `SMS-Trojan`, activates family 304, and adds
source/review metadata only. It does not alter mappings or assert every
sample behavior.
