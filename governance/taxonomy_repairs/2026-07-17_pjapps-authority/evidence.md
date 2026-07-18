# PJApps authority repair

## Research question

Can the existing inactive `pjapps` family record be restored as current Android
family authority after replacing its placeholder `Unknown` type with the
supported broad `Trojan` type, without adding aliases, changing mappings, or
asserting a disputed narrower subtype?

## Contemporaneous database evidence

Before application, family 262 (`Pjapps`) was an inactive
`lamda_catalog_gap_bootstrap` record with the placeholder `Unknown` type, no
aliases, no normalization target, and no canonical-source metadata. It had ten
catalog mappings. No active family slug or alias collision for `pjapps` was
found.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=262`

## Independent evidence

- [Microsoft Security Intelligence: TrojanSpy:AndroidOS/Pjapps.A](https://www.microsoft.com/security/portal/Threat/Encyclopedia/Entry.aspx?Name=TrojanSpy%3AAndroidOS%2FPjapps.A)
  identifies the Android Pjapps family and records vendor aliases.
- [F-Secure: Trojan:Android/PjApps](https://www.f-secure.com/v-descs/trojan-android-pjapps.shtml)
  independently identifies the family as Android Trojan malware.

The sources use different capability detail (`TrojanSpy` versus `Trojan`), so
the repair deliberately assigns only the common broad local `Trojan` type.

## Impact and conservative action

The repair replaces the existing placeholder type with `Trojan`, activates the
existing family record, and adds source/review metadata. It retains family ID
262; creates no family or alias; does not alter samples or mappings; does not
change a normalization target; and does not run a benchmark. The expected direct
effect is that ten existing catalog mappings become visible as typed family
authority.

## Limitations

The sources establish the Android family identity and broad local type only.
This narrow authority-governance repair does not attribute every capability to
every mapped sample, create a frozen benchmark artifact, or establish a
paper-result claim.
