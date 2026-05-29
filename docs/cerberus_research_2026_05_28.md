# Cerberus Research Pass

Date: 2026-05-28

## High-confidence external findings

Primary or near-primary sources support the following:

1. Cerberus emerged as a new Android banking Trojan in June 2019 and was rented on underground forums.
2. ThreatFabric assessed the initial Cerberus codebase as written from scratch and not based on Anubis.
3. Cerberus used Accessibility abuse, overlay attacks, SMS control, contact harvesting, call forwarding, USSD, and step-counter sandbox evasion.
4. Kaspersky tracked a 2020 revival after the Cerberus source leak. The source code release materially increased downstream reuse risk.
5. Post-leak descendants should be modeled as lineage, not aliases:
   - `ermac -> cerberus`
   - `hook -> ermac`

## Sources used

- ThreatFabric, `Cerberus - A new banking Trojan from the underworld`, 2019-08-01  
  https://www.threatfabric.com/blogs/cerberus-a-new-banking-trojan-from-the-underworld
- Kaspersky press release, `The rise of Cerberus`, 2020-09-16  
  https://www.kaspersky.com/about/press-releases/the-rise-of-cerberus
- MITRE ATT&CK `S0480 Cerberus`  
  https://attack.mitre.org/software/S0480/
- Cyble, `ERMAC Malware: Latest Threats, Attack Methods & Cybersecurity Insights`, 2022-05-25  
  https://cyble.com/blog/ermac-back-in-action/
- Prey, `Cerberus RAT: Android malware’s dark legacy in 2025`  
  https://preyproject.com/blog/cerberus-rat-android-malware-dark-legacy

## Local catalog findings

Current Android catalog footprint:

- `Cerberus`: 28 rows
- `Ermac`: 18 rows
- `Alien`: 28 rows

Cerberus vs ERMAC:

- shared Android package names: 0
- shared SHA256s: 0
- overlap is mostly generic banker-tail noise such as `hqwar` and `bankbot`
- current data supports lineage, not synonym merge

Cerberus package/hash corroboration from ThreatFabric appendix:

- ThreatFabric appendix package `com.uxlgtsvfdc.zipvwntdy` with SHA256 `728a6ea44aab94a2d0ebbccbf0c1b4a93fbd9efa8813c19a88d368d6a46b4f4f`
  matches local sample `1392`
- ThreatFabric appendix package `com.mwmnfwt.arhkrgajn` with SHA256 `ffa5ac3460998e7b9856fc136ebcd112196c3abf24816ccab1fbae11eae4954c`
  matches local sample `2418`

This gives direct source-backed confidence that at least part of the local Cerberus slice is anchored to the original 2019 ThreatFabric reporting.

## Data implications

Safe changes already applied:

- explicit lineage edges:
  - `ermac -> cerberus`
  - `hook -> ermac`
- typo normalization:
  - `cebruser -> cerberus`
- explicit Cerberus VT-tail sample hints normalized to Cerberus
- ERMAC version strings normalized to canonical ERMAC:
  - `ermacv2 -> ermac`
  - `ermac 2.0 -> ermac`

## Residual review items

Cerberus still has a small residual review slice where other strings appear on top of the governed catalog family, for example:

- `sample_label = Xerxes`
- `sample_label = Godfather`
- `vt_family_token = brunhilda`
- `vt_suggested_label` tails containing `godfather`, `brunhilda`, or other cross-family names

These should remain analyst-review rows rather than being auto-merged into or out of Cerberus.

Diagnostic:

- [cerberus_residual_review_2026_05_28.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/cerberus_residual_review_2026_05_28.sql)

## Recommended taxonomy policy

1. Keep `Cerberus` separate from `Ermac`, `Hook`, and `Alien`.
2. Use lineage edges for descendants or forks instead of aliasing them together.
3. Treat `bankbot`, `hqwar`, and similar banker tails as generic or parser-context strings, not Cerberus synonyms.
4. Accept explicit family strings like `trojan.cerberus/...` as sample-level support for Cerberus truth.
