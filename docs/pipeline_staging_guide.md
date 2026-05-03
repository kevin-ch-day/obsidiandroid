# Pipeline Staging Guide

This guide explains the refactored stage-based pipeline layout and how to extend it safely. Use this document when adding new stages, debugging runtime behavior, or reviewing performance changes.

## Why staging was introduced

Originally a single module handled orchestration and many stage internals, which made it hard to:

- reason about performance bottlenecks,
- unit test stage behavior in isolation,
- evolve one stage without risking unrelated sections.

Today **`analysis/pipeline/runner.py`** owns **`run_pipeline`** (stage sequencing); **`main.py`** is the CLI shell and test-stable import surface. Heavy logic stays in **`analysis/pipeline/stage_*.py`** modules.

## Current stage modules

| Stage module | Responsibility | Runner call site (`analysis/pipeline/runner.py`) |
| --- | --- | --- |
| `analysis/pipeline/stage_samples.py` | Cohort loading, gate checks, snapshot/lock controls, package integrity checks. | `load_and_prepare_samples(...)` |
| `analysis/pipeline/stage_av_vendor.py` | AV analysis execution, engine lifecycle integrity, vendor metadata extraction, feature-label alignment checks. | `run_av_analysis_stage(...)`, `extract_vendor_metadata_stage(...)`, `run_feature_alignment_stage(...)` |
| `analysis/pipeline/stage_feature_enrichment.py` | Optional metadata feature enrichment merge before vectorization. | `merge_sample_metadata_features(...)` |
| `analysis/pipeline/stage_modeling.py` | Engine weighting, feature vector build, training, and final label resolution helpers. | `compute_engine_weights_from_pipeline(...)`, `build_feature_matrix_stage(...)`, `run_training_stage(...)`, `resolve_final_labels_stage(...)` |
| `analysis/pipeline/stage_manifest.py` | Run manifest assembly/writing and lifecycle summary extraction. | `finalize_run_manifest_stage(...)` |
| `analysis/pipeline/stage_ablation.py` | Leakage-oriented ablation matrix builds, cohort gap exports, label-target stats. | `run_ablation_experiments(...)` (from `runner.py` when enabled) |
| `analysis/pipeline/sample_preparation.py` | Shared dataset filtering and metadata-feature helper functions reused by stages. | Imported by stage modules and compatibility wrappers |

## Observability (single truth layer)

- **Package:** `analysis/observability/` — use `analysis.observability.api` for `record_stage_start` / `record_data_population_change` / `record_artifact_write` / `record_partial_failure` instead of ad-hoc diagnostics CSVs.
- **Authoritative JSON:** `diagnostics/run_observability_summary.json` is produced during manifest output hygiene (`paths.run_observability_summary_json`). It consolidates pipeline status, paper/evidence flags, cohort row funnel, model headline, ablation snapshot, research warnings, and open-first artifact paths.
- **Human layers:** `pipeline_events.jsonl` (timeline), `pipeline_stage_summary.csv` / `.md`, `partial_failures.md`, `logging_audit.md` / `.csv`.
- **Alignment:** Terminal **Run Health** and `run_evidence_index.md` read the same summary fields so they do not contradict `run_summary.json` / hostile-audit outputs for static counts and verdicts.

## Compatibility layer

`main.py` re-exports **`run_pipeline`** and symbols that older tests monkeypatch (`finalize_run_manifest_stage`, `profile_manager`, `runtime_logging`, etc.). Implementations live in **`runner.py`**; **`analysis/pipeline/main_facade.py`** resolves patched attributes on `main` when orchestration runs outside `main.py`.

When adding new stage modules:

1. Add a stage helper under `analysis/pipeline/` and invoke it from **`runner.run_pipeline`** (not from `main.py`).
2. If tests must patch a callable, expose it on **`main`** for monkeypatch compatibility or patch `analysis.pipeline.stage_*` directly.
3. Prefer **`from utils.pipeline_entry import run_pipeline`** in new automation scripts (same implementation as `main.run_pipeline`).

## How to add a new stage

1. **Create a focused module** under `analysis/pipeline/` (for example `stage_export.py`).
2. **Use explicit inputs/outputs** (typed args + return values). Avoid hidden global state.
3. **Keep integrity checks near stage boundaries** and raise `ValueError` with clear messages.
4. **Return `None` for recoverable failure modes** only when the caller has explicit handling.
5. **Add targeted tests** in `tests/test_stage_<name>.py` for both success and failure paths.
6. **Wire into `analysis/pipeline/runner.py`** (`run_pipeline`) with clear “Step N” comments and `stop_after` support if applicable.

## Performance checklist for staged code

When touching stage modules, validate these patterns:

- Avoid DataFrame `iterrows()` in hot paths.
- Reuse normalized/cached column transformations instead of repeated `.astype(str).str.*` chains.
- Keep expensive DB calls inside stage modules and avoid duplicate round trips.
- Add small, deterministic tests around integrity checks to catch regressions early.

## Troubleshooting quick map

- Failure before `samples` stage: profile/load configuration issue.
- Failure in `av_pipeline`: likely DB AV matrix or engine lifecycle consistency issue.
- Failure in `vendor_metadata`: parser-map mismatch or metadata extraction contract issue.
- Failure in `feature_matrix`/`alignment`: feature merge schema mismatch or missing supervised label columns.
- Failure in `training`: model selection/config mismatch or invalid aligned dataset.

Use this map with run logs and diagnostics under `output/diagnostics` to localize issues quickly.
