# ObsidianDroid Documentation

ObsidianDroid is an end-to-end framework for Android malware analysis, AV engine scoring, and machine learning classification that recommends probable malware family assignments per sample. This directory aggregates reference material for maintainers and analysts who need to understand, operate, or extend the system.

## Documentation Map

| Document | Purpose |
| --- | --- |
| [`architecture.md`](architecture.md) | Deep dive into the data flow, pipeline stages, and responsibilities of each package. |
| [`data_sources.md`](data_sources.md) | Database schema, VirusTotal replication strategy, and data refresh guardrails. |
| [`modeling_reference.md`](modeling_reference.md) | Catalog of supported classifiers, features, and evaluation artefacts. |
| [`user_guide.md`](user_guide.md) | Task-focused instructions for installing dependencies, configuring data sources, running jobs, and interpreting results. |
| [`developer_guide.md`](developer_guide.md) | Workflows for contributors: environment setup, branching strategy, testing expectations, and release procedures. |
| [`pipeline_staging_guide.md`](pipeline_staging_guide.md) | Stage-by-stage reference for the refactored pipeline modules and extension patterns. |
| [`../analysis/pipeline/README.md`](../analysis/pipeline/README.md) | Quick index of `runner.py`, `stage_*` modules, and `manifest/` helpers. |
| [`operations_playbook.md`](operations_playbook.md) | Runbooks and checklists for production support, monitoring, incident response, and change management. |

## Quick Facts

- **Entry points:** `main.py` is the CLI shell; `analysis/pipeline/runner.py` runs `run_pipeline` and calls staged helpers under `analysis/pipeline/stage_*.py`. `model_tuning.py` handles targeted hyperparameter sweeps; `scripts/` contains recurring maintenance utilities.
- **Configuration:** YAML/JSON files in `config/` control feature toggles, model parameters, and database credentials.
- **Outputs:** Runtime artifacts (labels, evaluation metrics, feature matrices) are written under an `output/` directory that is created on demand.
- **Testing:** Run `pytest -q` or `./run_tests.sh` before committing changes. Additional QA helpers (fuzzer, static scan) live under `devtools/`, separate from `tests/`.
- **VirusTotal data:** The pipeline consumes replicated VirusTotal tables (`vt_av_engines*`, `vt_permissions`, `vt_*_metadata`) from the project database rather than issuing live API calls. Integration specifics and required refresh cadences are captured in [`data_sources.md`](data_sources.md).

Consult the documents listed above for detailed component descriptions and operator workflows.
