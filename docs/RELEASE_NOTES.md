# ObsidianDroid v2.4.0 — Release Notes

**Release type:** live Android-malware research platform code-complete
**Not a publication-ready scientific paper-reproduction tag.**
**Core results persistence is not available in this release.**

## Summary

v2.4.0 packages the completed offline permission-research reporting stack for the
live corpus, freezes diagnostic evidence for run `20260721T231415Z__e0c43b`, and
adds:

- a versioned **permission capability-category** contract (orthogonal to protection lanes);
- an **observation-date temporal** contract with offline yearly trend reports;
- package-balanced / dominant-family / protection-lane / Permission Intel enrichment
  composers already landed on `main`.

Submitted papers remain frozen historical work. Do not treat diagnostic Macro-F1
figures as paper-reproduction claims.

## Diagnostic evidence freeze

| Field | Value |
| --- | --- |
| Profile | `android_malware_all_current` |
| Run ID | `20260721T231415Z__e0c43b` |
| Run git commit | `8b60754` |
| Immutable archive | `output/runs/_archived/completed/allcurrent_diagnostic/20260721T231415Z__e0c43b` |
| Offline reports | `output/runs/_offline_reports/20260721T231415Z__e0c43b` |
| Prepared samples | 9716 |
| Permission-signal-positive | 9457 |
| Governed / observed families | 206 / 207 |
| Governed / observed types | 14 / 15 |
| Training / held-out classes | 169 / 132 |
| Headline LR Macro-F1 / weighted F1 / accuracy | ≈0.698 / 0.944 / 0.945 |

Later taxonomy reactivation commits after `8b60754` are **not** part of this run’s
model evidence.

Frozen offline capability/temporal report packages were generated during the
release-candidate window. Final-tag composer hardening (archive write guards,
OEM-namespace ordering, CSV stub safety, temporal `pd.NA` handling) may differ
from the exact composer revision that wrote those packages; regenerate offline
reports only under a separate authorization if bit-identical refresh is required.

Graph inventory: [`docs/releases/2.4.0_OFFLINE_GRAPH_INDEX.md`](releases/2.4.0_OFFLINE_GRAPH_INDEX.md).

## What v2.4.0 ships

- Taxonomy count clarity (known vs observed; training vs held-out)
- Type-permission pattern, pairwise, type-guard, calibration, and family-context reports
- Dominant-family sensitivity and protection-level stratification
- Post-run Permission Intel enrichment and signature-aware analysis
- Package-balanced permission sensitivity stack
- CSV / reusable run-slot hygiene
- Core **incident and migration tooling** (apply/remediation remain deferred)
- Taxonomy reactivation **receipt packages** (historical; not a redesign campaign)
- Permission **capability categories** + offline reports/figures
- Temporal **observation-date** contract + offline yearly trends/figures
- Code-complete checklist: `docs/releases/2.4.0_CODE_COMPLETE_CHECKLIST.md`

## Capability categories

Contract version: `permission_capability_categories` **1.0.0**.

Categories are human-interpretable capability groups (SMS, overlay, location, …)
and are **independent** of Android protection / governance lanes. A token may
carry both dimensions. Multi-label capability assignment is allowed only via the
explicit map. Static declarations do **not** prove runtime behavior.

Generate (offline):

```bash
PYTHONPATH=src python scripts/diagnostics/generate_permission_capability_categories.py \
  --run-root output/runs/_archived/completed/allcurrent_diagnostic/20260721T231415Z__e0c43b
```

## Temporal reports

Contract version: `temporal_observation` **1.0.0**.

This is an **observation-date framework, not APK creation dating**.

Precedence when fields are present and parseable:

1. `first_seen_in_the_wild`
2. `first_discovered`
3. `first_analyzed` / VirusTotal first submission (default coverage proxy)

Original source fields are retained. Platform-event annotations are contextual
markers only; no causal Android-update claims.

On the frozen `e0c43b` offline package:

- ~94% of rows select first submission;
- ~6% select first-seen-in-the-wild;
- `first_discovered` is unavailable (100% missing);
- **2026 is a partial year**;
- annual trends reflect collection/source-batch composition, not global prevalence.

```bash
PYTHONPATH=src python scripts/diagnostics/generate_temporal_permission_trends.py \
  --run-root output/runs/_archived/completed/allcurrent_diagnostic/20260721T231415Z__e0c43b \
  --min-support 30
```

## Known limitations

- Diagnostic results are live-dataset research diagnostics, not paper locks
- ITW dates are sparse; first-discovered fields are typically absent in current artifacts
- App-defined / OEM tokens often land in `app_defined_unknown` / `oem_platform`
- Package identity is an accounting key, not malware lineage
- Reusable slot `output/runs/allcurrent_diagnostic` can be overwritten by a future run

## Explicitly deferred (not in v2.4.0)

- Core migration 0004 ledger repair; migration 0005; Core result grants
- Core results writer; enabling Core or legacy warehouse persistence
- Database restoration / desktop promotion / Mercury cutover acceptance
- Benign-versus-malware full benchmark; hierarchical classification
- Causal Android-update analysis; unrestricted three-way permission mining
- New taxonomy campaigns beyond already-receipted repairs

## Database compatibility

Normal analysis runtime remains:

- source databases: **read-only**
- `RESULTS_PERSISTENCE_MODE=read_only`
- `OBSIDIANDROID_CORE_PERSISTENCE_ENABLED=false`

Do not enable Core persistence for this release.

## Upgrade notes

1. Install / sync to this tag’s commit (or RC HEAD).
2. Prefer the immutable archived run for offline composers; archive before overwriting the reusable slot.
3. Report/schema contract versions are independent of the app version string.
4. Desktop migration and production DB restore are a separate workstream.

## Validation

```bash
git diff --check
python -m compileall -q src scripts tests
make doc-check
make verify
make ci-fast
./scripts/dev/run_tests.sh \
  tests/test_permission_capability_categories.py \
  tests/test_temporal_permission_trends.py \
  tests/test_package_balanced_permission_analysis.py \
  tests/test_package_balance_attribution.py \
  tests/test_enriched_package_family_sensitivity.py
python -m obsidiandroid.governance.taxonomy_repair_receipts governance/taxonomy_repairs
```

## Prior release

Historical platform-closure notes for **v2.2.0** remain relevant for canonical
profile slots and DL seed exports; see git history for `docs/RELEASE_NOTES.md`
at tag/era `v2.2.0`.
