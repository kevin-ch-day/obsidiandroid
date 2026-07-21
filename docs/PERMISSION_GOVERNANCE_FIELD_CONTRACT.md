# Permission governance field contract

Offline inventory of permission-governance fields available on completed-run
artifacts. Composers must not invent classifications when structured fields are
absent.

## Contract version

| Field | Value |
| --- | --- |
| `governance_field_contract_version` | `1.0.0` |
| Companion lane contract | `protection_lane_contract_version` `2.0.0` |

## Observed completed-run audit columns

Source: `diagnostics/permission_feature_audit.csv`

| Field | Present | Headline usable | Notes |
| --- | --- | --- | --- |
| `permission_string` | yes | yes | Join key |
| `pi_bucket_source` | yes | yes | AOSP / OEM / GOOGLE / APP_DEFINED / UNKNOWN |
| `dangerous_bucket` | yes | yes | normal / dangerous / google / oem_vendor / app_defined / unknown |
| `feature_column` | yes | yes | ML column linkage |
| `feature_group` | yes | limited | Capability grouping |
| `global_support` | yes | yes | Support gates |
| `max_family_support` | yes | limited | Concentration |
| `max_type_support` | yes | limited | Type concentration |
| `retained_after_pruning` | yes | yes | Feature-contract membership |
| `pruned_as_leakage` | yes | limited | Always `no` in current run |
| `base_protection_level` | **no** | no | Required for confirmed `aosp_signature*` |
| `protection_flags` | **no** | no | Required for privileged confirmation |
| alias / review / confidence | **no** | no | Do not invent |

## Ambiguity rule

When `base_protection_level` / `protection_flags` are absent, AOSP tokens with
non-normal/non-dangerous `dangerous_bucket` map to `unknown_unresolved`.
Do not claim confirmed signature or privileged lanes from name heuristics.

Generated live CSV: `permission_governance_field_contract.csv` under
`diagnostics/type_permission_protection/`.
