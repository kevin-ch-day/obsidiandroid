# Taxonomy lifecycle repair — applied

**Status:** applied 2026-07-22 (Option A remaps). No type reactivations.

**Evidence export:** `output/diagnostics/taxonomy_active_family_inactive_type_gaps_latest.csv`  
**Generator:** `scripts/diagnostics/report_taxonomy_type_lifecycle_gaps.py`  
**Post-repair gap rows:** **0**

## Applied remaps

| family_id | family_slug | before type | after type | receipt |
|-----------|-------------|-------------|------------|---------|
| 80 | kuguo | retired `pua` (19) | active `adware` (3) | `governance/taxonomy_repairs/2026-07-22_kuguo-type-lifecycle/` |
| 85 | smsworm | retired `worm` (10) | active `sms-trojan` (14) | `governance/taxonomy_repairs/2026-07-22_smsworm-type-lifecycle/` |

Mappings and aliases were not modified. Sample-level attribution was not rewritten.

## Independent evidence used

- **Kuguo → adware:** Dr.Web Adware.Kuguo, AMD 2017 adware ground truth, SANER 2019 adware-family study; Microsoft PUA naming retained as identity support only.
- **SMSWorm → sms-trojan:** SecurityWeek SMS-worm reporting, F-Secure SMS-Worm category, Cyble SMSWorm write-up; local peer families already use `sms-trojan`.

## Related families reviewed (no DB change)

| family | current type | notes |
|--------|--------------|-------|
| Gigabud | active `banker` | Public sources describe RAT + banking credential theft; local banker placement retained. |
| SaferRat | active `banker` | Zimperium banking-trojan/RAT campaign; local banker placement retained. |
| SpyNote | active `rat` | Already correctly typed; no lifecycle gap. |

## Explicit non-actions

- No reactivation of retired `pua` / `worm` types.
- No Core writes; no grant/migration changes.
- No pipeline re-run; archived run evidence left untouched.
- No sample remapping or alias edits.
