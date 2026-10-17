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
| [`operations_playbook.md`](operations_playbook.md) | Runbooks and checklists for production support, monitoring, incident response, and change management. |
| [`GOVERNANCE.md`](GOVERNANCE.md) | Mandatory governance behavior for runtime, diagnostics, and reproducibility. |
| [`AGENTS.md`](AGENTS.md) | Contributor and automated-agent conventions (layout, testing, hygiene); repo-root `AGENTS.md` is a pointer. |
| [`ROOT_AND_STRUCTURE_AUDIT.md`](ROOT_AND_STRUCTURE_AUDIT.md) | **Project status & deep root/layout audit** — hybrid layout rationale, what moved vs what stays, CI/professionalism checklist. |
| [`STRUCTURE_MIGRATION_PLAN.md`](STRUCTURE_MIGRATION_PLAN.md) | Living migration/status ledger for canonical `src/obsidiandroid` relocation and shim retirement. |
| [`LABEL_AUTHORITY_ROLLOUT_RUNBOOK.md`](LABEL_AUTHORITY_ROLLOUT_RUNBOOK.md) | Operator workflow for label-authority rollout and validation. |
| [`LABEL_AUTHORITY_SCHEMA_PLAN.md`](LABEL_AUTHORITY_SCHEMA_PLAN.md) | Schema and view plan for label-authority adoption. |
| [`ML_BOUNDARY_PLAN.md`](ML_BOUNDARY_PLAN.md) | Boundary notes for ML pipeline responsibilities and future cleanup seams. |
| [`VENDOR_EVALUATION_BOUNDARY_PLAN.md`](VENDOR_EVALUATION_BOUNDARY_PLAN.md) | Boundary notes for vendor parsing, evaluation, and related contract cleanup. |
| [`module_split_audit.md`](module_split_audit.md) | Audit of large modules/functions and candidates for decomposition. |
| [`code_review.md`](code_review.md) | Historical engineering review notes that still inform migration and cleanup work. |
| [`PERMISSION_PATTERN_REPORT_PLAN.md`](PERMISSION_PATTERN_REPORT_PLAN.md) | Design plan for making permission-pattern analysis a first-class reporting lane across broad corpus, family benchmark, and type-level surfaces. |
| [`CANONICAL_RUN_CONTRACTS.md`](CANONICAL_RUN_CONTRACTS.md) | Final canonical scope boundary: permission-pattern contract, DB ownership, inference-vs-rebuild, and explicit later release deferrals. |
| [`OPERATIONAL_ASSESSMENT_V1.md`](OPERATIONAL_ASSESSMENT_V1.md) | Exact-SHA, revisioned operational assessment from existing evidence; distinct from model prediction and paper evaluation. |
| [`ASSESSMENT_HTTP_API.md`](ASSESSMENT_HTTP_API.md) | Read-only current/history HTTP adapter and its deployment boundary. |
| [`ANALYSIS_PERSISTENCE_V1.md`](ANALYSIS_PERSISTENCE_V1.md) | Downstream analysis persistence contract and activation boundaries. |
| [`runtime_source_connection_policy.md`](runtime_source_connection_policy.md) | Read-only upstream source defaults and persistence gates. |
| [`core_migration/README.md`](core_migration/README.md) | Core migration phases, historical checkpoints, and exact apply/review procedures. |

## Quick Facts

- **Entry points:** Repo-root `main.py` is a thin shim; canonical CLI lives in `src/obsidiandroid/cli/main.py`. **Pipeline orchestration** and all stage implementations (`stage_*`, AV/vendor chain, permission-trends report, manifest, …) live under **`src/obsidiandroid/pipeline/`**. Model tuning entrypoint: `python -m obsidiandroid.evaluation.model_tuning`. `scripts/` holds maintenance tools (`scripts/dev/` for hygiene/import checks, `scripts/diagnostics/` for inspection CLIs).
- **Configuration:** YAML/JSON files in `config/` control profiles and model settings. Database connections use private environment variables or approved client option files; credentials do not belong in tracked profile files.
- **Outputs:** Runtime artifacts (labels, evaluation metrics, feature matrices) are written under an `output/` directory that is created on demand.
- **Generated paper exports:** `paper_exports/docs/` holds generated runtime evidence such as cohort census reports. Regenerate these files when needed; do not treat checked-in copies as hand-maintained source of truth.
- **Testing:** Run **`make verify`** (import smoke + fast pytest), `pytest -q`, or `make test` before committing changes. `make ci-fast` adds documentation hygiene and the strict ML scan; `make ci` adds canonical closure. Relevant integration lanes run separately. See **Makefile quick reference** in `developer_guide.md`.
- **Upstream evidence:** The pipeline reads stored Erebus catalog and VirusTotal verdicts (including `virustotal_sample_vendor_engine_verdicts`) and live Permission Intel observations from their configured source schemas. It does not issue live VirusTotal API calls. Schema ownership and refresh assumptions are in [`data_sources.md`](data_sources.md).

Consult the documents listed above for detailed component descriptions and operator workflows.

The locked paper benchmark, current diagnostics, operational assessment
records, and Core persistence are separate evidence surfaces. A dated lock or
checkpoint is not a live database count or proof of independent paper
reproduction; verify its profile, run manifest, and source snapshot before
reusing a claim.

## PI V2 access and historical evidence

For current runtime access use [runtime_source_connection_policy.md](runtime_source_connection_policy.md).
The July `live_schema_preflight_report.md` and its CSV inventories, and
`PERMISSION_INTEL_AUTHORITY_SOURCE_CONTRACT.md`, retain historical inspection
facts. Their legacy schema shapes and joins are not instructions to restore
current PI reader privileges. Retain those reports for provenance; do not use
historical visibility as proof of current V2 acceptance.
