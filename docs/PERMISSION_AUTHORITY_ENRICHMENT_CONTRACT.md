# Permission authority enrichment contract (post-run, read-only)

Offline + read-only Permission Intel enrichment for a **frozen completed run**.
This is a **post-run** authority observation, not a rewrite of run-time artifacts.

## Contract versions

| Field | Value |
| --- | --- |
| `permission_authority_enrichment_contract_version` | `1.0.0` |
| Enriched protection-lane contract | `2.1.0` |
| Artifact-only protection-lane baseline | `2.0.0` (unchanged) |

## Enrichment kind

```text
enrichment_kind: POST_RUN_READ_ONLY_AUTHORITY_ENRICHMENT
original_run_time_authority_frozen: false
source_run_artifacts: frozen
Permission Intel observation: current as of explicit UTC timestamp
```

## Database boundary

Reader: `obsidiandroid_pipeline_reader` only.

Allowed: `SELECT`, `SHOW`, `information_schema`.

Forbidden: any write/DDL/`CALL`/temporary tables/Core/admin credentials/Phase 2C reader.

## Source tables (Permission Intel)

| Table | Role |
| --- | --- |
| `android_permission_authority_fact` | Primary structured protection-level authority (`is_current_best=1`) |
| `android_permission_dict_aosp` | AOSP dictionary fallback (`constant_value_norm`) |
| `android_permission_dict_oem` | OEM dictionary (`permission_string_norm`) |
| `android_permission_token_alias` | Alias raw → canonical (`raw_token_norm` → `canonical_token_norm`) |
| `android_permission_review_state` | Optional review status join |
| `android_permission_dict_unknown` | Unknown-token triage surface (non-authoritative) |

No dedicated Google dictionary table is present; Google namespace continues from
run-local `pi_bucket_source` when PI lacks a structured row.

## Match statuses

| Status | Meaning |
| --- | --- |
| `exact_authority_match` | Current-best authority fact (or AOSP/OEM dict) matched |
| `alias_resolved` | Alias map used before authority lookup |
| `multiple_authority_conflict` | Conflicting accepted protection strings / multi-base parse |
| `app_defined` | Run or PI classifies as app-defined |
| `unknown` | Listed in unknown dict / no structured protection |
| `non_permission` | Explicit non-permission / package_defined-only without permission semantics |
| `unresolved` | No usable authority |

## Protection parsing

Preserve:

- `raw_protection_level`
- `base_protection_level`
- `protection_flags` (ordered, deterministic)
- `headline_lane`

Base candidates recognized for headline mapping: `normal`, `dangerous`,
`signature`. Additional tokens (`signatureOrSystem`, `internal`,
`package_defined`, …) are recorded; unknown bases stay unresolved unless a
documented mapping applies (`signatureOrSystem` → base `signature` + flag
`system`).

Flags such as `privileged`, `appop`, `setup`, `pre23` are **never** bases.

## Lane contract 2.1.0

Same headline lanes as 2.0.0, plus explicit match/conflict statuses.
Signature lanes populate **only** from structured authority evidence.

## Outputs

Under `diagnostics/permission_authority_enrichment/` and enriched protection
directories. Artifact-only `type_permission_protection/` remains the baseline.

## Source contract

Inspected table/column details:
[`PERMISSION_INTEL_AUTHORITY_SOURCE_CONTRACT.md`](PERMISSION_INTEL_AUTHORITY_SOURCE_CONTRACT.md).
