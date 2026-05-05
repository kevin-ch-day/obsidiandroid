# Code Review: Architecture & Performance Opportunities

> **Note:** Snapshot from an earlier review cycle. Line counts and suggested splits describe historical layout before the **`analysis/pipeline/`** orchestration split and **`src/obsidiandroid/`** CLI migration; use **`analysis/pipeline/runner.py`** and **`docs/pipeline_staging_guide.md`** as the source of truth for current stages.

## Scope and approach

This review focused on:

- Module/file size and coupling hot spots.
- Obvious algorithmic performance risks in Python and SQL paths.
- Refactoring opportunities to break up large files and reduce complexity.

## High-priority refactor targets (break up first)

### 1) `main.py` (652 LOC) is doing orchestration + business logic + feature engineering

**Symptoms**
- Contains pipeline orchestration, cohort filtering, metadata feature construction, diagnostics, and manifest handling in one entry module.
- Very long `run_pipeline()` routine with many stages and branch exits.

**Impact**
- Hard to reason about failures and stage interactions.
- Harder unit testing (you need a broad environment to exercise many paths).

**Recommended split**
- `pipeline/orchestrator.py`: keep high-level stage sequence only.
- `pipeline/stages/*.py`: one file per stage (`samples`, `av_pipeline`, `vendor_metadata`, `weights`, `feature_matrix`, `training`).
- `pipeline/cohort_filters.py`: `_split_benign_malicious`, `_apply_dataset_filters`.
- `analysis/pipeline/sample_preparation.py`: `extract_vt_tag_count`, `build_metadata_feature_frame` (see also thin re-export `analysis/orchestration/metadata_features.py`).
- `pipeline/contracts.py`: typed dataclasses for stage inputs/outputs.

---

### 2) `database/db_sample_metadata_queries.py` (455 LOC) mixes query builders, wrappers, and multiple cohorts

**Symptoms**
- Multiple query pathways in one module (legacy banker cohort + generalized type cohort + utility loaders).
- `get_type_cohort_gate_stats()` runs several separate count queries over similar joins.

**Impact**
- More DB round trips than needed for readiness stats.
- Hard to optimize/index as a cohesive unit.

**Recommended split**
- `database/queries/sample_cohort_queries.py`: only SQL/query builder logic.
- `database/repositories/sample_cohort_repo.py`: adapter that returns DataFrames/domain objects.
- `database/queries/legacy_queries.py`: isolate legacy cohort helpers.

**Performance improvement**
- Replace repeated `_scalar()` count calls with one aggregate query using conditional sums (`SUM(CASE WHEN ... THEN 1 END)`), reducing query count.

---

### 3) `ml_classification/training/pipeline_core.py` (360 LOC) combines alignment, filtering, training loop, summarization, promotion

**Symptoms**
- One module responsible for too many ML lifecycle phases.
- Several broad try/except blocks swallow stage-specific failure details.

**Recommended split**
- `training/stages/data_prep.py` (align/prune/filter)
- `training/stages/train.py` (model training and skipped handling)
- `training/stages/report.py` (comparison, exports)
- `training/stages/promote.py` (output promotion)

## Key performance issues observed

### A) Row-wise parsing with `iterrows()` in parser execution path

- `analysis/execution/vendor_classification_processor.py` loops through every row with `iterrows()` and performs per-row object construction/parsing.

**Why this hurts**
- `iterrows()` is one of the slowest pandas iteration patterns.
- This is likely on a hot path for large AV matrices.

**Fix direction**
- Use `itertuples(index=False, name=None)` for faster row iteration.
- Pre-extract needed columns into arrays/lists and operate in plain Python loop.
- If parser functions allow, batch parse per vendor column (vectorized preprocess + selective row parse only where non-empty).

---

### B) Repeated heavy string conversions in parser coverage routines

- `analysis/evaluation/vendor_parser_utils.py` computes non-empty coverage using repeated `series.astype(str).str.strip()` transformations per column.

**Why this hurts**
- Repeating conversion/strip/lower per column multiplies work on wide matrices.

**Fix direction**
- Normalize once per column (or once for all object columns) and reuse cached cleaned series.
- Avoid recomputing the same cleaned string expression multiple times.

---

### C) Query executor always `fetchall()` for reads

- `database/db_engine.py` always fetches all rows into memory when `fetch=True`.

**Why this hurts**
- Large result sets cause memory spikes and delay first-row processing.

**Fix direction**
- Add streaming/chunked options (`fetchmany`, server-side cursors).
- Expose chunked dataframe iterator utilities for large exports/transformations.

---

### D) Multiple count queries for cohort gate stats

- `get_type_cohort_gate_stats()` executes multiple separate count statements with the same base joins.

**Why this hurts**
- Repeated scans/joins and extra round trips.

**Fix direction**
- Collapse into one aggregated query returning all counters at once.

---

### E) Canonicalization/scoring loops perform repeated per-column conversions

- In `analysis/pipeline/score_av_engines.py`, duplicate-resolution path repeatedly calls numeric coercion and coverage calculations per engine column.

**Why this hurts**
- Expensive on very wide matrices with many engine columns.

**Fix direction**
- Precompute per-column numeric sums and non-null counts once.
- Reuse cached metrics during canonical duplicate resolution.

## Additional maintainability recommendations

1. Introduce a typed run context object (dataclass) passed between stages instead of a mutable dict with ad hoc keys.
2. Replace catch-all `except Exception` where possible with targeted exceptions and stage-specific error types.
3. Add lightweight timing instrumentation per stage (e.g., context timer + structured log line).
4. Create performance regression tests around:
   - parser processing throughput,
   - cohort stat query latency,
   - feature matrix build time on representative dataset sizes.

## Suggested implementation order

1. Break up `main.py` into stage modules and orchestrator (highest impact for maintainability).
2. Optimize parser hot path (`iterrows` -> `itertuples` + cached string cleanup).
3. Collapse cohort gate stats to one aggregate SQL.
4. Add chunked DB fetch interface and adopt it in large-read paths.
5. Add timing + benchmark tests to prevent regressions.
