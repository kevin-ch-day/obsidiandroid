# ATT&CK mapping reconciliation snapshot — 2026-11-14

Read-only snapshot of the `android_permission_intel` ATT&CK objects compared with the
ObsidianDroid relationship contract `config/taxonomy/mobile_attack_permission_mapping.yaml`
(`permission-attack-relationships-v2`, version `20261113-v3`, 21 rules, 29 token→technique edges).

- Connection: `mariadb -u claude_ro` over the local unix socket; grants are `SELECT, SHOW VIEW` only.
  Statements executed are listed verbatim in `queries.sql`. No DDL, DML, grant or migration ran.
- Generated: see `snapshot_receipt.json` (`generated_at_utc`, bundle hashes, YAML hash).
- Regenerate with `generate_snapshot.py` into a fresh directory; it refuses to overwrite outputs.

## Release provenance matters

The database objects were created and seeded by Erebus migration `0058_pi_attack_context_layer.sql`,
recorded in `schema_migrations` as version `0058` applied **2026-05-17 17:28:36 UTC**. Mobile ATT&CK
**v20.1 was released 2026-11-05** (collection object modified 2026-11-05T05:02:21Z; GitHub release
published 2026-11-05T16:35:43Z per `config/taxonomy/mitre/mobile-attack-v20.1.source-manifest.json`).
The database LUT and the YAML pin therefore derive from different ATT&CK releases, and the LUT carries
no release, STIX id, version or modified metadata of its own.

`lut_vs_attack_releases.tsv` records, per technique, whether the LUT name and tactic match v20.1 and,
where determinable from a retained earlier bundle, which earlier release they match. The earlier bundle
available offline is Mobile ATT&CK **v19.2** (collection modified 2026-08-05; SHA-256
`acfa5ca2d93484476f79bf38590e2b55bb675fc0ce85e76bffa0af2c82dada64`, retained under
`~/Documents/Erebus_Audits/EVIDENCE/archive/.../run-003-attack-evidence/source/mobile-attack-19.2.json`).
Result: 8 of 10 LUT rows are consistent with both v19.2 and v20.1 (names either exact or the
"Parent: Sub-technique" display alias). `T1453` (LUT: Privilege Escalation; official: Collection,
Credential Access) and `T1582` (LUT: Command and Control; official: Impact) match **neither** v19.2 nor
v20.1. Both official objects were last modified 2026-05-12, five days before the seed, so the LUT either
followed a pre-2026-05-12 release or was hand-authored; no earlier bundle is retained offline to decide
which (UNKNOWN).

## Files

| File | Content |
|---|---|
| `queries.sql` | Exact read-only statements |
| `lut_rows.tsv` | 10 rows of `android_attack_technique_lut` |
| `mapping_rows.tsv` | 16 rows of `android_permission_attack_mapping` with `HEX()`, byte/char length, collation (`utf8mb4_unicode_ci`), plus dictionary/identity facts for each token |
| `view_definitions.txt` | `SHOW CREATE VIEW` for both `v_android_permission_attack_surface_*` views |
| `view_summary_rows.tsv` | Current summary-view output (9 techniques) |
| `lut_vs_attack_releases.tsv` | LUT vs v20.1 and v19.2 with name/tactic match and release attribution columns |
| `db_rows_vs_yaml_edges.tsv` | One row per token→technique edge with a `disposition` and a `strength_conflict` flag |
| `snapshot_receipt.json` | Hashes, counts, connection, disposition totals |

## Edge dispositions (db_rows_vs_yaml_edges.tsv)

| disposition | count | meaning |
|---|---:|---|
| `exact_match` | 0 | identical bytes in DB and YAML |
| `case_only_difference` | 9 | same edge; DB stores lowercase, YAML stores the canonical case |
| `db_only_legacy` | 3 | DB-only token on a removed or AOSP-hidden permission (WRITE_SMS, AUTHENTICATE_ACCOUNTS, MANAGE_ACCOUNTS) |
| `db_only_write_token` | 3 | DB-only write permission the v2 review removed from read/collection hypotheses |
| `technique_absent_from_yaml` | 1 | SEND_SMS → T1643; valid active technique, not yet reviewed in the YAML |
| `yaml_only` | 20 | YAML edges with no DB row |
| `strength_conflict` (flag) | 3 | DB `strong` where the YAML category is CONTEXT_REQUIRED (T1453, T1626.001, T1582 edges) |

`mapping_strength` is a property of the seeded relationship rows (an analyst weight on how directly a
permission relates to a technique). It is **not** behavioural evidence, not an observation confidence,
and must not be read as the strength of evidence that a sample performed a technique.
