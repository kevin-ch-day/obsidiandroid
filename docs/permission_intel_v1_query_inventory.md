# Permission Intel v1 Query Inventory

Inventory version: `permission-intel-v1-query-inventory-1`
Audited/current commit: `b65d78993c417d1390062098f0b4e110d65bc224`

The machine-readable inventory is
[`tests/fixtures/permission_intel_v1_query_inventory.json`](../tests/fixtures/permission_intel_v1_query_inventory.json).
It records source symbols, SQL objects, selected fields, parameters, callers,
fallbacks, proposed v1 mappings, and inclusion decisions. Static report labels
and prose-only mentions are not executable queries and are excluded.

## Query families

| Family | Current surfaces | Pilot decision |
| --- | --- | --- |
| Platform reference | Legacy AOSP dictionary joins and run-scoped authority enrichment | Narrow v1 lookup included; existing paths unchanged |
| Platform provenance | Brownfield column discovery and runtime reachability | v1 catalog gate/evidence/split reads included; live config audit unchanged |
| Observation | Feature building, trends, alignment gaps, cohort readiness, family debt | Excluded |
| VT enrichment | Banking-trojan mixed query | Excluded |
| OEM/vendor | Banking-trojan, feature, and authority-enrichment joins | Excluded |
| Analytical governance | Authority enrichment and workflow audit | Excluded |
| Signal taxonomy | 23-signal/54-mapping reads and seed path | Excluded and remains Obsidian-owned |
| Triage/workflow | Restore rehearsal and workflow lineage | Excluded |

## Dynamic SQL

Current runtime code dynamically chooses normalized legacy join columns after
information-schema inspection and renders sample-ID placeholder batches. Those
query families mix observations or analytical state and are not compiled into
the pilot. The v1 pilot uses fixed versioned view names and parameterized
permission values; it does not dynamically discover a replacement authority.

## Pilot scope

The new adapter reads accepted catalog metadata, canonical permission identity,
authority class, lifecycle, visibility, defining package, protection base and
all modifiers, flags, full API text, the separately typed SDK-extension release
ID, declaration provenance, and split relations. It does not query observations,
VT enrichment, OEM promotion, queues, signal writes, governance writes, or
analytical persistence.
