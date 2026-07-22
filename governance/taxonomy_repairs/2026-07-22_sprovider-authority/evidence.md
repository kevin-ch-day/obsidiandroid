# Sprovider authority repair

## Research question

Can the existing inactive `sprovider` family record be restored as current
Android family authority after replacing its placeholder `Unknown` type with
the supported `Adware` type, without adding aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 284 (`Sprovider`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had
eight catalog mappings. No active family slug or alias collision for
`sprovider` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=284`

## Independent evidence

- [Dr.Web: Android.Sprovider.7](https://vms.drweb.com/virus/?i=9013116)
  documents firmware-embedded Android.Sprovider that shows ads and installs
  applications.
- [Doctor Web news: Trojans in Android firmware](https://news.drweb.com/show/?i=10345&lng=en)
  independently describes Sprovider ad/display and install behaviors.
- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists
  Sprovider under Adware.

Local `Adware` matches AndMal2020 placement and the advertising-centric
monetization documented by Dr.Web.

## Impact and limitations

The repair remaps to `Adware`, activates family 284, and adds source/review
metadata only. Dr.Web also labels variants as Trojans; this repair chooses
the AndMal adware primary type without asserting every modular capability.
