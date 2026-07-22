# SmsAgent authority repair

## Research question

Can the existing inactive `smsagent` family record be restored as current
Android family authority using its existing `SMS-Trojan` type, without adding
aliases or changing mappings?

## Contemporaneous database evidence

Before application, family 282 (`Smsagent`) was an inactive
`lamda_catalog_gap_bootstrap` record with the existing `SMS-Trojan` type, no
aliases, no normalization target, and no canonical-source metadata. It had
nine catalog mappings. No active family slug or alias collision for
`smsagent` was found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=282`

## Independent evidence

- [Malpedia: apk.smsagent](https://malpedia.caad.fkie.fraunhofer.de/details/apk.smsagent)
  catalogs SmsAgent as an Android family that appears as a game while
  downloading additional payloads and sending expensive SMS/MMS messages.
- Malpedia references McAfee and EST/Alyac analyses of Trojan.Android.SmsAgent
  campaigns, supporting the local SMS-Trojan typing.

## Impact and limitations

The repair activates family 282 and adds source/review metadata only. It
keeps type ID 14 and does not alter mappings.
