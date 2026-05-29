# Advanced Regex Audit

Date: `2026-05-27`

This pass moves regex analysis from simple exact-label cleanup into morphology:

- lexical stem families
- token-shape families
- package-shape families
- residual FP review label-shape families

The rerunnable SQL pack is:

- [database/sql/android_regex_advanced_audit.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/android_regex_advanced_audit.sql)

## Live Findings

### 1. Residual unresolved-family tokens mostly lack strong malware-family stems

Largest stem buckets:

- `no_signal_stem`: `56`
- `contains_bot`: `10`
- `contains_fake_fraud_phish`: `9`
- `contains_pack`: `9`
- `contains_bank_or_loan`: `8`
- `contains_spy`: `5`

Interpretation:

- the residual unresolved-family queue is no longer dominated by hidden canonical-family names
- it is dominated by either:
  - stemless compact labels
  - policy-hold style labels
  - campaign/composite/coarse terms

### 2. Shape-wise, unresolved-family debt is overwhelmingly `letters_only`

Shape buckets:

- `letters_only`: `101`
- `contains_space`: `9`
- `contains_punct`: `4`
- `alnum_compact`: `2`

Interpretation:

- once punctuation/composite noise was reduced, the residual tail became mostly simple lowercase slug tokens
- regex can still separate some semantics, but the remaining queue is no longer filename noise

### 3. Missing-resolution package lane is structurally simple

Main package/VT-tail pairings:

- `com_style_package + no_vt_tail`: `29`
- `blank_package + no_vt_tail`: `21`
- `other_tld_style_package + no_vt_tail`: `5`
- only `2` rows have weak VT tails in the whole lane:
  - blank package + weak tail: `1`
  - com-style package + weak tail: `1`

Interpretation:

- the missing-resolution lane is overwhelmingly a no-context package backlog
- it is not hiding a large regex-discoverable family-token signal

### 4. Effective false-positive review residue still has strong label-shape structure

Main shape buckets:

- `compact_slug / android`: `16`
  - all `Gigabud`
- `file_suffix_like / windows`: `11`
- `file_suffix_like / unknown`: `6`
- `generic_placeholder / unknown`: `5`
- `generic_placeholder / windows`: `4`
- `hash_prefix_like / unknown`: `3`

Interpretation:

- the effective FP queue still splits cleanly into:
  - real malware-family compact slugs that should stay visible
  - artifact/file-like residue that may still be suppressible
  - generic placeholders like `UNCLASSIFIED` / `Phishing`

### 5. Regex conclusion

Regex is still useful, but in a different role now:

- not to discover many more family names
- but to separate:
  - family-like compact slugs
  - package/provenance backlog noise
  - generic placeholders
  - artifact/file/hash residue

## Operational Meaning

The hidden pattern we were missing is:

- unresolved authority debt is now mostly semantically weak lowercase slug residue
- missing-resolution debt is now mostly package-shape plus no-VT-tail residue
- effective FP residue still has enough artifact morphology to support more QA cleanup

So the next regex-driven work should focus on:

1. placeholder and artifact review in the effective FP queue
2. package/provenance routing for the missing-resolution lane
3. resisting the urge to interpret every remaining lowercase slug as a new family candidate
