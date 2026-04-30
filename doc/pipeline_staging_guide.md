# Pipeline Staging Guide

This guide explains the refactored stage-based pipeline layout and how to extend it safely. Use this document when adding new stages, debugging runtime behavior, or reviewing performance changes.

## Why staging was introduced

The original `main.py` handled orchestration and most stage internals directly, which made it hard to:

- reason about performance bottlenecks,
- unit test stage behavior in isolation,
- evolve one stage without risking unrelated sections.

The staged design keeps `main.py` focused on high-level control flow and delegates heavy logic to `analysis/pipeline/stage_*.py` modules.

## Current stage modules

| Stage module | Responsibility | Main call site |
| --- | --- | --- |
| `analysis/pipeline/stage_samples.py` | Cohort loading, gate checks, snapshot/lock controls, package integrity checks. | `load_and_prepare_samples(...)` in `main.py` |
| `analysis/pipeline/stage_av_vendor.py` | AV analysis execution, engine lifecycle integrity, vendor metadata extraction, feature-label alignment checks. | `run_av_analysis_stage(...)`, `extract_vendor_metadata_stage(...)`, `run_feature_alignment_stage(...)` |
| `analysis/pipeline/stage_feature_enrichment.py` | Optional metadata feature enrichment merge before vectorization. | `merge_sample_metadata_features(...)` |
| `analysis/pipeline/stage_modeling.py` | Engine weighting, feature vector build, training, and final label resolution helpers. | `compute_engine_weights_from_pipeline(...)`, `build_feature_matrix_stage(...)`, `run_training_stage(...)`, `resolve_final_labels_stage(...)` |
| `analysis/pipeline/stage_manifest.py` | Run manifest assembly/writing and lifecycle summary extraction. | `finalize_run_manifest_stage(...)` |
| `analysis/pipeline/sample_preparation.py` | Shared dataset filtering and metadata-feature helper functions reused by stages. | Imported by stage modules and compatibility wrappers |

## Compatibility layer in `main.py`

`main.py` intentionally preserves wrapper functions (`compute_engine_weights`, `generate_feature_matrix`, `resolve_final_labels`) and underscore aliases (`_build_metadata_feature_frame`, etc.) so tests and older internal callers remain stable during migration.

When adding new stage modules:

1. Prefer adding a new stage helper and calling it from `main.py`.
2. Keep old helper names as wrappers if tests or downstream scripts still import them.
3. Add deprecation comments when wrappers are intended to be removed in a future release.

## How to add a new stage

1. **Create a focused module** under `analysis/pipeline/` (for example `stage_export.py`).
2. **Use explicit inputs/outputs** (typed args + return values). Avoid hidden global state.
3. **Keep integrity checks near stage boundaries** and raise `ValueError` with clear messages.
4. **Return `None` for recoverable failure modes** only when the caller has explicit handling.
5. **Add targeted tests** in `tests/test_stage_<name>.py` for both success and failure paths.
6. **Wire into `main.py`** with clear “Step N” comments and stop-after support if applicable.

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
