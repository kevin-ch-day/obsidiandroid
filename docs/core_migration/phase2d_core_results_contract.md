# Phase 2D Core Results contract

## Ownership boundary

ObsidianDroid reads, but never writes, the two upstream source databases:

```text
erebus_threat_intel_prod  — samples, AV evidence, taxonomy, and source lineage
android_permission_intel  — permission observations and permission intelligence
```

`obsidiandroid_core_prod` is the application's sole write target. It owns
preserved run evidence, generated ML results, result contracts, predictions,
and references to immutable run artifacts. It is not a scratch database and
the retained Phase 2C fixture must not be cleared or overwritten.

## Current gap

The existing seven Core tables preserve a run, its source snapshot, sample
membership, and artifact lineage. They do not represent model executions,
metrics, feature/split contracts, predictions, ablation cells, or permission
and temporal result values.

The legacy `stage_results_warehouse` currently creates result tables at
runtime in Erebus. That behavior is transitional only: Phase 2D must replace
it with reviewed numbered Core migrations and a dedicated Core results writer.
No normal pipeline code may create tables at runtime.

## Core Results v1 tables

The first additive Core-results migration must provide these run-scoped
surfaces:

| Table | Purpose |
|---|---|
| `core_run_stage` | Stage status, timestamps, duration, and failure class. |
| `core_feature_contract` | Modality/feature contract identity, ordered-column hash, leakage status, and immutable artifact reference. |
| `core_split_ledger` | Per-sample split assignment and immutable split hash. |
| `core_model_execution` | Model identity, estimator/configuration hash, feature/split contract references, and promoted status. |
| `core_model_metric` | Scalar metrics for one model, split, and evaluation scope. |
| `core_prediction` | Held-out prediction ledger keyed by run, model, split, and sample. |
| `core_experiment` | Ablation or sensitivity experiment definition and status. |
| `core_experiment_metric` | Metrics for an experiment/model/split cell. |
| `core_permission_measure` | Run-scoped permission, family, type, and temporal measures with an explicit measure kind and dimensions. |
| `core_label_contract` | Label target, class universe, taxonomy version, and authority state. |
| `core_label_assignment` | Per-sample target/observed/resolved/predicted labels without an opaque JSON blob. |
| `core_confusion_cell` | Queryable true-label/predicted-label counts for each evaluated model and split. |

Existing `core_artifact` remains the registry for immutable CSV, JSON, model,
plot, and bundle files; result rows reference its role rather than duplicate
paths or hashes.

## Required safeguards

1. Every result row is tied to one `core_run` and, where applicable, the
   snapshot-backed sample membership.
2. A result writer has `INSERT`/narrow `SELECT` privileges only on reviewed
   Core result tables; it has no privilege on either source database.
3. The normal source reader has `SELECT` only on Erebus and Permission Intel;
   it has no Core privilege.
4. Core migrations are additive, numbered, and validated in a disposable
   schema before production application.
5. The pipeline must remain `read_only` until the Core writer, migration,
   write receipt, and fail-closed error policy are reviewed together.
6. Existing Erebus result tables remain historical read-only migration sources
   until a separate, receipted backfill decision is approved. They are not
   dropped as part of Phase 2D.

## Delivery order

1. Inventory the exact CSV/JSON contracts emitted by training, ablation,
   permission trends, and label resolution.
2. Implement and test the additive Core Results v1 migration.
3. Add a Core-only result writer and a `core` persistence mode that remains
   disabled by default.
4. Validate a synthetic run in a disposable Core schema, including rollback
   and artifact/hash reconciliation.
5. Apply the reviewed migration to production Core without modifying the
   preserved fixture.
6. Enable one separately approved nonpublication run with Core persistence.
7. Only after reconciliation, retire normal writes to the Erebus legacy
   warehouse and decide separately whether historical backfill is worthwhile.
