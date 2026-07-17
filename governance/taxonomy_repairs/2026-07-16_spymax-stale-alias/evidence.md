# SpyMax stale-alias repair

## Research question

Did active alias `SpyMax` on family 37 create an ambiguous current authority
assignment after that family had been retired in favor of SpyNote (family 36)?

## Observed inconsistency

Alias 183 (`SpyMax`) was active and preferred while its parent family 37 was
inactive, marked `needs_review`, and had normalization target 36. The active
alias `spymax` already resolved directly to active SpyNote. The resulting alias
join produced one unresolved and one resolved authority row for the same
catalog sample.

## Evidence considered

- `database://erebus_threat_intel_prod/android_malware_family_alias/183`
  is the protected database locator for the repaired alias row. It is a locator,
  not a public URL and does not expose sample-level data.
- Reconstructed terminal output captured alias 183 as active/preferred on
  inactive family 37, with normalization target 36.
- Family 36 was active SpyNote; family 37 retained 29 historical mappings plus
  review, name, and time provenance.
- Post-change read-only validation captured the alias update timestamp and
  confirmed no remaining active normalized-alias collisions or duplicate
  authority-view sample groups.

## Conservative action

Deactivate alias 183 only. The repair did not delete family 37, alter its
normalization target, move historical mappings, or change `is_preferred`.

## Alternatives rejected

- Moving alias 183 to family 36 would duplicate provenance-bearing aliases.
- Deleting family 37 or its mappings would destroy historical evidence.
- Choosing between ambiguous aliases at query time would hide a governance
  defect instead of correcting it.

## Known uncertainty

The before-state is reconstructed from recorded query output, not a
contemporaneous exported snapshot. The current row independently confirms the
post-change identity and state.

## Post-change result

Alias 183 remains present but inactive. Family 37 remains inactive and still
normalizes to family 36. The 29 historical mappings remain present, and the
global alias/authority duplicate checks return zero.
