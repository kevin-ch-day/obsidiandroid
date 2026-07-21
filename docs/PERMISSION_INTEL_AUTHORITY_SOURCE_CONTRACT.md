# Permission Intel source contract (read-only inspection)

Durable documentation of Permission Intel surfaces used for post-run
protection-authority enrichment. Inspected with
`obsidiandroid_pipeline_reader` via `SELECT` / `information_schema` only.

## Connection identity

| Field | Value |
| --- | --- |
| Database user | `obsidiandroid_pipeline_reader@localhost` |
| Schema | `android_permission_intel` |
| Write operations | Forbidden |

## Tables

### `android_permission_authority_fact`

| Aspect | Detail |
| --- | --- |
| Role | Primary structured protection-level authority |
| Key | `authority_fact_id` (PK) |
| Canonical token | `permission_string_norm` (lookup); display `permission_string` |
| Protection level | `protection_level` (varchar; may be multi-flag `\|`-joined) |
| Namespace/source | `source_family_key`, `authority_source_type` |
| Active / accepted | `is_current_best = 1` plus `lifecycle_status`, `authority_confidence` |
| Review status | Not on this table; join `android_permission_review_state` |
| Alias relationship | Via `android_permission_token_alias` before lookup |
| Duplicate/conflict | Multiple `is_current_best=1` rows with distinct `protection_level` → explicit conflict; do not silently pick |
| Update timestamp | `updated_at_utc` |

### `android_permission_dict_aosp`

| Aspect | Detail |
| --- | --- |
| Role | AOSP dictionary fallback when authority fact lacks usable protection |
| Key | `constant_value` (PK) |
| Canonical token | `constant_value_norm` |
| Protection level | `protection_level` |
| Namespace/source | `source_family_key`, `authority_source_type` |
| Active | `lifecycle_status` |
| Update timestamp | `record_updated_at_utc` |

### `android_permission_dict_oem`

| Aspect | Detail |
| --- | --- |
| Role | OEM / vendor dictionary |
| Key | `permission_string` (PK) |
| Canonical token | `permission_string_norm` |
| Protection level | `protection_level` (often sparse) |
| Namespace/source | `vendor_id`, `classification_source` |
| Active / confidence | `confidence` enum |
| Update timestamp | `record_updated_at_utc` |

### `android_permission_token_alias`

| Aspect | Detail |
| --- | --- |
| Role | Raw → canonical token mapping |
| Key | `alias_id` |
| Fields | `raw_token_norm` → `canonical_token_norm`; `rule_version` |
| Update timestamp | `record_updated_at_utc` |

### `android_permission_review_state`

| Aspect | Detail |
| --- | --- |
| Role | Optional review / decision overlay |
| Key | `review_state_id` |
| Canonical token | `permission_string_norm` |
| Review status | `review_status`, `decision_type`, `reviewed_at_utc` |

### `android_permission_dict_unknown`

| Aspect | Detail |
| --- | --- |
| Role | Unknown / triage surface (non-authoritative for signature lanes) |
| Key | `permission_string` (PK); unique `permission_string_norm` |
| Fields | `triage_status`, `seen_count`, `notes` |
| Update timestamp | `record_updated_at_utc` |

## Google / platform surfaces

No dedicated Google dictionary table was present at inspection time.
Google-namespace classification continues from run-local
`pi_bucket_source` / `dangerous_bucket` when Permission Intel lacks a
structured row.

## Enrichment query policy

- Bound lookups to the frozen run token universe only (parameterized `IN` batches).
- Prefer `android_permission_authority_fact` where `is_current_best = 1`.
- Fall back to AOSP dict, then OEM dict.
- Never invent signature lanes without a structured `protection_level`.
- Conflicts remain `multiple_authority_conflict` / unresolved headline lane.

## Related contracts

- [`PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md`](PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md)
- [`PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](PERMISSION_GOVERNANCE_LANE_CONTRACT.md) (2.0.0 artifact-only; 2.1.0 enriched)
