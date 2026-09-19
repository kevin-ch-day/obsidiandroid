# Permission Intel v1 Query Inventory

Inventory version: `permission-intel-v1-query-inventory-1`

Audited legacy baseline: `b65d78993c417d1390062098f0b4e110d65bc224`

Integration and artifact-generation commit:
`15d6b738ee8df85b473a08306fa7259fb5a747e6`

Shared contract commit: `0cf71e18e43f33f5bd43ac442e88c4a423529236`

Accepted catalog release:
`android-17-r1-audit-2026-09-08-module-scope-expansion-3`

The baseline identifies the legacy query surface that was audited. It is not
the integration branch head. The machine inventory records the baseline,
integration, artifact-generation, shared-contract, catalog, and semantic
evidence identities separately. The catalog identity must match the runtime pin
in `obsidiandroid.database.permission_intel_v1.models`.

The machine-readable inventory is
[`tests/fixtures/permission_intel_v1_query_inventory.json`](../tests/fixtures/permission_intel_v1_query_inventory.json).
It records source symbols, SQL objects, selected fields, parameters, callers,
fallbacks, proposed v1 mappings, and inclusion decisions. Static report labels
and prose-only mentions are not executable queries and are excluded.

## Query families

| Family | Current surfaces | Pilot decision |
| --- | --- | --- |
| Platform reference | Legacy AOSP dictionary joins and run-scoped authority enrichment | Narrow v1 lookup included; existing paths unchanged |
| Platform provenance | Exact-join helpers and runtime reachability | v1 catalog gate/evidence/split reads included; live config audit unchanged |
| Observation | Feature building, trends, alignment gaps, cohort readiness, family debt | Excluded |
| VT enrichment | Banking-trojan mixed query | Excluded |
| OEM/vendor | Banking-trojan, feature, and authority-enrichment joins | Excluded |
| Analytical governance | Authority enrichment and workflow audit | Excluded |
| Signal taxonomy | 23-signal/54-mapping reads and seed path | Excluded and remains Obsidian-owned |
| Triage/workflow | Restore rehearsal and workflow lineage | Excluded |

## Dynamic SQL

Current runtime code still inspects whether observation rows expose
`permission_string_norm` for grouping keys, and it renders sample-ID
placeholder batches. Dictionary and authority-fact joins no longer discover
normalized columns at runtime; they use exact token-byte predicates. VirusTotal
current enrichment is joined uniquely by casefold, not exact bytes. Those
observation families are not compiled into the pilot. The v1 pilot uses fixed
versioned view names and parameterized permission values; it does not
dynamically discover a replacement authority. Accepted identities with no
protection columns withhold scalar protection and flags
(`WITHHELD_MISSING_PROTECTION`) instead of inventing a lane.

## Pilot scope

The new adapter reads accepted catalog metadata, canonical permission identity,
authority class, lifecycle, visibility, defining package, protection base and
all modifiers, flags, full API text, the separately typed SDK-extension release
ID, declaration provenance, and split relations from the deployed
`android_permission_v1_*` views. It does not query undeployed
`android_permission_v1_1_*` interpretation views, observations, VT enrichment,
OEM promotion, queues, signal writes, governance writes, or analytical
persistence.
