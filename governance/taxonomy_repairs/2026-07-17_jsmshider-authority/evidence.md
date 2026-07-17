# Jsmshider authority repair

## Research question

Could existing inactive bootstrap family 268 (`Jsmshider`) be safely restored as
current Android family authority without creating a duplicate family identity?

## Observed inconsistency

Family 268 already existed with the correct `SMS-Trojan` type but was inactive
and marked `lamda_catalog_gap_bootstrap`. It had no canonical source or active
authority fact, leaving ten catalog-label samples unresolved in the current
authority view.

## Evidence considered

- [Microsoft Security Intelligence: Trojan:AndroidOS/SmsHider.A](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan%3AAndroidOS%2FSmsHider.A)
  identifies `Android.Jsmshider` as an alias and documents Android-targeted SMS
  monitoring and backdoor behavior.
- [Yajin Zhou, *Android Malware: Detection*](https://repository.lib.ncsu.edu/server/api/core/bitstreams/54aa6ff0-d29e-40b3-9c25-bf7478d7b453/content)
  independently treats jSMSHider as an Android malware family and identifies
  its SMS-Trojan context. This supports family identity and type at a taxonomy
  level; it does not independently prove every behavioral claim for every local
  sample.
- The database contained ten historical catalog mappings for family 268, all
  marked `family_under_review`, and no conflicting active family/alias record.

## Conservative action

Reactivate the pre-existing family only. The repair retained family ID 268 and
its existing `SMS-Trojan` type; it did not create a new family, alter a
normalization target, add aliases, modify sample mappings, or run a benchmark.

## Alternatives rejected

- Creating a new SmsHider family would duplicate a supported existing identity.
- Adding several vendor aliases before validating their collision surface would
  broaden the repair unnecessarily.
- Treating historical mappings as current authority without review would bypass
  the evidence record.

## Known uncertainty

The before-state is reconstructed from recorded query output. External sources
support the Android family identity, but local database rows alone do not prove
every reported behavior for every sample.

## Post-change result

Family 268 is active with its existing SMS-Trojan type and Microsoft canonical
source. Ten distinct catalog-label samples resolve to typed family 268. Global
active-alias collision and authority-view duplicate checks remain zero.
