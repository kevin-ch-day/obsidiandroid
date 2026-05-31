# Cohort Census Report

## ZIP / source status

- The reviewed ZIP is stale relative to this active source tree.
- Active locked manuscript contract in source: `1226 / 39 / 6`.
- Archived rebaseline artifact still present: `20260526T021235Z__8b6966` (`1187 / 35 / 3` taxonomy note, archived only).

## Required answers

1. `1226 / 39 / 6` encoded in active source tree: **yes** (`malicious_temporal_stability_locked`, `paper2_primary_locked`, `20260504T044304Z__8c64e6/cohort_lock_manifest.json`).
2. `1187 / 35 / 3` still the active locked profile contract: **no**. That count survives only as an archived baseline note, not the active lock manifest.
3. Multiple lock concepts: **yes**. Manuscript-facing lock = `20260504T044304Z__8c64e6`; archived rebaseline = `/home/secadmin/Laughlin/GitHub/obsidiandroid/artifacts/baselines/20260526T021235Z__8b6966/MANIFEST.txt`.
4. Available now under exact profile semantics:
   - `malicious_temporal_stability_locked`: 1226 samples / 39 families / 6 types
   - `malicious_temporal_stability`: 1602 / 23 / 3
   - `malicious_temporal_stability_expanded`: 1815 / 38 / 4
   - `malicious_temporal_stability_long_tail`: 1954 / 60 / 7
   - `malicious_temporal_consensus10`: 1596 / 23 / 3
   - `malicious_temporal_family300`: 1420 / 23 / 3
5. Support-floor availability under exact semantics:
   - floor 20: 1602 samples / 23 families / 3 types
   - floor 10: 1815 samples / 38 families / 4 types
   - floor 5: 1954 samples / 60 families / 7 types
   - floor 1: 2061 samples / 111 families / 10 types
6. Permission observation required: **advisory only** for these profiles (`advisory_readiness_bucket`).
7. High/strong VT confidence required: **advisory only** for these profiles (`advisory_high_or_strong_readiness_bucket`).
8. Devixor/Gigabud in listed profiles: **excluded** via `cohort_gates.exclude_families`.
9. Devixor/Gigabud dominance if included under base current semantics: Devixor=709 (0.253), Gigabud=496 (0.177), combined=0.429.
10. Live samples eligible today but missing from the lock: **598**.
11. Locked samples failing current gates today: **222** total; time-window failures=39; top reasons={"below_min_samples_per_family": 183, "outside_time_window": 39}.
12. Defensible expanded cohort today: **yes, with caution** because the expansion delta is still highly concentrated in a small number of families/sources.
13. Best paper-expansion candidate today: **malicious_temporal_stability_expanded**. Rationale: best conservative expansion candidate: support floor 10 increases coverage beyond the standard floor-20 cohort without dropping to the long-tail floor 5.
14. Tables/figures needing regeneration if the paper cohort expands: all cohort-derived paper exports (`table1`-`table5`, `fig2`-`fig5`); `fig1_pipeline_architecture` is conceptual and does not need rerendering unless the workflow narrative changes.
15. Strict export gates fail today: **yes**. Missing/failed sources: ["paper_constants.json"]; paper_constants_present=False.

## Recommendation

- Do not rewrite the manuscript from counts discussion alone.
- Use this census bundle to choose between frozen `1226 / 39 / 6`, archived `1187`, or a new expanded cohort.
