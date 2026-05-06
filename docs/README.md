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
| [`GOVERNANCE.md`](GOVERNANCE.md) | Mandatory governance behavior for runtime, diagnostics, and reproducibility. |
| [`AGENTS.md`](AGENTS.md) | Contributor and automated-agent conventions (layout, testing, hygiene); repo-root `AGENTS.md` is a pointer. |
| [`ROOT_AND_STRUCTURE_AUDIT.md`](ROOT_AND_STRUCTURE_AUDIT.md) | **Project status & deep root/layout audit** — hybrid layout rationale, what moved vs what stays, CI/professionalism checklist. |

## Quick Facts

- **Entry points:** Repo-root `main.py` is a thin shim; canonical CLI lives in `src/obsidiandroid/cli/main.py`. Canonical pipeline orchestration is `src/obsidiandroid/pipeline/runner.py` (legacy `analysis.pipeline.runner` is an identity shim) and stages still live under legacy `analysis/pipeline/stage_*.py` paths. Model tuning entrypoint: `python -m obsidiandroid.evaluation.model_tuning`. `scripts/` holds maintenance tools (`scripts/dev/` for hygiene/import checks, `scripts/diagnostics/` for inspection CLIs).
- **Configuration:** YAML/JSON files in `config/` control feature toggles, model parameters, and database credentials.
- **Outputs:** Runtime artifacts (labels, evaluation metrics, feature matrices) are written under an `output/` directory that is created on demand.
- **Testing:** Run **`make verify`** (import smoke + fast pytest), `pytest -q`, or `make test` before committing changes. The fuzzer and ML call-site scan live under `scripts/dev/`. See **Makefile quick reference** in `developer_guide.md` for `make setup`, `make menu`, and `make install-editable`.
- **VirusTotal data:** The pipeline consumes replicated VirusTotal tables (`vt_av_engines*`, `vt_permissions`, `vt_*_metadata`) from the project database rather than issuing live API calls. Integration specifics and required refresh cadences are captured in [`data_sources.md`](data_sources.md).

Consult the documents listed above for detailed component descriptions and operator workflows.
