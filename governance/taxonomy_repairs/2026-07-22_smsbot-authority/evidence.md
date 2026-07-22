# SmsBot authority repair

## Research question

Can the existing inactive `smsbot` family record be restored as current
Android family authority using its existing `SMS-Trojan` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 283 (`Smsbot`) was an inactive
`lamda_catalog_gap_bootstrap` record with the existing `SMS-Trojan` type, no
aliases, no normalization target, and no canonical-source metadata. It had
nine catalog mappings. No active family slug or alias collision for `smsbot`
was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=283`

## Independent evidence

- [Dr.Web: Android.SmsBot.182](https://vms.drweb.com/virus/?i=16422499)
  documents SMS sending, interception/blocking of incoming SMS, administrator
  privilege use, overlay windows, and SMS parsing — matching SMS-Trojan
  behavior under the Android.SmsBot detection family.

## Impact and limitations

The repair activates family 283 and adds source/review metadata only. It
keeps type ID 14 and does not alter mappings.
