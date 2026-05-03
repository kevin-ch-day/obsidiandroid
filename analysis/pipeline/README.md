# Pipeline package (`analysis/pipeline`)

End-to-end staged workflow for cohort loading, AV/vendor processing, features, training, ablation, reporting, and manifest finalization.

| Module | Role |
| --- | --- |
| **`runner.py`** | **`run_pipeline`** — stage ordering, evidence/paper paths, timing, manifest hooks. Invoked from **`main.py`** and **`utils.pipeline_entry`**. |
| **`main_facade.py`** | Resolves monkeypatched symbols on **`main`** so tests can stub stages while orchestration lives in **`runner`**. |
| **`run_bounds.py`** | **`PipelineRunBounds`**: frozen snapshot of `run_id`, `diagnostics_dir`, run/output roots. Set from **`runner`** after profile load and evidence/paper path remapping; cleared in **`finally`**. |
| **`stage_*.py`** | Individual stages (`stage_samples`, `stage_av_vendor`, `stage_modeling`, `stage_manifest`, …). |
| **`manifest/`** | Manifest hashing, atomic writer, paper figures, **`paper_compliance_checks`**, runtime support helpers. |
| **`governance/`** | Integrity / path policy helpers. |
| **`runtime_policy.py`** | Profile-driven feature flags and config mutations for a run. |

Extension guide: [`docs/pipeline_staging_guide.md`](../../docs/pipeline_staging_guide.md).
