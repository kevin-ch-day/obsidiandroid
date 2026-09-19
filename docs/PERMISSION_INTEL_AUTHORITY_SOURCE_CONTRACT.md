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
| Duplicate/conflict | Unique on `(permission_string_norm, authority_source_type, authority_url)`, not the token. Multiple `is_current_best=1` rows for one exact token are a conflict: do not join them into observation rows and do not silently pick. |
| Update timestamp | `updated_at_utc` |

### `android_permission_dict_aosp`

| Aspect | Detail |
| --- | --- |
| Role | Legacy invalid-token and provisional-seed guard only; not platform authority |
| Key | `constant_value` (PK) |
| Canonical token | `constant_value_norm` (index / display only; not the authority join) |
| Lookup | Exact token bytes (`BINARY constant_value`) only for `invalid_token` and provisional `queue_apply_shell` guards. Platform identity uses deployed v1 views. |
| Protection level | `protection_level` |
| Namespace/source | `source_family_key`, `authority_source_type` |
| Active | `lifecycle_status` |
| Update timestamp | `record_updated_at_utc` |

### `android_permission_dict_oem`

| Aspect | Detail |
| --- | --- |
| Role | OEM / vendor dictionary |
| Key | `permission_string` (PK) |
| Canonical token | `permission_string_norm` (index / display only; not the authority join) |
| Lookup | Exact token bytes (`BINARY permission_string`) and a resolved `vendor_id` |
| Protection level | `protection_level` (often sparse) |
| Namespace/source | `vendor_id`, `classification_source` |
| Active / confidence | `confidence` enum |
| Update timestamp | `record_updated_at_utc` |

Observation `vendor_id` is not the OEM lookup root. Live observations are
almost entirely NULL there, and OEM rows without a resolved `vendor_id` are
not authorized manufacturer matches. Do not join with
`OR observation.vendor_id IS NULL` or `OR oem.vendor_id IS NULL`.

### `android_permission_token_alias`

| Aspect | Detail |
| --- | --- |
| Role | Unique AOSP case recovery (`raw_token` → `canonical_token`) |
| Key | `alias_id` |
| Fields | Exact `raw_token` / `canonical_token`; generated `*_norm` is not identity |
| Live rule | `aosp_case_alias_v1` (lowercase observation/VT token to catalog bytes) |
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
- Prefer `android_permission_authority_fact` where `is_current_best = 1` and the exact token has exactly one authority-bearing fact (`permission_definition`, `removed_api`, or `provider_permission`). A leftover `custom_permission_pattern` row is not a second authority.
- Recover catalog identity through unique exact `android_permission_token_alias.raw_token` case aliases before joining v1 current permission.
- Join `android_permission_enrich_vt_current` uniquely by `LOWER(permission_string)`. Live VT rows are stored lowercased; exact-byte equality misses catalog-cased observations. Multiple VT rows for one casefold are a conflict: attach none.
- Attach non-permission and anomaly facts only when catalog identity is absent. Live anomaly rows include lowercase catalog tokens labeled `typo_variant`; those are case aliases, not malformed identities.
- Fall back to AOSP dict only for exact `invalid_token` / provisional-seed guards, then OEM dict by exact `permission_string` bytes plus resolved vendor.
- Never invent signature lanes without a structured `protection_level`.
- Conflicts remain `multiple_authority_conflict` / unresolved headline lane.

## Related contracts

- [`PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md`](PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md)
- [`PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](PERMISSION_GOVERNANCE_LANE_CONTRACT.md) (2.0.0 artifact-only; 2.1.0 enriched)
