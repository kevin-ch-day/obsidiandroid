# SMSWorm type lifecycle repair

## Research question

Can the already-active `smsworm` family keep its current identity while remapping
its primary type from the retired `worm` type to the active `sms-trojan` type,
without creating aliases, changing sample mappings, or reactivating `worm`?

## Contemporaneous database evidence

Before application, family 85 (`SMSWorm`) was an active authority family whose
`primary_type_id` pointed at retired type 10 (`worm`). It had 8 catalog
mappings / authority-visible samples and one alias row. No normalization target
was set.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=85`

## Independent evidence

- [SecurityWeek: SMS Worm Hits Chinese Users Hard](https://www.securityweek.com/sms-worm-hits-chinese-users-hard-installs-android-backdoor/)
  (existing canonical source) describes SMS-propagating Android malware with
  trojan/backdoor follow-on behavior.
- [F-Secure: SMS-Worm](https://www.f-secure.com/v-descs/sms-worm)
  defines the SMS-worm category as SMS-distributed mobile malware.
- [Cyble: Android SMS Worm / SMSWorm](https://cyble.com/blog/android-sms-worm-impersonating-covid-19-vaccine-registration-app-spreads-via-text-messages/)
  uses the SMSWorm label for SMS-propagating Android malware that also steals
  sensitive data.
- Local taxonomy already places related SMS malware families (`hipposms`,
  `smskey`) under active type `sms-trojan` (type_id 14).

## Impact and conservative action

The repair remaps only `primary_type_id` from retired `worm` (10) to active
`sms-trojan` (14) and records review metadata. It retains family ID 85, leaves
mappings/aliases untouched, does not reactivate `worm`, and does not run a
benchmark. Expected effect: the eight SMSWorm authority samples report
`sms-trojan` instead of the retired `worm` type.

## Rejected alternatives

- Reactivating `worm` would restore a retired governed type for eight samples.
- Remapping to generic `trojan` would lose the SMS-specific type already used
  for peer SMS malware families.
- Deactivating the family would discard a curated SMS-propagation identity.

## Limitations

External sources support SMS-propagation malware identity and justify the local
`sms-trojan` placement. This repair does not assert every mapped sample's full
behavior set or create a frozen benchmark artifact.
