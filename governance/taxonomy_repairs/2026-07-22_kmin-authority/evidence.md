# Kmin authority repair

## Research question

Can the existing inactive `kmin` family record be restored as current
Android family authority with a researched `SMS-Trojan` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 303 (`Kmin`) was an inactive
`lamda_catalog_gap_bootstrap` record typed `Unknown`, with no aliases, no
normalization target, and no canonical-source metadata. It had three catalog
mappings. No active family slug or alias collision for `kmin` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=303`

## Independent evidence

- [F-Secure: Trojan:Android/Kmin](https://www.f-secure.com/v-descs/trojan-android-kmin.shtml)
  describes decoy prompts followed by premium-rate SMS sending, IMEI/phone
  exfiltration, secondary downloads, and background services.
- [Microsoft: Trojan:AndroidOS/Kmin.A](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan%3AAndroidOS%2FKmin.A)
  and Contagio mobile sample notes corroborate the Android Kmin/KMHome
  SMS/info-stealer surface (including Kaspersky Backdoor.AndroidOS.Kmin aliases).

## Impact and limitations

The repair activates family 303, remaps primary type from Unknown (8) to
SMS-Trojan (14), and adds source/review metadata only. It does not alter mappings.
