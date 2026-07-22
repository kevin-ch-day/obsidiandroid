# MadAd authority repair

## Research question

Can the existing inactive `madad` family record be restored as current
Android family authority using its existing `Adware` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 289 (`Madad`) was an inactive
`lamda_catalog_gap_bootstrap` record with the existing `Adware` type, no
aliases, no normalization target, and no canonical-source metadata. It had
seven catalog mappings. No active family slug or alias collision for `madad`
was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=289`

## Independent evidence

- [Microsoft: Adware:AndroidOS/MadAd!MTB](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Adware%3AAndroidOS%2FMadAd%21MTB)
  independently provides an Android MadAd adware detection surface matching
  the local family identity and Adware type.

## Impact and limitations

The repair activates family 289 and adds source/review metadata only. It
keeps type ID 3 and does not alter mappings.
