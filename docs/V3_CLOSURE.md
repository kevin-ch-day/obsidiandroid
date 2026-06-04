# ObsidianDroid V3 Closure Scope

ObsidianDroid V3 closes the current Android malware classification and
permission-pattern research platform phase. V3 is **not** the later deep-learning
system and does **not** absorb ScytaleDroid responsibilities.

## V3 scope

V3 positions ObsidianDroid as a governed, reproducible platform for:

- authority-aware Android malware cohort selection
- family/type benchmark classification
- permission-feature research and permission-pattern reporting
- manifest-backed run observability, evidence, and diagnostics

The V3 platform is intended to feed later Neptune / Iapetus work, not replace it.

## Database ownership boundary

ObsidianDroid stays **downstream** from upstream intelligence systems.

- **Erebus** remains the owner of Android sample catalog, VT-derived metadata, and
  family/type authority truth.
- **Permission Intel** remains the owner of live `android_permission_*` tables and
  permission-source governance metadata.
- **ObsidianDroid** may read from both systems and may persist its own
  run-scoped summaries, diagnostics, and research outputs in
  ObsidianDroid-owned tables.
- ObsidianDroid must **not** write back into Erebus source tables or mutate live
  Permission Intel source-of-truth tables.

This keeps V3 production-safe while still allowing later persistence and audit.

## Permission-pattern contract

V3 adopts a normalized 9-level permission-pattern ladder:

1. No Pattern Found
2. Conflicting Evidence
3. Inconclusive
4. Very Weak Pattern
5. Weak Pattern
6. Moderate Pattern
7. Strong Pattern
8. Very Strong Pattern
9. Exceptional Pattern

Existing permission-pattern outputs may now expose:

- `pattern_score`
- `pattern_level`
- `pattern_label`
- `pattern_basis`
- `pattern_confidence`
- `pattern_reason`

These fields normalize interpretation without replacing the underlying
prevalence/enrichment metrics.

## Inference mode vs rebuild mode

V3 treats these as design concepts even where the full inference-only path is not
yet a first-class CLI workflow.

- **Inference mode** means classifying newly added samples against a frozen
  baseline and frozen trained model without rebuilding the benchmark cohort.
- **Rebuild mode** means re-resolving the cohort, refreshing alignment, retraining,
  and emitting a new benchmark baseline.

V3 primarily implements rebuild mode plus locked-baseline reproducibility
controls. A dedicated frozen-model inference path is a follow-on capability.

## What moves to V4 or later

The following work is intentionally outside V3 closure:

- ScytaleDroid integration
- Iapetus / deep-learning model work
- full Android permission lifecycle and API-level temporal semantics
- broader cross-system persistence orchestration beyond run/result storage
- a full operator-grade frozen-model inference UX

V3 should close with truthful reporting, bounded operator surfaces, and stable
reproducibility, not a platform redesign.
