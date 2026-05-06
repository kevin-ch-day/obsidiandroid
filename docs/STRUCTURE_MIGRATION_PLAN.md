# ObsidianDroid structure migration plan

This document maps the current repository layout to the target `src/obsidiandroid/` domain layout.

## Developer import modes (verified)

Use one of the following so `import obsidiandroid` resolves to `src/obsidiandroid/`:

| Mode | How |
|------|-----|
| **Preferred** | From the repo root: `pip install -e .` (editable install registers the package; plain imports work in any cwd). |
| **Checkout without install** | `export PYTHONPATH="$PWD/src:$PYTHONPATH"` (or your shell equivalent). |
| **`./run.sh`** | Prepends `repo/src` to `PYTHONPATH` before launching Python so the startup menu works without an editable install. |
| **pytest** | `tests/conftest.py` prepends `repo/src` to `sys.path` so tests see `obsidiandroid` even without editable install. |

Quick verification: `python scripts/dev/check_import_surface.py` or `make dev-import-check`.

---

## Status labels

| Status | Meaning |
|--------|---------|
| **moved_now** | Canonical code now lives under `src/obsidiandroid/...` in this pass. |
| **wrapper_kept** | Thin compatibility module at the old import path re-exports or bootstraps the new location. |
| **move_later** | Intended home is known; no move in this pass. |
| **delete_later** | Remove after callers migrate (often paired with a former shim). |
| **needs_review** | Boundary or ownership unclear; decide before moving. |

### Snapshot — current truth (update when passes land)

- **Canonical code** under **`src/obsidiandroid/`** includes **CLI**, **common** (hashing, paths, exports, hygiene, …), **governance** (compliance, manifest, cohort, artifacts, …), **reporting** (notably **`export_manager`** and related exporters), **observability** (**`logging/`** + **`pipeline_observability`**), **`pipeline`** façade: **`run_pipeline`**, every stage module **`runner`** imports directly (**Pass 70**), **`sample_preparation`**, **`sample_exports`**, **`main_facade`**, and policy leaves — each with legacy **`analysis.pipeline.*`** shims where moved (**Passes 66–70**); **`runner`** imports **`reset_runtime_training_caches`** from **`obsidiandroid.modeling.model_trainer_factory`** (**Pass 77**); vendor/feature-engineering helpers live under **`obsidiandroid.feature_engineering`** (**Pass 78**); pipeline orchestration surface (**permission features**, **`runtime_reporting`**, methodology exports, profile filters, metadata shim) lives under **`obsidiandroid.orchestration`**, and AV binary-matrix / enrichment under **`obsidiandroid.matrix`** (**Pass 80**). **diagnostics** under **`obsidiandroid.diagnostics`** (**`research_validity/`**, **`hostile_audit/`**, and leaf run diagnostics modules; Pass **65**; legacy **`analysis.diagnostics`** is package-only registration + identity — Pass **36** façade mirroring superseded), **database** façade → **`obsidiandroid.database`** re-exports curated **`database.*`** modules (Pass 38; implementation stays repo-root **`database/`**), **modeling** (**`model_exporter`**, **`distribution_reporter`**, **`feature_label_alignment_helper`**), **evaluation** implementation under **`obsidiandroid.evaluation`** (Pass 63; legacy **`analysis.evaluation`** is package-only registration + identity), **vendor parsing** under **`obsidiandroid.vendors.parsing`** (Pass 59 + legacy shim), **vendor contracts** under **`obsidiandroid.vendors.contracts`** (including record diagnostics / metadata normalization helper closure in **Pass 84**), and **vendor execution** (parser runtime) under **`obsidiandroid.vendors.execution`** (Pass 64; legacy **`analysis.execution`** is package-only registration + identity). **`obsidiandroid.risk_band`** owns risk-band assignment plus config (**Passes 81, 84**). **`obsidiandroid.labeling.malware_family_constants`** owns malware-family taxonomy constants/helpers with legacy **`ml_classification.common.malware_family_constants`** as an identity shim (**Pass 85**), **`obsidiandroid.labeling.classification_label_resolver`** owns the stable resolver entrypoint with legacy shim (**Pass 86**), while **`obsidiandroid.labeling.taxonomy`** remains the function-level wrapper for public normalization use. **`obsidiandroid.features.vectorization`** holds the four vectorization modules physically (**Pass 83**); **`obsidiandroid.features`** façade re-exports them; legacy **`ml_classification.vectorization.*`** remains valid via thin shims + package **`sys.modules`** registration (**Pass 83**). Repo-root **`ml_classification/`** leaf **`.py`** files are **thin shims** only; after **Pass 100**, each legacy subpackage (**`builder`**, **`inference`**, **`engine_weights`**, **`labeling`**, **`reporting`**, **`vectorization`**, **`training`**, **`training.ml_trainers`**) exposes its known submodule names via lazy **`__getattr__`** (aligned with **`common`** / **`ml_utils`** — **Pass 99**). Remaining sizable moves under **`obsidiandroid.*`** are optional doc/caller cleanups; ML implementation under repo-root **`ml_classification/**`** is not present beyond shims and these package facades.
- **Dev tooling (Pass 101):** Repo-root thin wrappers **`run_tests.sh`**, **`run_tests_full.sh`**, **`clean_bytecode_cache.py`**, and **`run_ml_static_scan.py`** were removed; use **`make test`** / **`./scripts/dev/run_tests.sh`**, **`make ml-scan`** / **`python -m scripts.dev.run_ml_static_scan`**, **`python scripts/dev/clean_bytecode_cache.py`** / **`make clean-bytecode`**. **`pyproject.toml`** **`py-modules`** lists **`main`** only.
- **CLI shell (Pass 103):** Repo-root **`main.py`** bootstraps checkout installs with **`import utils`** only ( **`utils.__init__`** pulls in **`repo_import_paths`**); no direct import of **`ensure_repo_src_on_sys_path`** from **`utils.repo_import_paths`**.
- **Legacy trees** at the repo root (**`analysis/`**, **`database/`**, **`ml_classification/`**, **`model/`**, **`utils/`**) stay for compatibility and bulk of implementation; **`utils/`** is primarily **shims** plus package **`__init__.py`** that imports **`repo_import_paths`** once (**Pass 102** — leaf modules no longer duplicate **`import utils.repo_import_paths`**), **`export_manager`** (**`sys.modules`** alias), and entry wrappers (**`startup_menu`**, **`pipeline_entry`**). In-repo scripts and tests should prefer the canonical bootstrap `obsidiandroid.common.repo_paths.ensure_repo_src_on_sys_path`.
- **Removed (Pass 33):** the **`analysis/observability`** package — pipeline observability APIs live only under **`obsidiandroid.observability.pipeline_observability`**.
- **Quality gates:** **`make ci`** runs doc hygiene, **`scripts/dev/check_import_surface.py`** (imports, thin-shim rules for **`utils/`** subtrees, UTF-8 BOM scan), fast pytest, and strict ML static scan.

### How to read this document (maintenance, 2026-05)

- **Living sections** (use these for decisions): **Status labels**, **Snapshot — current truth**, **Restructure backlog (living)**, **Locked migration policy**, and **Intended future moves** (below).
- **Historical sections:** The per-pass tables (**Pass 1**, **Pass 2**, …) are an **archive** of what shipped on each pass. They are **not** retro-edited when later passes supersede them. If an old pass table disagrees with the **Snapshot**, trust the **Snapshot**.
- **Stale detail in archives:** Early pass sections may cite **old pytest counts** or paths that have since moved; treat those as **time capsules**, not current CI facts. Today’s gate is **`make ci`** (import surface + fast pytest + strict ML scan).
- **Vendor / evaluation nuance:** Physical modules for vendor parsers, evaluation glue, vendor execution, and run diagnostics now live under **`src/obsidiandroid/`** (Passes **59**, **63**, **64**, **65**); several **`analysis/*`** trees are **package-only shims**. See **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`** for boundary and **wrapper** work still open.

### Restructure backlog (living)

| Priority | Item | Status |
|----------|------|--------|
| P0 | **`obsidiandroid.database`** thin façade + outer callers (no **`database/*.py`** internal churn) | **Done** through **Pass 43** (Tiers **A–D** narrow AV set on façade). |
| P1 | **`README.md`** operator quickstart: **`pip install -e .`**, **`obsidiandroid`**, canonical vs legacy imports | **Partial** — layout + DB façade pointers added (**Pass 43**); deepen if operators need full command cookbook |
| P1 | **`analysis/pipeline`** (and adjacent **core** **`analysis/**`**) physical move under **`src/`** (keep legacy shims) | **Partial** — Passes **66–71**, **74–76**, **78**, **80**, **81**: runner-linked pipeline, **`feature_engineering`**, **`orchestration`**, **`matrix`**, **`risk_band`** under **`obsidiandroid.*`**; matching **`analysis/*`** dirs hold thin shims. **Next high-ROI slice:** deepen **ML** façades, or widen **`obsidiandroid.database`**. |
| P2 | **`obsidiandroid.diagnostics`** vs **`analysis.diagnostics`** tree | **Done** (**Pass 65**) — implementations under **`src/obsidiandroid/diagnostics/`**; **`analysis/diagnostics/__init__.py`** identity shim only |
| P2 | **`ml_classification/`** → **`obsidiandroid.modeling` / `features` / `labeling`** façades + **wrappers** where needed | **Largely done** — Through **Pass 100**: leaf shims + lazy subpackage **`__getattr__`** for **`builder`**, **`inference`**, **`engine_weights`**, **`labeling`**, **`reporting`**, **`vectorization`**, **`training`**, **`training.ml_trainers`** (plus **Pass 99** **`common`** / **`ml_utils`**). New code should use **`obsidiandroid.*`** only. |
| P2 | **`ml_classification.common`** malware-family constants | **Done** (**Pass 85**) — implementation now **`obsidiandroid.labeling.malware_family_constants`**; legacy **`ml_classification.common.malware_family_constants`** is an identity shim; public callers should still prefer wrapper functions from **`obsidiandroid.labeling.taxonomy`** unless raw taxonomy tables are explicitly needed |
| P2 | Vendor / evaluation domain boundary (**`obsidiandroid.vendors`**, **`obsidiandroid.evaluation`**) | **Partial** — Pass **50B** inventory/spec, Pass **51** parser-map alias, Pass **58** execution roadmap, Pass **59** physical parser move to **`obsidiandroid.vendors.parsing`** with legacy identity shim; Pass **63** evaluation implementations **`obsidiandroid.evaluation`**; Pass **64** vendor execution (**`analysis/execution/*`** → **`obsidiandroid.vendors.execution`**) with legacy shim |
| P2 | Remaining **`model/*`** helper imports from canonical code | **Done** (**Pass 84**) — **`model.core.risk_band_config`** → **`obsidiandroid.risk_band.risk_band_config`**; **`model.core.record_diagnostics`** and **`model.utils.metadata_normalizer`** → **`obsidiandroid.vendors.contracts`**; legacy **`model.*`** paths are identity shims |
| P3 | Retire **`utils/*`** shims after caller + doc sunset | **Pending** — locked policy milestone (Pass 44 cleared **`tests/`** stragglers that were not asserting shim parity); **Pass 72** removed empty **`utils/menu`** / **`utils/ui`** stub packages; **Pass 73** removed dead **`analysis/pipeline/runtime/`** (**`RunContext`**) |
| P3 | Repo-root **`run_tests*.sh`**, bytecode-clean, ML-scan shims | **Done** — **Pass 101** removed thin wrappers; **`make`** / **`scripts/dev/*`** / **`python -m scripts.dev.run_ml_static_scan`** are canonical |
| P3 | Remaining **`database.db_*`** not on façade (e.g. **`db_sample_timelines_queries`**, **`db_extract_av_label_keywords`**) — add only when call sites need canonical imports | **Optional** |
- **Passes 41–43 (`obsidiandroid.database`):** Façade-only **`from database`** callers outside **`database/`** are migrated (Pass 41); **Pass 42** recorded the pre–Tier D audit; **Pass 43** expands the façade with four **Tier D** AV/scoring modules and migrates remaining outer callers (**`analysis/`**, tests, **`obsidiandroid.governance.run_manifest`**). **`database/*.py`** internal imports stay **`from database …`**.
- **Pass 44 (tests → canonical CLI):** Selected **`tests/`** modules import **`obsidiandroid.cli.menu` / `obsidiandroid.cli.ui.menu`** instead of **`utils.menu` / `utils.ui`** (legacy stub packages **removed** in **Pass 72** once unused).
- **Pass 45 (`obsidiandroid.pipeline` module aliases):** façade now lazily re-exports common **`analysis.pipeline.*`** modules (stages, scoring helpers, runner/main_facade), and tests moved to **`from obsidiandroid.pipeline import ...`** where safe.
- **Pass 46 (ML boundary inventory/spec):** docs-first import inventory + readiness tags completed in **`docs/ML_BOUNDARY_PLAN.md`**; no code moves, no caller migrations.
- **Pass 47 (first ML facade slice):** only Pass 46 **`ready_now`** aliases surfaced under **`obsidiandroid.modeling`**, **`obsidiandroid.features`**, and **`obsidiandroid.labeling`** with identity checks; no caller migration.
- **Pass 48 (low-risk ML caller adoption):** small outer-caller batch migrated to Pass 47 aliases (tests + canonical CLI + selected pipeline stages), with mixed/deferred rows intentionally skipped.
- **Pass 49 (post-Pass 48 audit):** legacy import counts and focused remaining-surface scans recorded; recommends **Pass 50A** second low-risk ML adoption batch.
- **Pass 50A (second low-risk ML adoption):** two evaluation helpers and four tests migrated to already-surfaced ML aliases; mixed/internal-only files remain skipped.
- **Pass 50B (vendor/evaluation boundary inventory):** docs-only boundary map completed in **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`**; only one clear vendor `ready_now` row found, evaluation remains deferred pending wrapper/spec work.
- **Pass 51 (first vendor facade slice):** **`obsidiandroid.vendors.vendor_parser_map`** now aliases **`analysis.vendor_processing.vendor_parser_map`** with identity checks; one diagnostics script and parser-map tests use the canonical path.
- **Pass 52 (pipeline facade adoption):** **`obsidiandroid.pipeline`** exposes three more top-level modules (**`sample_exports`**, **`sample_preparation`**, **`stage_results_warehouse`**) and a small outer-caller batch moved to canonical module imports.
- **Pass 53 (utils non-parity test cleanup):** remaining behavior tests that used **`utils.export_manager`** / **`utils.family_distribution_report`** now import canonical **`obsidiandroid.reporting`** modules; only shim/parity and entry-shim tests remain on **`utils.*`**.
- **Pass 54 (pipeline governance aliases):** stable run-integrity primitives now surface through **`obsidiandroid.governance.exceptions`** and **`obsidiandroid.governance.integrity`**; direct outer callers migrated.
- **Pass 55 (pipeline policy/helper aliases):** **`obsidiandroid.pipeline`** now exposes stable top-level helpers (**`contract_filters`**, **`run_bounds`**, **`runtime_policy`**) and corresponding tests use canonical imports.
- **Pass 56 (pipeline manifest subfacade):** **`obsidiandroid.pipeline.manifest`** now aliases stable manifest helper modules (**hashing**, **writer**, **runtime_support**, **paper_compliance_checks**, **paper_figure_renderers**) and manifest tests/stage imports use canonical paths.
- **Pass 57 (pipeline nested helper subfacades):** **`obsidiandroid.pipeline.artifacts`** and **`obsidiandroid.pipeline.permission_trends`** alias stable nested helper modules; their direct tests use canonical imports.
- **Pass 58 (ML taxonomy wrapper + vendor/eval execution roadmap):** **`obsidiandroid.labeling.taxonomy`** delegates three family helpers with an explicit **non-alias** wrapper contract; **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`** gains an ordered execution table (vendors vs evaluation vs internal vs reporting vs defer). No physical **`analysis/pipeline`** move; database policy unchanged.
- **Pass 59 (physical vendor parser move):** parser modules moved from **`analysis/vendor_processing`** to **`src/obsidiandroid/vendors/parsing`**. A legacy **`analysis.vendor_processing`** package shim registers module identities via **`sys.modules`** so legacy and canonical imports resolve to the same module objects. No parser behavior changes; **`model.vendor`**/**`model.parsing`** remain deferred.
- **Pass 63 (evaluation physical canonicalization):** vendor AV evaluation/scoring/parser glue modules previously under **`analysis/evaluation/*.py`** now live under **`src/obsidiandroid/evaluation/`**. **`analysis/evaluation/`** retains only **`__init__.py`**, which registers **`sys.modules['analysis.evaluation.<name>']`** to the canonical modules (same **`ModuleType`** objects). Selected callers (startup menu, pipeline stages, execution, diagnostics export wiring test) import **`obsidiandroid.evaluation`**; parity tests may keep **`analysis.evaluation`**. **`model_tuning`** no longer mutates **`sys.path`** from package code. No pipeline runner move, no parser/scoring behavior changes.
- **Pass 64 (vendor execution physical canonicalization):** vendor parser runtime modules moved from **`analysis/execution/*.py`** to **`src/obsidiandroid/vendors/execution/`**. Legacy **`analysis.execution.<name>`** imports remain valid via **`analysis/execution/__init__.py`**, which registers submodules in **`sys.modules`** for identity. Canonical callers now import **`obsidiandroid.vendors.execution`** (including the evaluation parser entrypoint and determinism tests). No parser/scoring behavior changes.
- **Pass 65 (diagnostics physical canonicalization):** run diagnostics (**`research_validity/`**, **`hostile_audit/`**, and leaf diagnostics modules) moved from **`analysis/diagnostics/`** into **`src/obsidiandroid/diagnostics/`**. Legacy **`analysis.diagnostics.<name>`** imports remain valid via **`analysis/diagnostics/__init__.py`**, registering the same **`ModuleType`** objects. **`finalize.py`** and import-surface checks use canonical paths where updated; **`output_artifact_policy`** producer strings use **`obsidiandroid.diagnostics.*`** for diagnostics-owned emitters.
- **Pass 66 (pipeline policy leaf physical slice):** **`contract_filters`**, **`run_bounds`**, and **`runtime_policy`** implementations live under **`src/obsidiandroid/pipeline/`**. Legacy **`analysis/pipeline/<name>.py`** files are thin shims that replace **`sys.modules[__name__]`** with the canonical module object. **`stage_*`** modules remain under **`analysis/pipeline/`**; the **`obsidiandroid.pipeline`** façade re-exports them via **`analysis.pipeline.<name>`** until moved. **`check_import_surface`** asserts legacy/canonical **`ModuleType`** identity for the moved leaves.
- **Pass 67 (pipeline runner physical slice):** **`run_pipeline`** and orchestration helpers live under **`src/obsidiandroid/pipeline/runner.py`**. Legacy **`analysis/pipeline/runner.py`** is a thin shim (same pattern as Pass 66 leaves). **`obsidiandroid.pipeline`** façade treats **`runner`** as a physical submodule; **`check_import_surface`** asserts **`analysis.pipeline.runner`** and **`obsidiandroid.pipeline.runner`** are the same **`ModuleType`**. Stage modules remain under **`analysis/pipeline/`** for now.
- **Pass 68 (pipeline main_facade + stage_samples):** **`main_facade`** ( **`from_main_or`** ) and **`stage_samples`** ( **`load_and_prepare_samples`** ) live under **`src/obsidiandroid/pipeline/`**; legacy **`analysis/pipeline/*.py`** are shims. Canonical **`runner`** imports these from **`obsidiandroid.pipeline`**. Remaining **`stage_*`** modules stay under **`analysis/pipeline/`** until a later pass.
- **Pass 69 (pipeline sample_exports + stage_av_vendor + stage_manifest):** Cohort export helpers (**`sample_exports`**), AV/vendor/alignment stage (**`stage_av_vendor`**), and manifest finalization (**`stage_manifest`**, large) are canonical under **`src/obsidiandroid/pipeline/`** with legacy shims. **`stage_samples`** imports **`sample_exports`** from the canonical package; **`runner`** imports the moved stages from **`obsidiandroid.pipeline`**.
- **Pass 70 (pipeline remaining runner stages):** **`sample_preparation`**, **`stage_feature_enrichment`**, **`stage_modeling`**, **`stage_ablation`**, **`stage_results_warehouse`**, and **`stage_permission_trends_report`** are canonical under **`src/obsidiandroid/pipeline/`**; **`runner`** imports them from **`obsidiandroid.pipeline`**. **`stage_feature_enrichment`** uses canonical **`sample_preparation`**; **`stage_permission_trends_report`** uses canonical **`stage_results_warehouse`**. Remaining under **`analysis/pipeline/`** include **`governance/`** integrity import in **`runner`**, **`av_engine_pipeline`**, **`vendor_metadata_pipeline`**, **`permission_trends_selection`**, **`permission_trends/`** package, and related helpers (**`engine_normalization`**, **`score_av_engines`**, etc.).
- **Pass 71 (AV engine + vendor metadata pipeline chain):** **`engine_pipeline_utils`**, **`attach_engine_metadata`**, **`engine_normalization`** (repo-root **`config/engine_aliases.yaml`** via **`Path(__file__).resolve().parents[3]`**), **`score_av_engines`**, **`av_engine_pipeline`**, and **`vendor_metadata_pipeline`** are canonical under **`src/obsidiandroid/pipeline/`** with legacy shims. **`stage_av_vendor`** imports **`av_engine_pipeline`** / **`vendor_metadata_pipeline`** from **`obsidiandroid.pipeline`**. **`runner`** and **`manifest/runtime_support`** import **`enforce_run_scoped_artifact_paths`** from **`obsidiandroid.governance.integrity`** (same module object as **`analysis.pipeline.governance.integrity`** via existing governance registration).
- **Pass 72 (prune empty utils CLI stubs):** Removed **`utils/menu/`** and **`utils/ui/`** (docstring-only **`__init__.py`** packages with no leaf shims and no in-repo **`import utils.menu` / `utils.ui`**). Console UI remains **`obsidiandroid.cli.menu`** / **`obsidiandroid.cli.ui`**; **`utils/display_utils.py`** stays the thin re-export for **`obsidiandroid.cli.ui.display`**. **`check_import_surface`** no longer enforces policies on the deleted directories.
- **Pass 73 (remove unused pipeline runtime stub):** Deleted **`analysis/pipeline/runtime/`** (**`RunContext`** dataclass only). Nothing in the repo imported **`analysis.pipeline.runtime`** or **`RunContext`**; pipeline run-scoped state remains **`runtime_policy`**, **`run_bounds`**, and **`app_config`** globals as today.
- **Pass 74 (permission trends helpers physical slice):** **`permission_trends/`** leaf modules (**`bundle_manifest`**, **`constants`**, **`publish_paths`**, **`reporting_support`**, **`sample_permission_data`**, **`stats_core`**) and **`permission_trends_selection`** are canonical under **`src/obsidiandroid/pipeline/`**; **`analysis/pipeline/permission_trends/*.py`** and **`analysis/pipeline/permission_trends_selection.py`** are thin identity shims. **`obsidiandroid.pipeline.permission_trends`** façade imports canonical modules; **`check_import_surface`** asserts legacy **`analysis.pipeline.permission_trends.*`** matches canonical **`ModuleType`** objects.
- **Pass 75 (pipeline governance physical slice):** **`exceptions`**, **`integrity`**, **`policy`**, and **`readiness`** are canonical under **`src/obsidiandroid/governance/`**. **`obsidiandroid.governance`** package **`__init__.py`** registers all submodules from **`src`** (no **`analysis.pipeline.governance`** hop for façade contents). **`analysis/pipeline/governance/*.py`** are thin identity shims; package **`__init__.py`** re-exports exception classes from canonical **`obsidiandroid.governance.exceptions`**.
- **Pass 76 (pipeline manifest + artifacts physical slice):** **`hashing`**, **`writer`**, **`runtime_support`**, **`paper_compliance_checks`**, **`paper_figure_renderers`**, **`builder`**, and **`schema`** live under **`src/obsidiandroid/pipeline/manifest/`**; **`paths`** and **`registry`** under **`src/obsidiandroid/pipeline/artifacts/`**. **`analysis/pipeline/manifest/*.py`** and **`analysis/pipeline/artifacts/*.py`** are thin identity shims (same **`ModuleType`** as canonical). **`obsidiandroid.pipeline.manifest`** / **`.artifacts`** package **`__init__`** re-exports submodules; **`check_import_surface`** asserts legacy shims match canonical modules.
- **Pass 77 (ML façade adoption slice):** **`obsidiandroid.pipeline.runner`** imports **`reset_runtime_training_caches`** from **`obsidiandroid.modeling.model_trainer_factory`** (same **`ModuleType`** as **`ml_classification.training.model_trainer_factory`**). **`output_artifact_policy`** producer strings for split-freeze, vendor-gate debug, saved models, and confusion matrices use **`obsidiandroid.modeling.*`** / **`obsidiandroid.features.feature_vector_builder`**. Selected tests switch to **`obsidiandroid.modeling`** / **`features`** for Pass **47**-surfaced modules; internals-only **`ml_classification`** imports remain where no façade exists.
- **Pass 78 (feature engineering physical slice):** **`assign_tier_scores`**, **`compute_vendor_scores`**, **`prepare_engine_metrics`**, and **`pattern_analysis`** live under **`src/obsidiandroid/feature_engineering/`**. **`analysis/feature_engineering/*.py`** are thin identity shims; canonical package **`__init__.py`** registers **`analysis.feature_engineering.<submodule>`** on **`sys.modules`** so legacy submodule imports preserve **`ModuleType`** identity (same pattern as **Pass 76** manifests). **`stage_modeling`** and vendor-score tests use **`obsidiandroid.feature_engineering`**.
- **Pass 79 (shim indirection prune):** **`obsidiandroid.pipeline`** **`__getattr__`** loads runner attributes from **`obsidiandroid.pipeline.runner`** (not **`analysis.pipeline.runner`**). Canonical diagnostics and tests that needed **`sample_preparation`** / **`pipeline_runner`** use **`obsidiandroid.pipeline`**. **`check_import_surface`** treats physical modules as source of truth and deduplicates the former double identity loop for moved pipeline leaves. **Disk shims under `analysis/pipeline/` remain** for legacy imports and operator stability.
- **Pass 80 (orchestration + matrix physical slice):** **`metadata_features`**, **`methodology_artifacts`**, **`permission_features`**, **`profile_filters`**, and **`runtime_reporting`** live under **`src/obsidiandroid/orchestration/`**; **`av_binary_matrix_builder`**, **`enrich_malicious_scores`**, and **`enrich_score_features`** under **`src/obsidiandroid/matrix/`**. **`analysis/orchestration/*.py`** and **`analysis/matrix/*.py`** are thin identity shims; canonical package **`__init__`** files register **`sys.modules`** aliases for **`analysis.orchestration.*`** / **`analysis.matrix.*`** (same pattern as **Pass 76** / **Pass 78**). Runner, CLI, **`ml_classification.training.pipeline_core`**, pipeline stages, and diagnostics imports use **`obsidiandroid.orchestration`** / **`obsidiandroid.matrix`**.
- **Pass 81 (risk band physical slice):** **`assign_risk_band`** and **`phase_score_engines`** live under **`src/obsidiandroid/risk_band/`**. **`analysis/risk_band/*.py`** are thin identity shims; canonical package **`__init__.py`** registers **`analysis.risk_band.<submodule>`** on **`sys.modules`** so legacy submodule imports preserve **`ModuleType`** identity. Callers (`score_av_engines`, matrix enrichment) use **`obsidiandroid.risk_band`**.
- **Pass 82 (features façade widen — vectorization helpers):** **`obsidiandroid.features`** façade adds **`feature_encoder`**, **`feature_engine_selection`**, and **`feature_vendor_extractor`** alongside **`feature_vector_builder`** (pre-**Pass 83**, all were aliases of **`ml_classification.vectorization.*`** module objects). Callers/tests updated toward canonical imports.
- **Pass 83 (vectorization physical slice):** **`feature_encoder`**, **`feature_engine_selection`**, **`feature_vendor_extractor`**, and **`feature_vector_builder`** live under **`src/obsidiandroid/features/vectorization/`**; **`ml_classification/vectorization/*.py`** are thin identity shims. **`obsidiandroid.features.vectorization`** **`__init__.py`** registers **`ml_classification.vectorization.<submodule>`** on **`sys.modules`** (submodule import identity). Façade **`obsidiandroid.features`** re-exports canonical **`obsidiandroid.features.vectorization.*`** modules.
- **Pass 84 (model helper closure slice):** **`risk_band_config`** lives under **`obsidiandroid.risk_band`**; **`record_diagnostics`** and **`metadata_normalizer`** live under **`obsidiandroid.vendors.contracts`**. Legacy **`model.core.*`** / **`model.utils.*`** imports remain valid through thin **`sys.modules`** identity shims. Canonical callers no longer import **`model.*`**.
- **Pass 85 (malware-family constants physical slice):** **`malware_family_constants`** lives under **`obsidiandroid.labeling`**; legacy **`ml_classification.common.malware_family_constants`** is a thin identity shim. Canonical taxonomy/vendor parser callers use **`obsidiandroid.labeling.*`** paths; legacy ML internals may continue through the shim until broader ML physical migration.
- **Pass 86 (classification label resolver physical slice):** **`classification_label_resolver`** lives under **`obsidiandroid.labeling`**; legacy **`ml_classification.labeling.classification_label_resolver`** is a thin identity shim. Deeper labeling helpers remain under **`ml_classification.labeling`** until wrapper contracts are settled.
- **Pass 87 (modeling utility physical slice):** **`distribution_reporter`** and **`feature_label_alignment_helper`** live under **`obsidiandroid.modeling`**; legacy **`ml_classification.ml_utils.*`** paths are thin identity shims. Large training modules remain under **`ml_classification.training`**.
- **Pass 88 (modeling alignment helper closure):** **`feature_alignment_utils`** lives under **`obsidiandroid.modeling`** as the implementation helper for **`feature_label_alignment_helper`**; legacy **`ml_classification.ml_utils.feature_alignment_utils`** is a thin identity shim.
- **Pass 89 (feature schema audit physical slice):** **`feature_schema_audit`** lives under **`obsidiandroid.features`**; legacy **`ml_classification.training.feature_schema_audit`** is a thin identity shim. **`prediction_builder`** imports the canonical helper while broader training remains legacy.
- **Pass 90 (data alignment physical slice):** **`data_alignment`** lives under **`obsidiandroid.modeling`**; legacy **`ml_classification.training.data_alignment`** is a thin identity shim. **`pipeline_core`** imports the canonical helper while broader training remains legacy.
- **Pass 91 (ML result/prediction helper closure):** **`ml_result_analyzer`**, **`ml_result_validator`**, and **`model_prediction`** live under **`obsidiandroid.modeling`**; legacy **`ml_classification.ml_utils.*`** / **`ml_classification.training.model_prediction`** paths are thin identity shims. Training orchestration remains legacy, but direct helper imports now use canonical modules.
- **Pass 92 (training controller physical slice):** **`pipeline_core`** and **`model_trainer_factory`** live under **`obsidiandroid.modeling`**; legacy **`ml_classification.training.pipeline_core`** / **`model_trainer_factory`** are thin identity shims.
- **Pass 93 (training execution stack lift):** **`pipeline_result_promoter`**, **`train_model_executor`**, **`model_training`**, **`prediction_builder`**, **`model_evaluation`**, **`training_helpers`**, and **`ml_trainers/`** live under **`obsidiandroid.modeling`**; **`pipeline_core`** / **`model_trainer_factory`** resolve those dependencies in-package (no hop through legacy trees for internals). **`ml_classification.training`** paths remain thin identity shims for compatibility.
- **Pass 94 (classifier evaluation + reporting closure):** **`ml_eval_engine`**, **`ml_comparator_summary`**, **`accuracy_band_utils`**, and **`ml_report_builder`** live under **`obsidiandroid.evaluation`**; legacy **`ml_classification.ml_utils.*`** (three modules) and **`ml_classification.reporting.ml_report_builder`** are thin identity shims. **`analysis.evaluation`** registers the same **`ModuleType`** objects. **`dataset_splitter`** lives under **`obsidiandroid.modeling`** with legacy **`ml_classification.ml_utils.dataset_splitter`** shim; **`model_trainer_factory`** imports it from the canonical modeling module.
- **Pass 95 (labeling helper physical slice):** **`label_input_validator`**, **`label_builder_wrapper`**, **`label_postprocessor`**, **`label_field_normalizer`**, and **`label_format_generator`** live under **`obsidiandroid.labeling`**; **`classification_label_resolver`** imports them in-package; legacy **`ml_classification.labeling.*`** paths are thin identity shims. **`label_field_normalizer`** / **`label_builder_wrapper`** / **`label_format_generator`** use canonical **`obsidiandroid.labeling.malware_family_constants`** for taxonomy helpers; **`inference`** engines remain legacy imports inside **`label_field_normalizer`** until a future pass.
- **Pass 96 (classification row-builder physical slice):** All **`ml_classification.builder`** leaf modules (**`sample_classification_builder`**, **`classification_row_builder`**, **`prediction_utils`**, **`vendor_record_selector`**, **`record_enrichment`**, **`classification_constants`**) live under **`obsidiandroid.classification_builder`** with lazy façade **`__getattr__`**; legacy **`ml_classification.builder.*`** are thin identity shims. **`label_builder_wrapper`** and **`compile_classification_results`** import **`sample_classification_builder`** canonically; **`prediction_utils`** uses **`obsidiandroid.labeling.malware_family_constants`**.
- **Pass 97 (inference heuristic physical slice):** **`label_consensus_engine`**, **`threat_class_engine`**, **`malware_type_engine`**, and **`signal_health_checker`** live under **`obsidiandroid.inference`** with lazy façade **`__getattr__`**; **`label_consensus_engine`** imports **`signal_health_checker`** in-package. **`classification_builder`**, **`label_field_normalizer`**, **`label_postprocessor`**, and **`compile_classification_results`** use canonical inference imports; legacy **`ml_classification.inference.*`** are thin identity shims.
- **Pass 98 (engine weights + classification results reporting):** All **`ml_classification.engine_weights`** modules live under **`obsidiandroid.engine_weights`** with lazy façade **`__getattr__`**; **`compile_classification_results`** lives under **`obsidiandroid.reporting`**; legacy paths are thin identity shims.
- **Pass 99 (legacy subtree hygiene):** Repo-root **`ml_classification/__init__.py`** documents the tree as transitional shim-first (no eager imports). **`ml_classification/ml_utils/__init__.py`** drops eager **`dataset_splitter`** pull-in; exposes known shim submodule names via **`__getattr__`** / **`__dir__`** / **`__all__`** for consistent discovery and **`pkg.attr`** access. **`ml_classification/common/__init__.py`** adds the same pattern for **`malware_family_constants`**.
- **Pass 100 (legacy subpackage lazy facades):** Non-empty **`__init__.py`** facades for **`ml_classification.builder`**, **`inference`**, **`engine_weights`**, **`labeling`**, **`reporting`**, **`vectorization`**, **`training`**, and **`training.ml_trainers`**: each lists its known shim leaf names and resolves **`__getattr__`** via **`importlib.import_module`** (same objects as explicit submodule imports). **`training.ml_trainers`** drops eager trainer pre-imports in favor of the same lazy pattern.
- **Pass 101 (repo-root dev wrapper sunset):** Removed **`run_tests.sh`**, **`run_tests_full.sh`**, **`clean_bytecode_cache.py`**, **`run_ml_static_scan.py`**; **`pyproject.toml`** **`py-modules`** is **`["main"]`** only. Documentation and **`scripts/dev/README.md`** now cite **`scripts/dev/*`** and **`python -m scripts.dev.run_ml_static_scan`** instead of repo-root duplicates.
- **Pass 102 (utils bootstrap dedupe):** **`utils/__init__.py`** imports **`utils.repo_import_paths`** once for checkout **`sys.path`** setup; redundant **`import utils.repo_import_paths`** lines removed from **`utils/`** leaf shims (**`exporting/`**, **`logging/`**, root **`utils/*.py`**). **`scripts/dev/check_import_surface.py`** enforces **`utils.repo_import_paths`** in **`utils/__init__.py`** and drops the per-file substring requirement for leaf shims.
- **Pass 103 (main.py bootstrap shortcut):** Repo-root **`main.py`** uses **`import utils`** (side-effect bootstrap via **`utils/__init__.py`** → **`repo_import_paths`**) instead of importing **`ensure_repo_src_on_sys_path`** from **`utils.repo_import_paths`** explicitly.

### Locked migration policy (product + imports)

These choices govern Pass 38+ work; they intentionally favor **operator stability** over **tree cosmetics**.

1. **Product identity** — ObsidianDroid is both a **research pipeline CLI / operator tool** and an **internal Python package** (`obsidiandroid.*`) for tooling, tests, and future integrations. **When goals conflict, priority order is:** (a) operator/research pipeline stability, (b) reproducibility and evidence integrity, (c) canonical package cleanliness, (d) external library polish. Do not change real pipeline behavior or paper/evidence outputs solely to tidy imports.

2. **Canonical surface** — **`obsidiandroid.*`** is the long-term **public/canonical** import surface. Root **`analysis.*`**, **`database.*`**, **`ml_classification.*`**, **`model.*`** remain **implementation** paths until each domain has an appropriate façade and migration coverage.

3. **Breaking changes / shims** — No sudden flag day. **New and internal code** should prefer **`obsidiandroid.*`**. Legacy imports remain via **shims** during migration. Retire old paths only after: internal code no longer needs them; tests rely on them only where shim parity is the point; docs do not recommend them; and at least one stable checkpoint exists after the canonical path is real. For now: **`utils.*` shims stay**, root **`main.py` stays** for operators, and legacy trees stay until façades land.

4. **Tests** — **New tests should use canonical imports by default** (`obsidiandroid.*`, **`scripts.dev`**, **`scripts.diagnostics`** as already documented). Use **`utils.*`**, **`main`**, or raw **`analysis.*` / `database.*`** only when testing shims, unavoidable monkeypatch surfaces, or migration parity explicitly.

## Pass 2 (complete): `common.repo_paths` + `pipeline` facade

| Item | Status | Notes |
|------|--------|-------|
| `src/obsidiandroid/common/repo_paths.py` | **moved_now** | Canonical `ensure_repo_src_on_sys_path()` for checkout installs (detects `.../src/obsidiandroid/...`). |
| `utils/repo_import_paths.py` | **wrapper_kept** | Prepends repo `src/` then imports and calls `obsidiandroid.common.repo_paths` (single policy, shims stay tiny). |
| `main.py` (root) | **wrapper_kept** | After local `src/` prepend, calls `ensure_repo_src_on_sys_path()` from `common`. |
| `src/obsidiandroid/common/__init__.py` | **moved_now** | Re-exports `ensure_repo_src_on_sys_path` (starts real `common` content). |
| `src/obsidiandroid/pipeline/__init__.py` | **moved_now** / **wrapper-style** | Re-exports `run_pipeline` from `analysis.pipeline.runner` for **`from obsidiandroid.pipeline import run_pipeline`** (files still under `analysis/pipeline/`). |
| `run.sh` | **moved_now** | Sets `PYTHONPATH="${ROOT_DIR}/src:..."` before invoking Python. |
| `tests/test_obsidiandroid_package_surface.py` | **moved_now** | Verifies pipeline facade identity + idempotent path helper. |

### Pass 2 tests

- **Outcome:** `pytest -q -m "not slow"` — **351 passed** (includes `tests/test_obsidiandroid_package_surface.py`).

## Pass 1 (complete): package shell + CLI

### Target package roots (`src/obsidiandroid/`)

| Path | Status | Notes |
|------|--------|-------|
| `obsidiandroid/__init__.py` | **moved_now** | Package root. |
| `obsidiandroid/cli/` | **moved_now** | `main.py`, `startup_menu.py`, `pipeline_entry.py`, `menu/`, `ui/`. |
| `obsidiandroid/pipeline/` | **partial** (**Passes 66–71, 74–76**) | **`runner`**, **`runner`-direct stages**, AV chain, **`vendor_metadata_pipeline`**, **`permission_trends/`**, **`manifest/`**, **`artifacts/`** under **`src/`**; **`analysis/pipeline/`** holds thin shims for moved leaves. |
| `obsidiandroid/orchestration/` | **moved_now** (**Pass 80**) | Permission / methodology / profile / **`runtime_reporting`** modules under **`src/`**; **`analysis/orchestration/`** shims. |
| `obsidiandroid/matrix/` | **moved_now** (**Pass 80**) | AV binary matrix + enrichment under **`src/`**; **`analysis/matrix/`** shims. |
| `obsidiandroid/risk_band/` | **moved_now** (**Passes 81, 84**) | Assignment + engine helpers + **`risk_band_config`** under **`src/`**; **`analysis/risk_band/`** shims; legacy **`model.core.risk_band_config`** identity shim. |
| `obsidiandroid/database/` | **partial** (Pass 38) | Curated façade re-exports **`database.*`** modules (same objects); implementation remains top-level **`database/`**. |
| `obsidiandroid/vendors/` | **partial** (Passes **59**, **64**, **84**) | **`parsing/`**, **`contracts/`** (incl. **`record_diagnostics`**, **`metadata_normalizer`** — Pass **84**), **`execution/`** under **`src/`**; **`analysis.vendor_processing`** / **`analysis.execution`** package shims. **`model.vendor`** / **`model.parsing`** record types still legacy shims into **`obsidiandroid.vendors.contracts`**. |
| `obsidiandroid/features/` | **partial** | **`vectorization/`** canonical (**Pass 83**); **`feature_schema_audit`** canonical at package root (**Pass 89**); legacy **`ml_classification.*`** shims; large training stack still **`ml_classification/training/`**. |
| `obsidiandroid/labeling/` | **partial** | **`malware_family_constants`**, **`classification_label_resolver`**, plus (**Pass 95**) **`label_input_validator`**, **`label_builder_wrapper`**, **`label_postprocessor`**, **`label_field_normalizer`**, **`label_format_generator`** under **`src/`**; **`taxonomy`** wrapper (**Pass 58**); legacy **`ml_classification/labeling/`** shim-only for those names. |
| `obsidiandroid/classification_builder/` | **moved_now** (**Pass 96**) | **`sample_classification_builder`**, **`classification_row_builder`**, **`prediction_utils`**, **`vendor_record_selector`**, **`record_enrichment`**, **`classification_constants`** under **`src/`**; lazy façade; legacy **`ml_classification/builder/`** shim-only. |
| `obsidiandroid/inference/` | **moved_now** (**Pass 97**) | Vendor-consensus + threat/type inference + signal-health helpers under **`src/`**; lazy façade; legacy **`ml_classification/inference/`** shim-only. |
| `obsidiandroid/engine_weights/` | **moved_now** (**Pass 98**) | AV engine ML weight pipeline helpers under **`src/`**; lazy façade; legacy **`ml_classification/engine_weights/`** shim-only. |
| `obsidiandroid/modeling/` | **partial** | **`model_exporter`** canonical; modeling + **full default training execution surface** (**Passes 87–88, 90–93**) under **`src/`** including **`ml_trainers/`**; legacy **`ml_classification/training/`** is shim-only for moved names. **`ml_classification.ml_utils`** beyond shims remains separate. |
| `obsidiandroid/evaluation/` | **partial** (Passes **63**, **94**) | AV/vendor tooling + (**Pass 94**) classifier training eval/reporting (**`ml_eval_engine`**, **`ml_comparator_summary`**, **`accuracy_band_utils`**, **`ml_report_builder`**) canonical under **`src/`**; **`analysis/evaluation/`** registers identity. Boundaries still per **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`**. |
| `obsidiandroid/diagnostics/` | **moved_now** (**Pass 65**) | **Implementations** under **`src/`**; **`analysis/diagnostics/`** is **`__init__.py` only** (identity shim). Further work is optional (callers, docs-only). |
| `obsidiandroid/reporting/` | **partial** | **`export_manager`**, LaTeX/family/confusion helpers canonical; **`compile_classification_results`** (**Pass 98**); legacy **`ml_classification.reporting.compile_classification_results`** shim-only; **`ml_report_builder`** canonical under **`obsidiandroid.evaluation`** (**Pass 94**). |
| `obsidiandroid/observability/` | **partial** | **`logging/`** + **`pipeline_observability/`** canonical; package **`__init__`** re-exports **`get_logger`** / **`log_event`**. |
| `obsidiandroid/governance/` | **partial** (**Pass 75** + prior passes) | Pipeline governance leaves (**exceptions**, **integrity**, **policy**, **readiness**) canonical; compliance, manifest, cohort, evidence mode, artifacts under **`src/`**; legacy **`analysis.pipeline.governance.*`** shims for import identity. |
| `obsidiandroid/common/` | **partial** | Hashing, canonical CSV/SHA helpers, path safety, runtime diagnostics paths, and checkout ``repo_paths`` live here; see Pass 4. |

### CLI / entrypoint files

| Current path | Target | Status |
|--------------|--------|--------|
| `main.py` | `obsidiandroid/cli/main.py` | **moved_now** (canonical) + **wrapper_kept** at repo root |
| `utils/startup_menu.py` | `obsidiandroid/cli/startup_menu.py` | **moved_now** + **wrapper_kept** |
| `utils/pipeline_entry.py` | `obsidiandroid/cli/pipeline_entry.py` | **moved_now** + **wrapper_kept** |
| `utils/menu/`, `utils/ui/` | `obsidiandroid/cli/menu/`, `obsidiandroid/cli/ui/` | **deleted** (**Pass 72**) — were empty stubs; canonical CLI lives under **`src/`** only |
| `utils/repo_import_paths.py` | *(new)* | **moved_now** | Bootstrap `src/` onto `sys.path` for checkout runs without editable install. |

### Build / tooling

| File | Change | Status |
|------|--------|--------|
| `pyproject.toml` | `[project.scripts] obsidiandroid` → `obsidiandroid.cli.startup_menu:main`; `[tool.setuptools.packages.find] where = ["src", "."]` + `obsidiandroid*` in `include` | **moved_now** |
| `tests/conftest.py` | Prepend `repo/src` to `sys.path` for `import obsidiandroid` during pytest | **moved_now** |

### Intended future moves (reference)

This table mixes **completed** (**moved_now**) and **remaining** targets; use the **Snapshot** for narrative current truth.

| Current area | Target domain | Status |
|--------------|---------------|--------|
| `analysis/pipeline/runner.py` | `obsidiandroid.pipeline.runner` | **moved_now** (**Pass 67**) — **`analysis/pipeline/runner.py`** is shim only. |
| `analysis/pipeline/main_facade.py` | `obsidiandroid.pipeline.main_facade` | **moved_now** (**Pass 68**) — shim only. |
| `analysis/pipeline/stage_samples.py` | `obsidiandroid.pipeline.stage_samples` | **moved_now** (**Pass 68**) — shim only. |
| `analysis/pipeline/sample_exports.py` | `obsidiandroid.pipeline.sample_exports` | **moved_now** (**Pass 69**) — shim only. |
| `analysis/pipeline/stage_av_vendor.py` | `obsidiandroid.pipeline.stage_av_vendor` | **moved_now** (**Pass 69**) — shim only. |
| `analysis/pipeline/stage_manifest.py` | `obsidiandroid.pipeline.stage_manifest` | **moved_now** (**Pass 69**) — shim only. |
| `analysis/pipeline/sample_preparation.py` | `obsidiandroid.pipeline.sample_preparation` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/stage_feature_enrichment.py` | `obsidiandroid.pipeline.stage_feature_enrichment` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/stage_modeling.py` | `obsidiandroid.pipeline.stage_modeling` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/stage_ablation.py` | `obsidiandroid.pipeline.stage_ablation` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/stage_results_warehouse.py` | `obsidiandroid.pipeline.stage_results_warehouse` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/stage_permission_trends_report.py` | `obsidiandroid.pipeline.stage_permission_trends_report` | **moved_now** (**Pass 70**) — shim only. |
| `analysis/pipeline/av_engine_pipeline.py` (chain) | `obsidiandroid.pipeline.*` | **moved_now** (**Pass 71**) — **`engine_pipeline_utils`**, **`attach_engine_metadata`**, **`engine_normalization`**, **`score_av_engines`**, **`av_engine_pipeline`**, **`vendor_metadata_pipeline`**; shims only under **`analysis/pipeline/`**. |
| `analysis/pipeline/permission_trends/*`, `permission_trends_selection.py` | `obsidiandroid.pipeline.*` | **moved_now** (**Pass 74**) — shims only under **`analysis/pipeline/`**. |
| `analysis/pipeline/governance/*` | `obsidiandroid.governance` | **moved_now** (**Pass 75**) — **`exceptions`**, **`integrity`**, **`policy`**, **`readiness`** under **`src/`**; **`analysis/pipeline/governance/`** shims + **`__init__.py`** re-exports only. |
| `analysis/vendor_processing/*` (parser leaf modules) | `obsidiandroid.vendors.parsing` | **moved_now** (**Pass 59**) — **`analysis/vendor_processing/`** is package-only shim (**`__init__.py`**). |
| `model/vendor`, `model/parsing/`, `ml_classification/engine_weights/` | `obsidiandroid.vendors` / `obsidiandroid.evaluation` | **move_later** / **needs_review** — types and weights still on legacy paths; boundary rules in **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`**. |
| `model/core/risk_band_config.py` | `obsidiandroid.risk_band.risk_band_config` | **moved_now** (**Pass 84**) — shim only. |
| `model/core/record_diagnostics.py` | `obsidiandroid.vendors.contracts.record_diagnostics` | **moved_now** (**Pass 84**) — shim only. |
| `model/utils/metadata_normalizer.py` | `obsidiandroid.vendors.contracts.metadata_normalizer` | **moved_now** (**Pass 84**) — shim only. |
| `ml_classification/vectorization/` | `obsidiandroid.features.vectorization` | **moved_now** (**Pass 83**) — shims only. |
| `ml_classification/common/malware_family_constants.py` | `obsidiandroid.labeling.malware_family_constants` | **moved_now** (**Pass 85**) — shim only. |
| `ml_classification/labeling/classification_label_resolver.py` | `obsidiandroid.labeling.classification_label_resolver` | **moved_now** (**Pass 86**) — shim only. |
| `ml_classification/labeling/label_input_validator.py` | `obsidiandroid.labeling.label_input_validator` | **moved_now** (**Pass 95**) — shim only. |
| `ml_classification/labeling/label_builder_wrapper.py` | `obsidiandroid.labeling.label_builder_wrapper` | **moved_now** (**Pass 95**) — shim only. |
| `ml_classification/labeling/label_postprocessor.py` | `obsidiandroid.labeling.label_postprocessor` | **moved_now** (**Pass 95**) — shim only. |
| `ml_classification/labeling/label_field_normalizer.py` | `obsidiandroid.labeling.label_field_normalizer` | **moved_now** (**Pass 95**) — shim only. |
| `ml_classification/labeling/label_format_generator.py` | `obsidiandroid.labeling.label_format_generator` | **moved_now** (**Pass 95**) — shim only. |
| `ml_classification/ml_utils/distribution_reporter.py` | `obsidiandroid.modeling.distribution_reporter` | **moved_now** (**Pass 87**) — shim only. |
| `ml_classification/ml_utils/feature_label_alignment_helper.py` | `obsidiandroid.modeling.feature_label_alignment_helper` | **moved_now** (**Pass 87**) — shim only. |
| `ml_classification/ml_utils/feature_alignment_utils.py` | `obsidiandroid.modeling.feature_alignment_utils` | **moved_now** (**Pass 88**) — shim only. |
| `ml_classification/training/feature_schema_audit.py` | `obsidiandroid.features.feature_schema_audit` | **moved_now** (**Pass 89**) — shim only. |
| `ml_classification/training/data_alignment.py` | `obsidiandroid.modeling.data_alignment` | **moved_now** (**Pass 90**) — shim only. |
| `ml_classification/ml_utils/ml_result_analyzer.py` | `obsidiandroid.modeling.ml_result_analyzer` | **moved_now** (**Pass 91**) — shim only. |
| `ml_classification/ml_utils/ml_result_validator.py` | `obsidiandroid.modeling.ml_result_validator` | **moved_now** (**Pass 91**) — shim only. |
| `ml_classification/ml_utils/ml_eval_engine.py` | `obsidiandroid.evaluation.ml_eval_engine` | **moved_now** (**Pass 94**) — shim only. |
| `ml_classification/ml_utils/ml_comparator_summary.py` | `obsidiandroid.evaluation.ml_comparator_summary` | **moved_now** (**Pass 94**) — shim only. |
| `ml_classification/ml_utils/accuracy_band_utils.py` | `obsidiandroid.evaluation.accuracy_band_utils` | **moved_now** (**Pass 94**) — shim only. |
| `ml_classification/ml_utils/dataset_splitter.py` | `obsidiandroid.modeling.dataset_splitter` | **moved_now** (**Pass 94**) — shim only. |
| `ml_classification/reporting/ml_report_builder.py` | `obsidiandroid.evaluation.ml_report_builder` | **moved_now** (**Pass 94**) — shim only. |
| `ml_classification/reporting/compile_classification_results.py` | `obsidiandroid.reporting.compile_classification_results` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/assign_detection_tiers.py` | `obsidiandroid.engine_weights.assign_detection_tiers` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/build_classification_weights.py` | `obsidiandroid.engine_weights.build_classification_weights` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/classification_weight_inspector.py` | `obsidiandroid.engine_weights.classification_weight_inspector` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/classification_weight_utils.py` | `obsidiandroid.engine_weights.classification_weight_utils` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/compute_reliability_score.py` | `obsidiandroid.engine_weights.compute_reliability_score` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/engine_weights/engine_weights_utils.py` | `obsidiandroid.engine_weights.engine_weights_utils` | **moved_now** (**Pass 98**) — shim only. |
| `ml_classification/training/model_prediction.py` | `obsidiandroid.modeling.model_prediction` | **moved_now** (**Pass 91**) — shim only. |
| `ml_classification/training/pipeline_core.py` | `obsidiandroid.modeling.pipeline_core` | **moved_now** (**Pass 92**) — shim only. |
| `ml_classification/training/model_trainer_factory.py` | `obsidiandroid.modeling.model_trainer_factory` | **moved_now** (**Pass 92**) — shim only. |
| `ml_classification/training/pipeline_result_promoter.py` | `obsidiandroid.modeling.pipeline_result_promoter` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/train_model_executor.py` | `obsidiandroid.modeling.train_model_executor` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/model_training.py` | `obsidiandroid.modeling.model_training` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/prediction_builder.py` | `obsidiandroid.modeling.prediction_builder` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/model_evaluation.py` | `obsidiandroid.modeling.model_evaluation` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/training_helpers.py` | `obsidiandroid.modeling.training_helpers` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/training/ml_trainers/*.py` | `obsidiandroid.modeling.ml_trainers.*` | **moved_now** (**Pass 93**) — shim only. |
| `ml_classification/builder/classification_constants.py` | `obsidiandroid.classification_builder.classification_constants` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/builder/classification_row_builder.py` | `obsidiandroid.classification_builder.classification_row_builder` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/builder/prediction_utils.py` | `obsidiandroid.classification_builder.prediction_utils` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/builder/record_enrichment.py` | `obsidiandroid.classification_builder.record_enrichment` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/builder/sample_classification_builder.py` | `obsidiandroid.classification_builder.sample_classification_builder` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/builder/vendor_record_selector.py` | `obsidiandroid.classification_builder.vendor_record_selector` | **moved_now** (**Pass 96**) — shim only. |
| `ml_classification/inference/label_consensus_engine.py` | `obsidiandroid.inference.label_consensus_engine` | **moved_now** (**Pass 97**) — shim only. |
| `ml_classification/inference/threat_class_engine.py` | `obsidiandroid.inference.threat_class_engine` | **moved_now** (**Pass 97**) — shim only. |
| `ml_classification/inference/malware_type_engine.py` | `obsidiandroid.inference.malware_type_engine` | **moved_now** (**Pass 97**) — shim only. |
| `ml_classification/inference/signal_health_checker.py` | `obsidiandroid.inference.signal_health_checker` | **moved_now** (**Pass 97**) — shim only. |
| `ml_classification/labeling/` | `obsidiandroid.labeling` | **partial** — listed modules **Pass 85–86, 95** (**shim-only** on disk for moved names) |
| `ml_classification/training/` | `obsidiandroid.modeling` | **shim-only** for listed modules (**Passes 90–93**); no remaining training implementation |
| `analysis/evaluation/` (implementations were under leaf `*.py`) | `obsidiandroid.evaluation` | **partial** (**Pass 63**) — canonical modules under **`src/`**; **`analysis/evaluation/__init__.py`** only (**identity** via **`sys.modules`**) |
| `analysis/diagnostics/` (implementations were under leaf `*.py`) | `obsidiandroid.diagnostics` | **partial** (**Pass 65**) — canonical tree under **`src/`**; **`analysis/diagnostics/__init__.py`** only (**identity**) |
| `utils/export*`, LaTeX/workbook/paper exporters | `obsidiandroid.reporting` | **partial** — **`export_manager`** + several reporters canonical (**`utils.*`** shims **wrapper_kept**) |
| `utils/evidence_mode_resolver` | `obsidiandroid.governance.evidence_mode_resolver` | **moved_now** (shim **wrapper_kept**) |
| compliance, run manifest, cohort readiness, reproducibility | `obsidiandroid.governance` | **partial** — major modules canonical (**`utils.*`** shims **wrapper_kept**) |
| `utils/logging/` | `obsidiandroid.observability.logging` | **wrapper_kept** (shims); canonical under **`src/`** |
| `utils/hash_utils`, canonicalization, path safety, runtime/output paths | `obsidiandroid.common` | **partial** — implementations under **`src/`**; **`utils.*`** shims **wrapper_kept** |

### Legacy layout to retire after migration

| Item | Status |
|------|--------|
| Root `utils/menu/`, `utils/ui/` stub packages | **deleted** (**Pass 72**) — no callers remained |
| `utils/repo_import_paths.py` | **delete_later** or fold into `obsidiandroid.common` |
| Root `main.py` shim | **delete_later** (tests rely on `import main`; update tests/docs first) |

## Pass 1 test results

- **Command:** `pytest -q -m "not slow"`
- **Outcome:** 349 passed (155 deselected).
- **Fixes for this pass:** Tests that monkeypatched names on `utils.startup_menu` or `utils.menu.profile_preflight` were updated to patch **`obsidiandroid.cli.startup_menu`** and **`obsidiandroid.cli.menu.profile_preflight`**, because implementation globals live on the canonical modules; thin shims do not intercept runtime name lookup inside functions defined in `obsidiandroid.cli`.
- **Additional:** `tests/test_startup_menu.py` (slow tier) — 24 passed with `-m "slow or not slow"`.

## Pass 3 (complete): `.gitignore`, import smoke script, documentation

| Item | Status | Notes |
|------|--------|-------|
| `.gitignore` | **verified** | Already contained `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.venv/`, `build/`, `dist/`, `*.egg-info/` (no change required for this pass). |
| `scripts/dev/check_import_surface.py` | **moved_now** | Prints resolved paths and checks `run_pipeline` identity; exits nonzero on failure. |
| `make dev-import-check` | **moved_now** | Invokes the smoke script (`Makefile` target). |
| Developer import modes | **moved_now** | Documented in this file, `AGENTS.md`, and `docs/developer_guide.md`. |

## Pass 4 (complete): `obsidiandroid.common` utilities (first batch)

### Modules inspected

| Module | Risk | Decision |
|--------|------|----------|
| `utils/hash_utils.py` | Low — stdlib only | **moved_now** |
| `utils/canonicalization.py` | Low — stdlib only | **moved_now** |
| `utils/path_safety.py` | Low — pathlib only | **moved_now** |
| `utils/runtime_paths.py` | Low — depends on `config.app_config` only | **moved_now** |
| `utils/output_paths.py` | **moved** — canonical :mod:`obsidiandroid.common.output_paths`; **shim** kept at **utils** for legacy ``from utils import output_paths`` | **moved_now** |

### Canonical locations (`src/obsidiandroid/common/`)

| Implementation | Status |
|----------------|--------|
| `hash_utils.py` | **moved_now** |
| `canonicalization.py` | **moved_now** |
| `path_safety.py` | **moved_now** |
| `runtime_paths.py` | **moved_now** |

### Legacy shims (`utils/`)

| Shim | Status |
|------|--------|
| `utils/hash_utils.py` | **wrapper_kept** — `repo_import_paths` + star-import from `obsidiandroid.common.hash_utils` |
| `utils/canonicalization.py` | **wrapper_kept** |
| `utils/path_safety.py` | **wrapper_kept** |
| `utils/runtime_paths.py` | **wrapper_kept** |

### Import updates (canonical-first, minimal blast radius)

- `src/obsidiandroid/cli/menu/vendor_diagnostics.py` now imports `resolve_diagnostics_dir` from **`obsidiandroid.common.runtime_paths`**. Other callers keep **`from utils.runtime_paths`** (same objects via shims).

### Tests

- **New:** `tests/test_obsidiandroid_common_shims.py` — asserts legacy `utils.*` names are identical to `obsidiandroid.common.*` functions/classes.

### Pruning

- **None** — compatibility shims retained; no dead files removed this pass.

### Inspection backlog (no change yet)

- **Duplicate CSV helpers:** `analysis/pipeline/manifest/hashing.py` defines a `canonical_csv_bytes` used by manifest code paths; `utils.canonicalization` / `obsidiandroid.common.canonicalization` defines a different `canonical_csv_bytes(dict rows, fieldnames)` used by training/manifest CSV governance. Same name, different signatures — **needs_review** for future consolidation or renaming.
- **Stale docs:** Many modules still document `from utils.*`; shims remain valid. Prefer new code importing `obsidiandroid.common.*` where practical.
- **`utils/output_paths.py`:** **moved** — implementation in **`obsidiandroid.common.output_paths`** (uses **`repo_root()`** for log layout); pipeline and scripts import the canonical module; **shim** remains.

## Pass 5 (complete): more `obsidiandroid.common` (ML console + distribution printer)

### Modules moved

| Implementation | Notes | Status |
|----------------|-------|--------|
| `obsidiandroid/common/ml_console.py` | Config-driven verbosity gates (`is_minimal`, `is_debug`, …); same deps as before (`config.app_config`). | **moved_now** |
| `obsidiandroid/common/display_distribution.py` | `print_distribution` for pandas `Series`; pandas-only. | **moved_now** |

### Shims (`wrapper_kept`)

| Legacy path | Canonical module |
|-------------|------------------|
| `utils/ml_console.py` | `obsidiandroid.common.ml_console` |
| `utils/display_distribution.py` | `obsidiandroid.common.display_distribution` |

### Canonical import updates

- `src/obsidiandroid/cli/ui/display.py` imports **`obsidiandroid.common.display_distribution`** (CLI UI no longer depends on `utils.display_distribution` for the bundled helper).

### Tooling

- `scripts/dev/check_import_surface.py` also imports **`obsidiandroid.common.hash_utils`**, **`ml_console`**, **`display_distribution`**, and asserts **`utils.hash_utils`** re-exports match the canonical module.

### Tests

- `tests/test_obsidiandroid_common_shims.py` extended with **ml_console** and **display_distribution** identity checks.

### Pruning

- **None** this pass.

## Pass 6 (complete): root layout hygiene (docs + script index; no code moves)

### Scope A — Generated / runtime ignore policy (verified)

All of the following are **ignored** by `.gitignore` (rules in parentheses). When using `git check-ignore -v`, use **directory paths with a trailing slash** for directories (e.g. `obsidiandroid.egg-info/`, `__pycache__/`); bare `obsidiandroid.egg-info` may not match `*.egg-info/`.

| Path / pattern | Rule (see `.gitignore`) |
|------------------|-------------------------|
| `output/` | `output/` |
| `logs/` | `logs/` |
| `.pytest_tmp/` | `.pytest_tmp/` |
| `*.egg-info/` (e.g. `obsidiandroid.egg-info/`) | `*.egg-info/` |
| `__pycache__/` | `__pycache__/` |
| `*.py[cod]` (e.g. `foo.pyc`) | `*.py[cod]` |
| `.venv/` | `.venv/` |
| `build/` | `build/` |
| `dist/` | `dist/` |

**Note:** `git status --ignored` should list these when present (e.g. `!! output/`, `!! logs/`, `!! .venv/`).

### Scope B — Script organization (documentation only)

| Item | Status |
|------|--------|
| `scripts/dev/README.md` | **moved_now** — describes `check_import_surface.py` and `make dev-import-check` |
| `scripts/diagnostics/README.md` | **moved_now** — index of diagnostic scripts (files still at `scripts/*.py`) |
| `scripts/README.md` | **moved_now** — layout table updated for `dev/` and diagnostics index |

### Scope C — Transitional top-level markers

| Path | Status |
|------|--------|
| `README.md` | **moved_now** — “Repository layout (hybrid migration)” + tree lines for `src/`, `scripts/dev/` |
| `data_inspect/README.md` | **moved_now** — short purpose blurb |
| `devtools/README.md` | **moved_now** — short purpose blurb |

**Not moved:** `analysis/`, `database/`, `ml_classification/`, `model/`, `utils/`, `clean_bytecode_cache.py` — still top-level; **core implementation packages are unchanged** this pass.

**Agent policy:** `AGENTS.md` updated with repository layout rules (canonical `src/obsidiandroid/`, transitional top-level packages, thin `utils/` shims, `output/`/`logs/` vs `artifacts/baselines/`, `scripts/dev/` vs diagnostics index, validation commands).

## Pass 7 (complete): `obsidiandroid.governance` — evidence mode

| Item | Status |
|------|--------|
| `src/obsidiandroid/governance/evidence_mode_resolver.py` | **moved_now** — evidence / paper-mode resolution (stdlib + dataclasses only) |
| `utils/evidence_mode_resolver.py` | **wrapper_kept** — `repo_import_paths` + star-import from governance |
| `analysis/pipeline/runner.py` | **moved_now** — imports `from obsidiandroid.governance import evidence_mode_resolver` |
| `tests/test_governance_primitives.py` | **moved_now** — canonical governance import (monkeypatch targets same module as runner) |
| `tests/test_obsidiandroid_governance_shims.py` | **moved_now** — shim vs canonical identity |
| `scripts/dev/check_import_surface.py` | **moved_now** — loads governance module + shim parity check |

**Not changed:** `analysis/pipeline` directory layout; only the import in `runner.py` was repointed. No change to resolution logic.

## Pass 8 (complete): `obsidiandroid.pipeline` facade + script layout cleanup

### Scope A — Pipeline facade

| Symbol | Notes |
|--------|-------|
| `run_pipeline`, `DIAGNOSTICS_DIR`, `PIPELINE_MAIN_LOGGER`, `PARSER_QUALITY_PATH` | **moved_now** — resolved via :func:`__getattr__` from `analysis.pipeline.runner` (stays in sync when tests monkeypatch `runner`); **not** snapshot copies at import time |

**Canonical imports updated:** `obsidiandroid.cli.main`, `obsidiandroid.cli.pipeline_entry` now import from **`obsidiandroid.pipeline`** for those symbols (behavior unchanged).

### Scope B — Scripts / root clutter

| Change | Status |
|--------|--------|
| `scripts/dev/clean_bytecode_cache.py` | **moved_now** — implementation; repo-root **`clean_bytecode_cache.py`** is **wrapper_kept** (delegates to `scripts.dev`) |
| `scripts/dev/data_fuzzer.py`, `scripts/dev/scan_ml_predict_misuse.py` | **moved_now** — canonical copies |
| `devtools/data_fuzzer.py`, `devtools/scan_ml_predict_misuse.py` | **wrapper_kept** — star-import from `scripts.dev` |
| `data_inspect/*.py` (inspect\_*) | **moved_now** → **`scripts/diagnostics/`** |
| `data_inspect/*.py` at repo root | **wrapper_kept** — thin shims → `scripts.diagnostics.*` |
| `run_ml_static_scan.py` | **moved_now** — repo-root shim → **`scripts.dev.run_ml_static_scan`** (which imports `scan_ml_predict_misuse`) |
| `pyproject.toml` `[tool.setuptools.packages.find] include` | **moved_now** — added `devtools*`, `scripts*` |

**Dead files:** none removed without replacement shims.

### Docs / tooling

- `scripts/dev/README.md`, `scripts/diagnostics/README.md`, `data_inspect/README.md`, `devtools/README.md`, root `README.md`, `docs/module_split_audit.md`, `docs/architecture.md`, `docs/data_sources.md` updated for new paths.
- `scripts/dev/check_import_surface.py` validates full pipeline facade vs `runner`.

## Pass 9 (complete): debt / documentation hygiene

| Item | Notes |
|------|--------|
| `pyproject.toml` | Removed **`testing*`** from setuptools `packages.find` — no `testing/` package exists (dead config). |
| `docs/module_split_audit.md` | Refreshed for **src-layout** (shims vs `src/obsidiandroid/cli/`, `runner.py` owns `run_pipeline`, updated LOC guidance). |
| `docs/README.md` | Quick facts: canonical paths, `scripts/dev/` / `scripts/diagnostics/`. |
| `docs/operations_playbook.md` | Storage bullet acknowledges `scripts/diagnostics/` + `data_inspect/` shims. |

## Pass 10 (complete): root layout cleanup

| Item | Notes |
|------|-------|
| `docs/STRUCTURE_MIGRATION_PLAN.md` | **moved_now** — canonical migration doc; repo-root **`STRUCTURE_MIGRATION_PLAN.md`** is **wrapper_kept** (pointer only). |
| `docs/GOVERNANCE.md` | **moved_now** — canonical governance spec; repo-root **`GOVERNANCE.md`** is **wrapper_kept** (pointer only). |
| `config/engine_aliases.yaml` | **moved_now** — engine alias YAML (was repo root); **`analysis/pipeline/engine_normalization.py`** resolves via repo-root path (cwd-independent). |
| `scripts/dev/run_ml_static_scan.py` | **moved_now** — argparse / scan driver; repo-root **`run_ml_static_scan.py`** is **wrapper_kept** (delegates to `scripts.dev.run_ml_static_scan`). |
| `pyproject.toml` | Removed dead **`model_tuning`** from `[tool.setuptools] py-modules` (no matching top-level module). |

## Pass 11 (complete): shell entrypoints under `scripts/dev/`

| Item | Notes |
|------|-------|
| `scripts/dev/bootstrap_venv.sh` | **moved_now** — Fedora venv + `pip install -r requirements.txt`; repo-root **`setup.sh`** is **wrapper_kept**. |
| `scripts/dev/launch_startup_menu.sh` | **moved_now** — `PYTHONPATH=src` + `python -m utils.startup_menu`; repo-root **`run.sh`** is **wrapper_kept**. |
| `scripts/dev/run_tests.sh` | **moved_now** — fast pytest (`-m "not slow"`); repo-root **`run_tests.sh`** is **wrapper_kept** (`make test` unchanged). |
| `scripts/dev/run_tests_full.sh` | **moved_now** — full pytest; repo-root **`run_tests_full.sh`** is **wrapper_kept** (`make test-full` unchanged). |

## Pass 12 (complete): Pass 9 follow-up (diagnostics/devtools shims, docs, Makefile)

### Scope A — Internal imports (canonical `scripts.*`)

| File | Change |
|------|--------|
| `ml_classification/training/pipeline_core.py` | `from scripts.diagnostics import inspect_classification_results as inspector` (replaces `data_inspect`) |
| `analysis/evaluation/vendor_feature_extractor.py` | `from scripts.diagnostics import inspect_vendor_feature_results` |
| `tests/test_data_fuzzer.py` | `from scripts.dev import data_fuzzer` (canonical) |
| `tests/test_devtools_shim.py` | **new** — asserts `devtools.data_fuzzer.generate_fuzz_data` is `scripts.dev.data_fuzzer.generate_fuzz_data` (shim test **removed** in **Pass 24**). |

### Scope B — `data_inspect*` / `devtools*` in `pyproject.toml` *(superseded by **Pass 24**)*

**At Pass 12:** both patterns were **kept** in `[tool.setuptools.packages.find] include` for editable-install compatibility with `from data_inspect …` / `from devtools …`.

**Pass 24:** entries **removed**; **`data_inspect/`** and **`devtools/`** directories **deleted** — use **`scripts.diagnostics`** / **`scripts.dev`** (see **Pass 24** table for off-repo migration).

### Scope C — Stale path comments and docs

- `scripts/diagnostics/inspect_vendor_feature_results.py` and `inspect_parsed_data.py` — first-line **Filename:** comments point at `scripts/diagnostics/...`.
- `tests/README.md` — points operators at **`scripts.dev`** / **`scripts/diagnostics/`** (shim dirs removed in **Pass 24**).

### Scope D — Repo-root wrappers (classification)

| Path | Label | Notes |
|------|--------|-------|
| `clean_bytecode_cache.py` | **keep_root_wrapper** | Thin entry → `scripts.dev.clean_bytecode_cache` |
| `run_ml_static_scan.py` | **keep_root_wrapper** | Thin entry → `scripts.dev.run_ml_static_scan` |
| `run_tests.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/run_tests.sh` (`make test`) |
| `run_tests_full.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/run_tests_full.sh` (`make test-full`) |
| `setup.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/bootstrap_venv.sh` |
| `run.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/launch_startup_menu.sh` |

### Scope E — Makefile

- **`clean`** is an alias for **`clean-bytecode`**, which invokes **`python scripts/dev/clean_bytecode_cache.py . --exclude venv --exclude .venv`** (same behavior as the former inline recipe).
- **`tree-source`** prints an optional source tree when the **`tree`** utility is installed; otherwise prints a hint and exits 0.

## Pass 13 (complete): fewer top-level doc/config files

| Item | Notes |
|------|-------|
| **`docs/AGENTS.md`** | **moved_now** — full agent/contributor instructions (replaces a long monolithic root **`AGENTS.md`**). |
| **`AGENTS.md` (root)** | **wrapper_kept** — short pointer to **`docs/AGENTS.md`** for tools that expect **`AGENTS.md`** at the repo root. |
| **`pytest.ini`** | **removed** — pytest defaults and **`slow`** marker moved to **`pyproject.toml`** **`[tool.pytest.ini_options]`** (same default selection and **`--basetemp=.pytest_tmp`**). |

## Pass 14 (complete): root wrapper audit + Makefile as operator default

### Makefile now calls canonical dev paths

| Target | Invokes | Notes |
|--------|---------|------|
| **`make test`** | **`./scripts/dev/run_tests.sh`** | **Pass 101:** repo-root **`run_tests.sh`** removed; invoke this path or **`make test`**. |
| **`make test-full`** | **`./scripts/dev/run_tests_full.sh`** | **Pass 101:** repo-root **`run_tests_full.sh`** removed. |
| **`make ml-scan`** | **`python -m scripts.dev.run_ml_static_scan`** | **Pass 101:** repo-root **`run_ml_static_scan.py`** removed; use **`-m`** (or `make ml-scan`). |
| **`make setup`** | **`./setup.sh`** | Wraps **`scripts/dev/bootstrap_venv.sh`**; Fedora-style venv + **`requirements.txt`**. |
| **`make menu`** | **`./run.sh`** | Wraps **`scripts/dev/launch_startup_menu.sh`**; prepends **`src/`** to **`PYTHONPATH`**. |
| **`make install-editable`** | **`python -m pip install -e .`** | Run with venv activated; registers **`obsidiandroid`** for imports outside pytest. |

### Root wrapper classification (deprecation-oriented)

| Path | Label | Rationale |
|------|--------|-----------|
| **`main.py`** | **keep** | CLI entry, monkeypatch surface, setuptools **`py-modules`**. |
| **`run.sh`** | **keep** | Operator muscle memory; prepends **`src/`** for menu runs without editable install. |
| **`setup.sh`** | **keep** | Same; wraps **`scripts/dev/bootstrap_venv.sh`**. |
| **`run_tests.sh`** / **`run_tests_full.sh`** | **wrapper_kept** | Thin **`exec`** to **`scripts/dev/*.sh`**; **Makefile** bypasses them. Safe **delete_later** only after external CI/docs stop referencing `./run_tests.sh` by name. |
| **`clean_bytecode_cache.py`** | **wrapper_kept** | **`make clean`** / **`clean-bytecode`** call **`scripts/dev/clean_bytecode_cache.py`** directly. Root module retained for **`pyproject.toml`** **`py-modules`** and **`python clean_bytecode_cache.py`** docs — **delete_later** only with a packaging/doc migration. |
| **`run_ml_static_scan.py`** | **wrapper_kept** | **`make ml-scan`** uses **`python -m scripts.dev.run_ml_static_scan`**. Root shim **delete_later** only after dropping **`run_ml_static_scan`** from **`py-modules`** and updating all doc examples. |

**Pass 101 update:** The four repo-root wrappers in the table above (**`run_tests.sh`**, **`run_tests_full.sh`**, **`clean_bytecode_cache.py`**, **`run_ml_static_scan.py`**) were **removed**; **`py-modules`** is **`main`** only; see Snapshot — **Dev tooling (Pass 101)**.

### Inspecting layout without noise

For reviews, run **`make clean-bytecode`** then **`make tree-source`** (requires **`tree`** on **`PATH`**). **`tree-source`** ignores **`.venv`**, **`output/`**, **`logs/`**, **`.pytest_*`**, **`__pycache__`**, common tool caches, **build/dist**.

### Tests

- After wrapper/layout changes, run **`make verify`** (import smoke + fast pytest).

## Pass 16 (complete): `obsidiandroid.diagnostics` facade (partial)

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/diagnostics/__init__.py`** | Re-exports **`output_inventory`**, **`output_artifact_policy`**, **`feature_lineage_report`** from **`analysis.diagnostics`** (same module objects). |
| **`scripts/dev/check_import_surface.py`** | Verifies facade submodule identity vs **`analysis.diagnostics.*`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **`test_diagnostics_facade_modules_match_analysis_diagnostics`**. |

Implementation code remains under **`analysis/diagnostics/`**; expand re-exports only after dependency review.

## Pass 17 (complete): PR gate + editor hygiene

| Item | Notes |
|------|-------|
| **`make verify`** | **`check_import_surface.py` + fast pytest** in one command; documented in **README**, **`docs/AGENTS.md`**, **`docs/developer_guide.md`**. |
| **`.editorconfig`** | Root-level: UTF-8, LF, 4-space Python, tab **Makefile**, 2-space YAML. |
| **`.gitattributes`** | `text=auto`; explicit **LF** for **`.py`**, **`.sh`**, **`.md`**, **YAML**. |

## Pass 18 (complete): CI, local parity, optional pre-commit

| Item | Notes |
|------|-------|
| **`.github/workflows/ci.yml`** | **`make verify`** + **`make ml-scan-strict`** on **`push` → `main`** and PRs; Python **3.12**, **`pip install -e .`**. |
| **`.github/dependabot.yml`** | Monthly **GitHub Actions** version bumps. |
| **`.pre-commit-config.yaml`** | Optional: trailing whitespace, EOF, YAML, large-file guard (use with **`pre-commit install`**; not run in CI). |
| **`make ml-scan-strict`** / **`make ci`** | Strict ML scan; **`ci`** = **`doc-check`** + **`verify`** + **`ml-scan-strict`** (older docs omitted **`doc-check`**; workflow includes it). |
| **README** | CI status badge for **`kevin-ch-day/obsidiandroid`**. |

## Pass 19 (complete): CI matrix, pip hygiene, Dependabot pip, Make UX

| Item | Notes |
|------|-------|
| **CI workflow** | **`workflow_dispatch`** (manual runs); **`permissions: contents: read`**; **pip cache** keys on **`requirements.txt`** + **`pyproject.toml`**; **`pip check`** after install; **Python 3.10 and 3.12** matrix (**`fail-fast: false`**). |
| **Dependabot** | **`pip`** ecosystem weekly on repo root **`requirements.txt`** (**`increase-if-necessary`**). |
| **Makefile** | **`.DEFAULT_GOAL := help`** — bare **`make`** prints targets. |
| **`.python-version`** | **`3.12`** — optional hint for **pyenv**/asdf (matches primary CI version). |
| **Root `AGENTS.md`** | One-line pointer to **`make ci`** / **`.github/workflows/ci.yml`**. |

## Pass 20 (complete): consolidated structure audit publication

| Item | Notes |
|------|-------|
| **`docs/ROOT_AND_STRUCTURE_AUDIT.md`** | Deep audit of repo root categories, hybrid-layout rationale, passes timeline, professionalism checklist, prioritized next phases. Linked from **`README.md`** and **`docs/README.md`**. |

## Pass 21 (complete): documentation pruning (phantom paths)

| Item | Notes |
|------|-------|
| **`docs/user_guide.md`** | Removed references to non-existent **`scripts/export_feature_snapshot.py`**, **`scripts/update_vendor_scores.py`**, and **`config/thresholds.json`**; pointed to real pipeline / **`scripts/report_*.py`** / **`make ml-scan`**. |
| **`docs/modeling_reference.md`** | Estimator table aligned with **`ml_classification/training/ml_trainers/`**; removed phantom **`ml_classification/models/`**, **`model_factory.py`**, **`utils/config_loader.py`**, **`analysis/evaluation/report_builder.py`**. |
| **`main.py`** | Dropped redundant **Filename/Purpose** header lines; kept module docstring. |

## Pass 22 (complete): operations / architecture doc alignment

| Item | Notes |
|------|-------|
| **`docs/operations_playbook.md`** | **Data freshness** bullets aligned with **`data_sources.md`** table names; **backfill** points to **`scripts/backfill_permission_trends_warehouse.py`** and states **`backfill_labels.py`** is not shipped. |
| **`docs/architecture.md`** | Removed non-existent **`config/thresholds.json`**; described **app_config** / **profiles** / **labeling** instead. |
| **`docs/code_review.md`** | Banner clarifying document is a **historical review snapshot** vs current **`analysis/pipeline/`** layout. |

## Pass 23 (complete): doc hygiene guardrail

| Item | Notes |
|------|-------|
| **`scripts/dev/check_doc_hygiene.py`** | Fails the build if allowlisted operator docs reintroduce known-removed paths (phantom scripts/modules). |
| **`make doc-check` / `make ci`** | Doc check runs before fast tests; **`.github/workflows/ci.yml`** runs **`make doc-check`** then **`make verify`**. |
| **`tests/test_doc_hygiene.py`** | Subprocess smoke: script exits **0** on the current tree. |

## Pass 24 (complete): remove `data_inspect/` and `devtools/` shims

| Item | Notes |
|------|-------|
| **Audit** | No in-tree production imports of **`data_inspect`** or **`devtools`**; only shims, tests, docs, and **`pyproject.toml`** referred to them. |
| **Deleted** | Entire **`data_inspect/`** and **`devtools/`** trees. |
| **`pyproject.toml`** | Removed **`data_inspect*`** and **`devtools*`** from **`[tool.setuptools.packages.find] include`**. |
| **Tests** | Removed **`tests/test_data_inspect_shim.py`**, **`tests/test_devtools_shim.py`**. |
| **Off-repo migration** | `from data_inspect import M` → `from scripts.diagnostics import M` (or `importlib.import_module("scripts.diagnostics." + name)`). `from devtools import data_fuzzer` → `from scripts.dev import data_fuzzer`. |

*Project briefs may call this work “Pass 14 (shim sunset)”; the migration plan numbers it **Pass 24** to follow **Pass 23**.*

## Pass 25 (complete): first physical moves into `src/obsidiandroid/`

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/common/export_naming.py`** | **Moved** from **`utils/exporting/naming.py`** (workbook / export naming helpers). **`utils/exporting/naming.py`** is a **shim** re-export. |
| **`src/obsidiandroid/cli/prompt_utils.py`** | **Moved** from **`utils/prompt_utils.py`**. **`utils/prompt_utils.py`** is a **shim**; **`obsidiandroid.cli.ui.menu`** imports the **canonical** module. |
| **`src/obsidiandroid/common/export_vendor_raw.py`** | **Moved** from **`utils/exporting/vendor_raw.py`**; shim at **`utils/exporting/vendor_raw.py`**. |
| **`src/obsidiandroid/common/export_workbook.py`** | **Moved** from **`utils/exporting/workbook.py`** (imports **`obsidiandroid.common.export_naming`**); shim at **`utils/exporting/workbook.py`**. |
| **`src/obsidiandroid/reporting/confusion_matrix_exporter.py`** | **Moved** from **`utils/confusion_matrix_exporter.py`**; **`utils/confusion_matrix_exporter.py`** is a **shim**. **`utils/export_manager.py`** imports the **canonical** reporting + common modules. |
| **`src/obsidiandroid/common/output_cleanup_clutter.py`** | Output-wipe glob constants (was **`utils/output_cleanup_clutter.py`**); **`scripts/fresh_pipeline_reset.py`** / **`scripts/cleanup_output_artifacts.py`** import canonical module (**`src/`** prepended at runtime). |
| **`src/obsidiandroid/common/av_detection_tiers.py`** | Tier labels / pandas helpers (unused in-tree but kept for notebooks); **`utils/av_detection_tiers.py`** shim. |
| **`make tree-obsidiandroid`**, **`tree-utils`**, **`tree-exporting-shims`** | Compare **`src/obsidiandroid`** growth vs legacy **`utils/`** (needs **`tree`** on **`PATH`**). |
| **`check_import_surface` / tests** | Parity checks for export helpers, confusion matrix export, cleanup constants, tiers, and **`prompt_yes_no`**. |

More **`utils/`** → **`obsidiandroid.*`** moves can follow the same pattern: implement under **`src/`**, keep a one-line **`utils/`** shim until imports are fully switched.

## Pass 26 (complete): `utils/` reduction — implementation + metrics

This pass is **not** documentation-only: modules were **moved** (canonical under **`src/obsidiandroid/`**, **`utils/`** shims kept), **`sample_metadata_preprocessor`** included after the audit. Dead **`utils/*.py`** pruning had **no new targets** (import-graph scan found **no** orphan top-level modules).

### Metrics (verified on working tree; `find … \| wc -l`)

Heuristic for **shim vs real** (top-level **`utils/*.py`** excluding **`__init__.py`**): **shim** = short compatibility module / delegates to **`obsidiandroid.*`** in the first lines; **real** = substantial implementation still in **`utils/`** (includes **`export_manager`**, **`display_utils`**, **`startup_menu`**, etc.).

| Metric | Before `sample_metadata_preprocessor` move (same tree minus canonical **`sample_metadata_preprocessor`**) | After (current tree) |
|--------|-------------------------------------------------------------------------------------------------------------|----------------------|
| **`utils/*.py` top-level files** | **29** | **29** |
| **`utils/**/*.py` total** | **46** | **46** |
| **Top-level shim-only** (heuristic) | **15** | **16** (**`sample_metadata_preprocessor`** became a shim) |
| **Top-level real implementation** (heuristic) | **13** | **12** |
| **`src/obsidiandroid/**/*.py`** | **44** | **45** (+**`common/sample_metadata_preprocessor.py`**) |
| **Modules moved into `src/obsidiandroid/` this step** | — | **1** (`sample_metadata_preprocessor`) |
| **`utils/*.py` files pruned (deleted)** | — | **0** (import sweep found **no** orphan top-level **`utils`** modules) |

*Interpretation:* **`utils/`** file counts stay flat while migrating because policy keeps **thin shims** at old import paths. Progress shows up as **fewer “real” modules under `utils/`** (by the heuristic above) and **more files under `src/obsidiandroid/`**. Use **`make tree-utils`** vs **`make tree-obsidiandroid`** to compare trees.

### Scope A — `utils/` classification (snapshot)

| Classification | Modules / paths |
|----------------|-----------------|
| **`shim_only`** | **`hash_utils`**, **`canonicalization`**, **`display_distribution`**, **`ml_console`**, **`path_safety`**, **`runtime_paths`**, **`evidence_mode_resolver`**, **`prompt_utils`**, **`confusion_matrix_exporter`**, **`output_cleanup_clutter`**, **`av_detection_tiers`**, **`compliance`**, **`latex_tables`**, **`sample_metadata_preprocessor`**, **`pipeline_entry`**, **`repo_import_paths`**, **`exporting/naming`**, **`exporting/vendor_raw`**, **`exporting/workbook`**, **`menu/*`**, **`ui/*`**. |
| **`dead_candidate`** | *(none newly identified this pass; **`evaluation_summary_printer`**, **`df_inspector`** removed in Pass 25.)* |
| **`common_candidate`** | **`sample_metadata_preprocessor`** ✅ **moved** to **`obsidiandroid.common`** (uses **`obsidiandroid.cli.ui.display`**). |
| **`reporting_candidate`** | **`latex_tables`** ✅ **moved**; **`family_distribution_report`** ✅ **moved** to **`obsidiandroid.reporting.family_distribution_report`** (runner imports canonical; **`utils.family_distribution_report`** shim kept). |
| **`governance_candidate`** | **`compliance`**, **`cohort_readiness_report`**, **`cohort_reproducibility`**, **`run_manifest`**, **`artifacts`** ✅ **moved** under **`obsidiandroid.governance.*`** (shims under **`utils/`**). |
| **`observability_candidate`** | **Historical (Pass 26 snapshot)** — superseded: **`obsidiandroid.observability.logging`** (Pass 30) and **`pipeline_observability`** (Passes 32–33); **`analysis/observability`** shim **removed** (Pass 33). |
| **`cli_candidate`** | **`profile_manager`** ✅ **moved** to **`obsidiandroid.cli.profile_manager`** (**`PROFILES_DIR`** = **`repo_root() / "profiles"`** in **`repo_paths`**); covered by existing **`menu/`**, **`ui/`** shims under **`utils/`**. |
| **`high_risk_postpone`** | **Historical snapshot** — **`export_manager`** ✅ Pass 29; **`logging/`** ✅ Pass 30. Large remaining risk is **domain-wide** moves (**`analysis/pipeline`**, …), not these modules. |
| **`needs_review`** | At Pass 26 snapshot: **`model_exporter.py`**, **`output_hygiene.py`** — both **moved** in **Pass 27** / **Pass 28**. |

### Scope B — Moved this pass

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/governance/compliance.py`** | **`utils/compliance.py`** |
| **`src/obsidiandroid/reporting/latex_tables.py`** | **`utils/latex_tables.py`** |
| **`src/obsidiandroid/common/sample_metadata_preprocessor.py`** | **`utils/sample_metadata_preprocessor.py`** |
| **`src/obsidiandroid/reporting/family_distribution_report.py`** | **`utils/family_distribution_report.py`** |
| **`src/obsidiandroid/cli/profile_manager.py`** | **`utils/profile_manager.py`** |
| **`src/obsidiandroid/governance/cohort_readiness_report.py`** | **`utils/cohort_readiness_report.py`** |
| **`src/obsidiandroid/governance/cohort_reproducibility.py`** | **`utils/cohort_reproducibility.py`** |
| **`src/obsidiandroid/common/output_paths.py`** | **`utils/output_paths.py`** |
| **`src/obsidiandroid/governance/run_manifest.py`** | **`utils/run_manifest.py`** |
| **`src/obsidiandroid/governance/artifacts.py`** | **`utils/artifacts.py`** |

**Internal imports updated:** **`analysis/pipeline/stage_manifest.py`** (`compliance`, **`LatexTableSpec`** / **`render_tabular`**), **`scripts/research/export_publication_tables.py`**, **`tests/test_latex_tables.py`**, **`analysis/pipeline/stage_samples.py`** (`prepare_sample_dataframe` from **`obsidiandroid.common.sample_metadata_preprocessor`**; **`cohort_readiness_report`** / **`cohort_reproducibility`** from **`obsidiandroid.governance.*`**), **`analysis/pipeline/runner.py`** (`family_distribution_report` from **`obsidiandroid.reporting`**; **`profile_manager`** from **`obsidiandroid.cli.profile_manager`**), **`obsidiandroid.cli.main`**, **`obsidiandroid.cli.menu.profile_preflight`**, **`scripts/check_cohort_foundation.py`** (prepend **`src/`** to **`sys.path`**), **`tests/test_profile_manager.py`** (imports canonical module so **`PROFILES_DIR`** monkeypatches apply to **`load_profile`**), **`tests/test_cohort_readiness_report.py`**, **`tests/test_cohort_reproducibility.py`** (canonical governance imports).

**Output paths / hygiene:** **`obsidiandroid.common.output_paths`** and **`obsidiandroid.common.output_hygiene`** are imported across **`analysis/pipeline/`**, **`utils/export_manager`**, **`utils/logging`**, **`ml_classification/`**, **`obsidiandroid.cli`**, **`scripts/`**, and tests (**`test_output_paths`**, **`test_output_hygiene_resolve`**). Legacy **`utils.output_hygiene`** remains a shim.

**Run manifest / artifact manifest:** **`obsidiandroid.governance.run_manifest`** (runner, manifest stages, orchestration, **`tests/test_manifest_pipeline.py`**, **`tests/conftest`** monkeypatch) and **`obsidiandroid.governance.artifacts`** (**`stage_manifest`**, **`paper_compliance_checks`**, **`tests/test_governance_primitives`**).

**Import ergonomics:** **`utils/display_utils.py`** re-exports **`obsidiandroid.cli.ui.display`** for legacy **`from utils import display_utils`** ( **`utils/ui/`** removed in **Pass 72** ).

### Scope C — Prune

No additional deletes this pass (prior **`rg`** audit showed no further zero-caller **`utils/`** roots beyond already-pruned files).

### Scope E — Gates

**`check_import_surface`**, **`tests/test_obsidiandroid_package_surface.py`**, fast **`pytest`**, **`doc-check`**.

## Pass 27 (complete): `model_exporter` → `obsidiandroid.modeling`

| Item | Status | Notes |
|------|--------|-------|
| **`src/obsidiandroid/modeling/model_exporter.py`** | **moved_now** | Joblib + JSON export; uses **`obsidiandroid.cli.ui.display`** for console messages and **`config.app_config`** for **`RUNTIME_RUN_ID`**. |
| **`utils/model_exporter.py`** | **wrapper_kept** | Thin shim: **`import *`** from **`obsidiandroid.modeling.model_exporter`** (after **`repo_import_paths`**). |
| **`ml_classification/training/prediction_builder.py`** | **updated** | Imports **`obsidiandroid.modeling.model_exporter`** (canonical). |
| **`tests/test_model_exporter_paths.py`** | **updated** | Canonical import (same **`app_config`** monkeypatch surface). |
| **`scripts/dev/check_import_surface.py`** | **updated** | Parity: **`utils.model_exporter.export_model_to_file`** is **`obsidiandroid.modeling.model_exporter.export_model_to_file`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **updated** | **`test_model_exporter_shim_matches_canonical`**. |

**Not in this pass:** **`utils/export_manager.py`**, **`utils/output_hygiene.py`**, **`utils/logging/`**, **`analysis/pipeline/`**, broad **`ml_classification/training/`** moves, **`database/`**, **`model/`**.

### Metrics (same heuristic as Pass 26; verified after Pass 27)

| Metric | After Pass 26 | After Pass 27 |
|--------|----------------|---------------|
| **Top-level shim-only** (`utils/*.py`, heuristic) | **16** | **17** (**`model_exporter`** is a shim) |
| **Top-level real implementation** (heuristic) | **12** | **11** |
| **`src/obsidiandroid/**/*.py`** | **52** (tree before this pass) | **53** (+**`modeling/model_exporter.py`**) |

### Scope A — classification delta

- **`shim_only`**: add **`model_exporter`**.
- **`needs_review`**: **`model_exporter`** ✅ **Pass 27**; **`output_hygiene`** ✅ **Pass 28**.

### Scope B — canonical / shim pair

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/modeling/model_exporter.py`** | **`utils/model_exporter.py`** |

## Pass 28 (complete): `output_hygiene` → `obsidiandroid.common`

| Item | Status | Notes |
|------|--------|-------|
| **`src/obsidiandroid/common/output_hygiene.py`** | **moved_now** | Run-scoped vs global **`output/diagnostics`** mirrors; uses **`obsidiandroid.common.output_paths`** and **`config.app_config`**. |
| **`utils/output_hygiene.py`** | **wrapper_kept** | Thin shim: **`import *`** from **`obsidiandroid.common.output_hygiene`**. |
| **`analysis/pipeline/`** (runner, manifest, ablation, sample exports, vendor metadata) | **updated** | **`from obsidiandroid.common import output_hygiene as oh`**. |
| **`analysis/diagnostics/`** (`output_inventory`, feature drop trace) | **updated** | Canonical **`output_hygiene`** imports. |
| **`analysis/orchestration/runtime_reporting.py`** | **updated** | Canonical import. |
| **`obsidiandroid.cli.startup_menu`** | **updated** | Canonical import. |
| **`ml_classification/training/model_trainer_factory.py`** | **updated** | Canonical import. |
| **`tests/test_output_hygiene_resolve.py`** | **updated** | Canonical import. |
| **`scripts/dev/check_import_surface.py`** | **updated** | Parity on **`resolve_stable_output_root_for_mirrors`** and **`mirror_csv_text_run_then_global`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **updated** | **`test_output_hygiene_shim_matches_canonical`**. |

**Not in this pass:** **`utils/logging/`**, physical **`analysis/pipeline/`** tree move, broad **`ml_classification/training/`**, **`database/`**, **`model/`**. (**`export_manager`** moved in **Pass 29** below.)

### Metrics (heuristic; after Pass 28)

| Metric | After Pass 27 | After Pass 28 |
|--------|----------------|---------------|
| **Top-level shim-only** | **17** | **18** (**`output_hygiene`**) |
| **Top-level real implementation** | **11** | **10** |
| **`src/obsidiandroid/**/*.py`** | **53** | **54** (+**`common/output_hygiene.py`**) |

### Scope B — canonical / shim pair

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/common/output_hygiene.py`** | **`utils/output_hygiene.py`** |

## Consolidation (complete): metadata feature frame

| Item | Notes |
|------|-------|
| **`analysis/pipeline/sample_preparation`** | **Canonical** home for **`build_metadata_feature_frame`** and **`extract_vt_tag_count`** (used by **`stage_feature_enrichment`**). |
| **`analysis/orchestration/metadata_features.py`** | **Thin re-export** of the same functions for backward-compatible imports; **`tests/test_main_metadata_features.py`** imports the canonical module. |

## Dead-code pruning (ongoing)

| Item | Notes |
|------|-------|
| **`ml_classification/vectorization/label_decoder_utils.py`** | **Removed** — **never imported**; label decoding uses **`LabelEncoder`** / builder paths elsewhere. |
| **`ml_classification/training/compare_models.py`** | **Removed** — **never imported**; experimental multi-model compare helper only. |
| **`ml_classification/training/model_runner_helpers.py`** | **Removed** — only imported by **`compare_models.py`** (also removed); production training uses **`train_model_executor`**. |
| **`analysis/evaluation/random_forest_performance_report.py`** | **Removed** — **no** imports/docs; standalone **`__main__`** helper superseded by **`random_forest_diagnostics`** / ML reporting paths. |
| **`analysis/evaluation/vendor_classification_scoring.py`** | **Removed** — **never imported**; workflow duplicated by **`evaluate_av_classifications`** + pipeline scoring stages. |
| **`model/parsing/vendor_parse_result.py`** | **Removed** — **`VendorParseResult`** unused; no references outside the file. |
| **`model/vendor/record_exporter.py`**, **`record_debugger.py`** | **Removed** — **never imported**; debugging/export helpers redundant with **`record_core`** / validators. |
| **`analysis/av_feature_engineering.py`** | **Removed** — **no** imports or doc references; overlapped conceptually with **`analysis/feature_engineering/compute_vendor_scores.py`** (the supported scoring path). |
| **`analysis/orchestration/manifest_finalize.py`** | **Removed** — **never imported**; run manifest finalization lives in **`analysis/pipeline/stage_manifest.py`** (**`finalize_run_manifest_stage`**). |
| **`utils/evaluation_summary_printer.py`** | **Removed** — nothing imported it; evaluation UX lives in **`ml_classification/reporting/`** and exporters. **`docs/modeling_reference.md`** updated. |
| **`utils/df_inspector.py`** | **Removed** — interactive dataframe inspector had **no** in-repo callers. |

## Pass 29 (complete): `export_manager` canonical under `obsidiandroid.reporting`

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/reporting/export_manager.py`** | **moved_now** — Excel/vendor/confusion-matrix export orchestration (formerly **`utils/export_manager.py`** body). Imports **`obsidiandroid.cli.ui.display`**, **`obsidiandroid.common.*`**, **`obsidiandroid.observability.logging`** (**Pass 30**). |
| **`utils/export_manager.py`** | **wrapper_kept** — replaces **`sys.modules['utils.export_manager']`** with the canonical module object so **`from utils import export_manager`** and **`obsidiandroid.reporting.export_manager`** are **identical** (monkeypatch + **`tests/test_export_manager_wiring.py`** stable). |
| **Call sites** | **updated** — **`pipeline_core`**, **`score_av_engines`**, **`evaluate_av_classifications`**, **`vendor_feature_extractor`**, **`classification_label_resolver`**, **`ml_eval_engine`** use **`from obsidiandroid.reporting import export_manager`**. |
| **`scripts/dev/check_import_surface.py`** | **updated** — asserts module identity + **`export_dataframe_to_excel`** binding. |
| **`obsidiandroid.reporting` package** | **updated** — re-exports **`export_manager`** submodule in **`__all__`**. |

**Deferred:** splitting **`export_manager`** into smaller modules.

## Pass 30 (complete): `utils/logging` canonical under `obsidiandroid.observability.logging`

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/observability/logging/logger.py`** | **moved_now** — structured category loggers (**`get_logger`**, **`log_event`**, **`close_all_loggers`**). |
| **`src/obsidiandroid/observability/logging/runtime.py`** | **moved_now** — stdout/stderr tee (**`start_runtime_logging`**, **`stop_runtime_logging`**, **`RuntimeLogContext`**). |
| **`src/obsidiandroid/observability/logging/__init__.py`** | **moved_now** — exports **`get_logger`**, **`log_event`**, plus **`logger`** / **`runtime`** submodules for **`from … import logger as logger_manager`**. |
| **`utils/logging/`** | **wrapper_kept** — thin **`repo_import_paths`** + **`import *`** / re-export shims to canonical modules (no **`sys.modules`** alias). |
| **Call sites** | **updated** — CLI **`main`**, **`runner`**, pipeline stages, ML training, **`database/db_engine`**, **`export_manager`**, tests use **`obsidiandroid.observability.logging`**. |
| **`scripts/dev/check_import_surface.py`** | **updated** — parity on package + **`logger`** + **`runtime`** submodules. |
| **`tests/test_obsidiandroid_package_surface.py`** | **updated** — shim parity tests for **`utils.logging`**. |
| **`obsidiandroid.observability` package** | **updated** — re-exports **`get_logger`**, **`log_event`** for **`from obsidiandroid.observability import …`**. |
| **Pipeline / ML import hygiene** | **updated** — **`utils.hash_utils`** / **`utils.runtime_paths`** in **`analysis/`** and **`ml_classification/labeling/`** → **`obsidiandroid.common.*`** (fewer hot-path **`utils.*`** dependencies). |

**Deferred (historical note):** Pipeline observability moved to **`obsidiandroid.observability.pipeline_observability`** (Pass 32); the **`analysis/observability`** shim directory was **removed** (Pass 33). This pass delivered **`utils/logging`** → **`obsidiandroid.observability.logging`** only.

## Pass 31 (complete): canonical **`display`** / **`ml_console`** imports (implementation hygiene)

| Item | Notes |
|------|-------|
| **Display** | **`analysis/`**, **`database/`**, **`ml_classification/`**, **`model/`**, **`scripts/`**, **`src/obsidiandroid/cli/menu/`** — **`from utils import display_utils as du`** → **`from obsidiandroid.cli.ui import display as du`**. |
| **ML console** | Same trees — **`from utils import ml_console`** → **`from obsidiandroid.common import ml_console`**. |
| **`utils.display_utils` / `utils.ml_console`** | **Shims kept** — thin re-exports only. |
| **`tests/test_display_utils.py`** | Imports canonical **`obsidiandroid.cli.ui.display`**. Shim parity: **`test_obsidiandroid_package_surface`**, **`test_obsidiandroid_common_shims`** ( **`ml_console as ml_shim`** unchanged). |
| **`scripts/dev/check_import_surface.py`** | Asserts **`print_table`** and **`is_minimal`** shim parity. |
| **`obsidiandroid.observability.pipeline_observability.logging_audit`** | Terminal sink paths documented for audit artifacts (replaces legacy **`analysis/observability/logging_audit`** shim). |

## Pass 32 (complete): **`analysis/observability`** → **`obsidiandroid.observability.pipeline_observability`**

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/observability/pipeline_observability/`** | **moved_now** — **`taxonomy`**, **`session`**, **`api`**, **`logging_audit`**, **`finalize`**, **`run_health`** (same behavior as former **`analysis/observability/`**). |
| **`analysis/observability/*.py`** | **wrapper_kept** at Pass 32 — thin shims (**removed** in Pass 33; use **`obsidiandroid.observability.pipeline_observability`** only). |
| **Call sites** | **updated** — **`runner`**, **`stage_av_vendor`**, **`stage_manifest`**, **`stage_ablation`**, **`research_validity/bundle`**, **`hostile_audit/bundle`**, observability tests use **`obsidiandroid.observability.pipeline_observability.*`**. |
| **`scripts/dev/check_import_surface.py`** | **Thin shim policies:** repo-root **`utils/*.py`** (exclude **`repo_import_paths`**, **`export_manager`**, **`startup_menu`**, **`__init__.py`**), **`utils/exporting`** leaf modules (exclude aggregating **`__init__.py`**), **`utils/logging`** — max line counts, required **`utils.repo_import_paths`** + canonical substring, no module-level **`def`/`class`**. **UTF-8 BOM scan:** no **`*.py`** under the repo (excluding skipped dirs) may start with a BOM — breaks **`ast.parse`** and tooling. |
| **`tests/test_obsidiandroid_package_surface.py`** | **`test_thin_compat_shim_trees_follow_policy`**, **`test_python_sources_have_no_utf8_bom_prefix`**. |

## Pass 33 (complete): remove **`analysis/observability`** shim package (breaking for old import path)

| Item | Notes |
|------|-------|
| **`analysis/observability/`** | **delete_later → deleted** — implementation already lived under **`obsidiandroid.observability.pipeline_observability`**; in-repo callers did not import **`analysis.observability`**. |
| **`scripts/dev/check_import_surface.py`** | Dropped **`analysis.observability.api`** parity check and thin-shim policy for that directory. |
| **Docs** | **`AGENTS.md`**, **`docs/architecture.md`**, **`docs/pipeline_staging_guide.md`**, **`ROOT_AND_STRUCTURE_AUDIT.md`** — document **`obsidiandroid.observability.pipeline_observability`** as the only supported import path for pipeline observability APIs. |
| **Implementation hygiene** | **`ml_classification/training/model_trainer_factory.py`** and **`tests/test_governance_primitives.py`** — **`from utils import canonicalization`** / **`path_safety`** → **`obsidiandroid.common`**. |

## Pass 34 (complete): **`obsidiandroid.diagnostics`** facade + operator / pipeline imports

| Item | Notes |
|------|-------|
| **`obsidiandroid.diagnostics`** | Re-exports **`alignment_gap_diagnostics`**, **`feature_builder_drop_trace`**, **`feature_matrix_gap_lineage`**, **`feature_lineage_report`**, **`output_artifact_policy`**, **`output_inventory`** (same module objects as **`analysis.diagnostics.*`**). |
| **`scripts/report_output_inventory.py`** | **`from obsidiandroid.diagnostics import output_inventory`**; prepends repo **`src/`** to **`sys.path`**. |
| **`scripts/report_feature_lineage.py`** | **`from obsidiandroid.diagnostics import feature_lineage_report`**; **`src/`** + repo root on **`sys.path`**. |
| **`scripts/diagnose_alignment_gap.py`**, **`scripts/trace_feature_builder_drops.py`**, **`scripts/report_feature_matrix_gap.py`** | Import via **`obsidiandroid.diagnostics`** (**`src/`** + repo root **`sys.path`**). |
| **`scripts/dev/check_import_surface.py`** | Loops over facade vs **`analysis.diagnostics.<module>`** identity for all six exports. |
| **`analysis/pipeline/stage_manifest.py`** | Lazy imports use **`from obsidiandroid.diagnostics import output_inventory`** for run summary + output hygiene bundle. |
| **`tests/test_output_inventory*.py`**, **`tests/test_obsidiandroid_package_surface.py`** | Prefer **`obsidiandroid.diagnostics`** for parity tests. |

## Pass 35 (complete): expand **`obsidiandroid.diagnostics`** (cohort + feature-build + ML training paths)

| Item | Notes |
|------|-------|
| **`obsidiandroid.diagnostics`** | Adds **`ablation_cohort_diagnostics`**, **`cohort_foundation_export`**, **`cohort_sample_id_audit`**, **`cohort_vocabulary`**, **`feature_build_coverage_export`**, **`feature_column_survival_export`**, **`fused_permission_matrix_audit`**, **`permission_training_survival_audit`** (same module objects as **`analysis.diagnostics.*`**). |
| **`analysis/pipeline/runner.py`**, **`stage_samples.py`**, **`stage_ablation.py`** | Import diagnostics via **`obsidiandroid.diagnostics`** (module attributes for callables). |
| **`ml_classification/training/pipeline_core.py`**, **`ml_classification/labeling/classification_label_resolver.py`** | Same. |
| **`scripts/dev/check_import_surface.py`**, **`tests/test_obsidiandroid_package_surface.py`** | Identity checks extended to all facade exports. |
| **Unit tests** | **`test_cohort_*`**, **`test_feature_build_coverage_export`**, **`test_feature_column_survival_export`**, **`test_fused_permission_matrix_audit`** use the facade. |

## Pass 36 (complete): **`research_validity`** + **`hostile_audit`** package façade (manifest + imports)

| Item | Notes |
|------|-------|
| **`obsidiandroid.diagnostics`** | Exposes **`research_validity`** and **`hostile_audit`** as the same package objects as **`analysis.diagnostics.research_validity`** / **`…hostile_audit`**; registers matching keys on **`sys.modules`** so paths like **`obsidiandroid.diagnostics.research_validity.cohort_funnel`** resolve to the **`analysis`** implementation. |
| **`analysis/pipeline/stage_manifest.py`** | Calls **`research_validity.write_research_validity_bundle`** (**`from obsidiandroid.diagnostics import research_validity`**) instead of lazy **`analysis.diagnostics.research_validity.bundle`**. |
| **`scripts/dev/check_import_surface.py`** | Verifies package + **`.bundle`** submodule identity for both trees. |
| **`tests/test_obsidiandroid_package_surface.py`** | Asserts package and bundle parity. |
| **`tests/test_cohort_funnel_finalize.py`**, **`tests/test_hostile_audit_bundle_smoke.py`** | Import via **`obsidiandroid.diagnostics.*`**. |

## Pass 37 (complete): diagnostics import sweep (tests + inventory + relative edges)

| Item | Notes |
|------|-------|
| **Tests** | All former **`from analysis.diagnostics import …`** in **`tests/`** now use **`obsidiandroid.diagnostics`** (six modules used by lineage/gap/feature tests). |
| **`analysis/diagnostics/output_inventory.py`** | Classifies artifacts via **`obsidiandroid.diagnostics.output_artifact_policy`** (same module object as façade). |
| **`analysis/diagnostics`** internals | Same-package **`from .…` / `from ..…`** for **`cohort_vocabulary`** and **`alignment_gap_diagnostics`** edges (foundation export, hostile cohort audit, **`research_validity.cohort_funnel`**, **`feature_matrix_gap_lineage`**). |

## Pass 38 (complete): **`obsidiandroid.database`** curated façade (Tier A+B+C)

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/database/__init__.py`** | Re-exports **12** **`database.*`** modules (same **`ModuleType`**); registers each **`obsidiandroid.database.<name>`** on **`sys.modules`** so submodule imports preserve identity. |
| **Tiers A–C** | **A:** **`settings`**, **`db_config`**, **`db_engine`**, **`db_errors`**, **`split_db_health`**. **B:** **`cohort_sql_fragments`**, **`db_sample_metadata_*`**. **C:** **`db_permission_analysis_queries`**, **`db_utils`**, **`schema_map`**. |
| **`scripts/dev/check_import_surface.py`** | Verifies façade + **`import obsidiandroid.database.<name>`** identity vs **`database.<name>`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **`test_database_facade_matches_database_modules`**. |
| **Callers** | **No** bulk migration — **`database.*`** remains valid. |

## Pass 39 (inventory): canonical DB import migration audit

**Purpose:** Record **where** `obsidiandroid.database` should be adopted next. This pass is **documentation + audit only** — **no** production caller migration, **no** behavior/env/connection changes, **no** façade expansion (Tier D needs a separate decision).

### Pass 38 façade recap (canonical modules)

These **12** `database.<name>` modules are re-exported with **identity** from **`obsidiandroid.database`**: **`cohort_sql_fragments`**, **`db_config`**, **`db_engine`**, **`db_errors`**, **`db_permission_analysis_queries`**, **`db_sample_metadata_contracts`**, **`db_sample_metadata_fetchers`**, **`db_sample_metadata_queries`**, **`db_utils`**, **`schema_map`**, **`settings`**, **`split_db_health`**.

### Imports outside Pass 38 (still `database.*` only)

Repo code also imports **`database`** modules **not** on the façade (Tier D–style analysts / AV helpers). Examples seen in **`analysis/matrix/*`**, **`analysis/evaluation/*`**, **`analysis/pipeline/*`** (`db_av_engine_detection_totals`, `db_av_engine_verdicts`), **`database/*.py`** internals, and dedicated tests. **Adopting `obsidiandroid.database` for those symbols requires a separate façade or “stay legacy” decision** — not implied by Pass 38.

### 1. Import inventory (by area)

Counts are **call sites** (import lines / lazy imports), not deduplicated by symbol. **“Façade OK”** means every database symbol used in that row is among the **12** Pass 38 modules.

| Area | Representative files | Typical `database` symbols | Façade OK? |
|------|---------------------|----------------------------|------------|
| **Pipeline / runtime** | **`analysis/pipeline/runner.py`**, **`stage_samples.py`**, **`stage_results_warehouse.py`**, **`score_av_engines.py`**, **`attach_engine_metadata.py`**, **`engine_pipeline_utils.py`**, **`permission_trends/sample_permission_data.py`**, **`feature_matrix_gap_lineage.py`** (lazy) | **`db_engine`**, **`db_sample_metadata_queries`**, **`db_sample_metadata_contracts`**; plus **`db_av_engine_detection_totals`** / related **AV** modules in some pipeline files | **Mixed** — façade symbols present; **AV** imports need Tier D or stay on `database.*` |
| **Diagnostics** | **`analysis/diagnostics/alignment_gap_diagnostics.py`**, **`cohort_foundation_export.py`**, **`feature_matrix_gap_lineage.py`** | **`db_config`** (`DB_NAME`, `PERMISSION_INTEL_DB_NAME`), **`db_engine`** (lazy / optional paths) | **Yes** |
| **Orchestration** | **`analysis/orchestration/permission_features.py`** | **`db_engine`** | **Yes** |
| **Matrix / enrichment** | **`analysis/matrix/av_binary_matrix_builder.py`**, **`enrich_malicious_scores.py`** | **`db_av_engine_verdicts`**, **`db_sample_malicious_scoring`** | **No** — not on façade |
| **Evaluation / fetch** | **`analysis/evaluation/av_results_fetcher.py`**, **`engine_scoring_summary.py`** | **`db_fetch_av_engine_raw_results`**, **`db_av_engine_detection_totals`** | **No** |
| **ML / `ml_classification/`** | *(no direct `database.*` imports found in audit)* | — | — |
| **`analysis/feature_engineering/`**, **`model/`**, **`obsidiandroid.reporting`** | *(none in audit)* | — | — |
| **Canonical CLI** | **`src/obsidiandroid/cli/startup_menu.py`**, **`cli/menu/profile_preflight.py`**, **`cli/menu/vendor_diagnostics.py`** | **`db_engine`**, **`db_sample_metadata_fetchers`** | **Yes** |
| **Tests** | **`tests/test_database*.py`**, **`test_cohort_*`**, **`test_profile_preflight.py`**, **`test_sample_metadata_*`**, **`test_db_av_*`**, **`test_vendor_data_determinism.py`**, **`test_obsidiandroid_package_surface.py`**, **`check_import_surface`** strings | Mix of façade + **AV** + dynamic `import database.db_config` | **Mixed** |
| **Scripts / tools** | **`scripts/check_cohort_foundation.py`**, **`scripts/diagnostics/inspect_*.py`**, **`scripts/research/generate_structural_diagnostics.py`** | **`db_engine`**, **`db_sample_metadata_queries`**, **`cohort_sql_fragments`**, **`db_sample_metadata_fetchers`** | **Mostly yes**; confirm per file before migrating |
| **`database/` package (implementation)** | All **`database/db_*.py`**, **`settings.py`**, **`split_db_health.py`**, etc. | Internal **`from database import …`** / **`from database.X import …`** | **N/A** — keep **package-internal** `database.*` imports; do **not** route implementation through `obsidiandroid.database` |

### 2. Risk classification (by group)

| Group | Tier | Notes |
|-------|------|--------|
| **New / refactored tests** (non-shim) | **Safe to migrate later** | Aligns with **Locked migration policy**; identity preserved via façade. |
| **`src/obsidiandroid/cli/*`** | **Safe to migrate later** | Already on canonical tree; low blast radius. |
| **Pipeline / diagnostics** using **only** façade symbols | **Safe to migrate later** | Schedule away from critical release windows; run **`make ci`** + DB smoke when touching execution paths. |
| **Scripts** (`scripts/`) | **Safe with review** | Operator-facing; migrate in small batches. |
| **Call sites using Tier D `database.db_*` (AV, timelines, etc.)** | **Defer** | Extend Pass 38 façade (**Tier D**) or document as **intentionally legacy** until boundary review. |
| **`database/*.py` internal imports** | **Do not migrate** (current architecture) | Keeps the implementation package self-contained and avoids circular “façade → database → façade” patterns. |
| **Mass pipeline edit across AV + cohort in one PR** | **Requires separate architectural decision** | Split by façade coverage and test matrix. |

### 3. Permission Intel boundary check

**Conclusion:** Pass 38 did **not** obscure primary vs Permission Intel behavior.

- **`db_engine`** (façade) is unchanged: separate connector kwargs for primary vs Permission Intel remain in **`database/db_engine.py`**.
- **`db_config`** (façade) still exports **`DB_NAME`** and **`PERMISSION_INTEL_DB_NAME`** with the same env semantics.
- **`db_permission_analysis_queries`** (façade) continues to qualify SQL with **`_primary()`** vs **`_permission_intel()`** using those config constants — behavior is **visible in the same module object** whether imported as `database.*` or `obsidiandroid.database.*`.
- **`split_db_health`** (façade) remains the **health / contract** entry for split-DB expectations.
- **`schema_map`** (façade) still reads **`DB_NAME`** from **`db_config`** as before.
- **`alignment_gap_diagnostics`** imports **`DB_NAME`** / **`PERMISSION_INTEL_DB_NAME`** for labeling only — no routing change.

### 4. Proposed migration order (future — not part of Pass 39 execution)

1. **Tests** that use **only** façade modules → `obsidiandroid.database` (train contributors; low risk).  
2. **`src/obsidiandroid/cli/*`** → façade imports.  
3. **Scripts** with façade-only symbols (e.g. cohort foundation, selected diagnostics).  
4. **`analysis/diagnostics`** (façade symbols only).  
5. **`analysis/pipeline`** files that use **only** façade symbols — **exclude** or **batch separately** any file that imports **non-façade** AV modules.  
6. **Evaluation / matrix** AV paths — only after **Tier D** façade decision or explicit “remain `database.*` forever” note.

### Audit method

Static search of **`*.py`** for **`from database`**, **`import database.`**, and **`from database import`** / **`import database`** (includes lazy imports). Repeat when DB surface grows.

### 5. Pass 39 deliverable status

- **This section** is the audit record. **No** broad caller rewrites in Pass 39 unless a follow-up explicitly approves a **trivial** subset (e.g. a single test file already under review).

## Pass 40 (complete): adopt **`obsidiandroid.database`** in low-risk outer layers

**Goal:** Exercise the canonical DB import path in **tests**, **canonical CLI**, **scripts**, and **one trivial pipeline import** — **no** **`database/*.py`** edits, **no** Tier D façade expansion, **no** behavior/env/connection changes.

### Files migrated (imports only; same **`ModuleType`**)

| Area | Files |
|------|--------|
| **Tests** | **`tests/test_database.py`** (incl. subprocess env assert via **`obsidiandroid.database.db_config`** + **`sys.path`** repo + **`src`**), **`test_cohort_sql_fragments.py`**, **`test_database_settings.py`**, **`test_db_errors.py`**, **`test_sample_metadata_query_layer.py`**, **`test_sample_metadata_fetchers.py`**, **`test_profile_preflight.py`**, **`test_cohort_loader_contract.py`** |
| **`obsidiandroid.cli`** | **`startup_menu.py`**, **`menu/profile_preflight.py`**, **`menu/vendor_diagnostics.py`** |
| **Scripts** | **`scripts/check_cohort_foundation.py`**, **`scripts/diagnostics/inspect_vendor_parser_health.py`**, **`scripts/diagnostics/inspect_vendor_column_opportunities.py`**, **`scripts/research/generate_structural_diagnostics.py`** |
| **Pipeline (single trivial line)** | **`analysis/pipeline/runner.py`** — **`db_sample_metadata_contracts`** only |

**Note:** Two **`scripts/diagnostics/*`** tools previously used **`parents[1]`** as “repo root”; corrected to **`parents[2]`** with **`src/`** added so **`obsidiandroid.database`** resolves reliably when run as scripts.

### Intentionally deferred / untouched

| Reason | Examples |
|--------|----------|
| **Non-façade DB symbols** | **`tests/test_vendor_data_determinism.py`** (`db_fetch_av_engine_raw_results`), **`tests/test_db_av_engine_verdicts_cache.py`** (`db_av_engine_verdicts`) |
| **Mixed / non-façade pipeline & analysis** | Matrix/evaluation AV paths (Pass 39 audit); façade-only **`analysis/`** subsets deferred during Pass 40 were migrated in **Pass 41**. |
| **`database/` implementation** | Internal **`from database …`** unchanged by policy |
| **Façade identity tests** | **`check_import_surface`** / **`test_obsidiandroid_package_surface`** still reference **`database.*`** module names where proving parity |

**Tier D policy:** Unchanged — no new façade modules in Pass 40.

## Pass 41 (complete): façade-only **`analysis/`** callers (diagnostics + selected pipeline)

**Goal:** Migrate remaining **non-`database/`** modules that imported **only** Pass 38 façade symbols (**Tier A–C**). Same rules as Pass 40: **no** `database/*.py` edits, **no** new façade exports, **no** behavior or connection changes.

### Files migrated (imports only)

| Area | Files |
|------|--------|
| **Diagnostics** | **`analysis/diagnostics/cohort_foundation_export.py`** (`db_config`), **`alignment_gap_diagnostics.py`** (`db_config`, lazy `db_engine`), **`feature_matrix_gap_lineage.py`** (lazy `db_engine`) |
| **Orchestration** | **`analysis/orchestration/permission_features.py`** (`db_engine`) |
| **Pipeline** | **`analysis/pipeline/stage_samples.py`** (`db_sample_metadata_queries`), **`stage_results_warehouse.py`**, **`score_av_engines.py`**, **`permission_trends/sample_permission_data.py`** (`db_engine`) |

### Intentionally deferred (unchanged policy)

| Reason | Examples |
|--------|----------|
| **Tier D / non-façade DB** | **`analysis/pipeline/attach_engine_metadata.py`**, **`engine_pipeline_utils.py`**, **`analysis/evaluation/*`**, **`analysis/matrix/*`** AV/scoring paths, **`tests/test_vendor_data_determinism.py`**, **`tests/test_db_av_engine_verdicts_cache.py`** |
| **`database/` implementation** | Internal **`from database …`** |
| **Parity / import-surface tooling** | **`check_import_surface`**, **`test_obsidiandroid_package_surface`** continue to reference **`database.*`** where identity is asserted |

**Tier D policy:** Still unchanged — Pass 41 does **not** expand the curated façade.

### Mixed-import note

No files in this pass imported both façade and non-façade **`database.*`** modules; those remain deferred until Tier D is decided or split cleanly.

## Pass 42 (complete): database façade adoption — **audit closed** (outside **`database/`**)

**Goal:** Record closure of façade-only **`from database`** migration for **non-implementation** trees and list **Tier D** holdouts. **No** new **`obsidiandroid.database`** exports in this pass.

### Audit result (repo-wide `*.py`)

| Caller bucket | **`obsidiandroid.database` eligible imports left?** |
|---------------|-----------------------------------------------------|
| **`scripts/`**, **`utils/`**, **`config/`**, **`ml_classification/`**, **`model/`**, **`src/obsidiandroid/`** | **None** (already canonical or never imported **`database`**). |
| **`analysis/`** (outside **`database/`**) | **None** for Tier **A–C**; **`database.*`** remains only where **Tier D** / scoring / AV modules are required — see below. |
| **`tests/`** | **Two** intentionally legacy **`database.*`** imports for **Tier D** symbols (**no** façade re-export yet). |

### **`database.*`** intentionally remaining (Tier D / non-façade)

| Path | Imported module(s) |
|------|--------------------|
| **`analysis/evaluation/av_results_fetcher.py`** | **`db_fetch_av_engine_raw_results`** |
| **`analysis/evaluation/engine_scoring_summary.py`** | **`db_av_engine_detection_totals`** |
| **`analysis/matrix/av_binary_matrix_builder.py`** | **`db_av_engine_verdicts`** |
| **`analysis/matrix/enrich_malicious_scores.py`** | **`db_sample_malicious_scoring`** |
| **`analysis/pipeline/attach_engine_metadata.py`** | **`db_av_engine_detection_totals`** |
| **`analysis/pipeline/engine_pipeline_utils.py`** | **`db_av_engine_detection_totals`** |
| **`tests/test_db_av_engine_verdicts_cache.py`** | **`db_av_engine_verdicts`** |
| **`tests/test_vendor_data_determinism.py`** | **`db_fetch_av_engine_raw_results`** |

**Superseded (Pass 43):** façade now includes the four Tier D modules above; callers listed here were migrated — see **Pass 43**.

## Pass 43 (complete): Tier D façade + final outer **`database.*`** migrations

**Goal:** Put the **narrow AV/scoring Tier D surface** used by **`analysis/`** and tests onto **`obsidiandroid.database`** and switch those callers (plus **`obsidiandroid.governance.run_manifest`**) to canonical imports — **same** **`ModuleType`** as **`database.<name>`**; **no** behavior change.

### Façade extensions

| Submodules added (Pass 43) |
|----------------------------|
| **`db_av_engine_detection_totals`**, **`db_av_engine_verdicts`**, **`db_fetch_av_engine_raw_results`**, **`db_sample_malicious_scoring`** |

Tooling **`scripts/dev/check_import_surface.py`** and **`tests/test_obsidiandroid_package_surface.py`** parity lists updated.

### Callers migrated (imports only)

| Area | Files |
|------|--------|
| **Evaluation** | **`analysis/evaluation/av_results_fetcher.py`**, **`engine_scoring_summary.py`** |
| **Matrix** | **`analysis/matrix/av_binary_matrix_builder.py`**, **`enrich_malicious_scores.py`** |
| **Pipeline** | **`analysis/pipeline/attach_engine_metadata.py`**, **`engine_pipeline_utils.py`** |
| **Tests** | **`tests/test_db_av_engine_verdicts_cache.py`**, **`tests/test_vendor_data_determinism.py`** |
| **Governance (`src`)** | **`obsidiandroid/governance/run_manifest.py`** |

### Deferred (unchanged architecture)

| Area | Notes |
|------|--------|
| **`database/*.py`** | Internal **`from database …`** / **`database.db_*`** imports **not** rewritten (implementation package stays self-contained). |
| **`check_import_surface` / façade tests** | Continue to **`import_module("database.[…]")`** when asserting **`is`** identity. |

### Post-pass audit

Aside from **`database/`** implementation internals and tooling strings that **`import`** **`database.*`** for parity checks, **repo `*.py`** no longer uses **`from database import …`** outside **`database/`**.

## Pass 44 (complete): **`tests/`** adopt canonical **CLI menu / UI** imports

**Goal:** Align non–shim-parity tests with **Locked migration policy** (prefer **`obsidiandroid.*`**). **`utils/menu/`** and **`utils/ui/`** were later **removed** (**Pass 72**) as unused stubs; **`tests/test_obsidiandroid_package_surface.py`** still imports **`utils.*`** where asserting **re-export identity** for remaining shims.

### Files migrated (imports only)

| File | Change |
|------|--------|
| **`tests/test_workbook_loader.py`** | **`obsidiandroid.cli.menu.workbook_loader`** |
| **`tests/test_vendor_diagnostics_menu.py`** | **`obsidiandroid.cli.menu.vendor_diagnostics`** |
| **`tests/test_ui_menu.py`** | **`obsidiandroid.cli.ui.menu`** |
| **`tests/test_menu_interrupts.py`** | **`obsidiandroid.cli.ui.menu`** |

**Intentionally unchanged:** shim parity blocks in **`tests/test_obsidiandroid_package_surface.py`**; remaining **`utils/*`** shim implementations (root leaves, **`exporting/`**, **`logging/`**).

## Pass 45 (complete): expand **`obsidiandroid.pipeline`** module aliases

**Goal:** Increase canonical import adoption without a physical move by teaching **`obsidiandroid.pipeline`** to expose commonly used **`analysis.pipeline.*`** modules as thin aliases (same module objects), then migrate low-risk tests.

### Façade additions

`obsidiandroid.pipeline` now resolves these names via lazy imports:

- `runner`, `main_facade`, `engine_normalization`, `score_av_engines`
- `attach_engine_metadata`, `av_engine_pipeline`, `vendor_metadata_pipeline`
- `stage_ablation`, `stage_av_vendor`, `stage_feature_enrichment`, `stage_manifest`, `stage_modeling`, `stage_permission_trends_report`, `stage_samples`

### Migrations in this pass

- Tests that used **`from analysis.pipeline import ...`** for the alias set now import from **`obsidiandroid.pipeline`**.
- Import-surface guardrails updated in **`scripts/dev/check_import_surface.py`**.
- Package-surface parity extended in **`tests/test_obsidiandroid_package_surface.py`**.

**Architecture unchanged:** implementation still lives under **`analysis/pipeline/`**; no behavior changes.

## Pass 46 (complete): ML façade inventory and boundary spec (docs-only)

**Goal:** Produce a complete **`ml_classification`** import inventory and readiness table before implementing any ML façade aliases.

Primary artifact:
- **`docs/ML_BOUNDARY_PLAN.md`** (Pass 46 inventory/spec)

Highlights:
- AST-based inventory over repo `*.py` documented in **`docs/ML_BOUNDARY_PLAN.md`**.
- Caller groups covered: pipeline, evaluation, diagnostics, vendor processing, CLI, scripts, tests, and **`ml_classification`** internals.
- Every unique import target tagged: **`ready_now`**, **`needs_wrapper`**, **`defer`**, or **`internal_only`** with proposed canonical placement.
- Research-critical contract table included for:
  - label normalization
  - family/type taxonomy resolution
  - vendor consensus parsing (explicitly deferred boundary; not assumed labeling-owned)
  - feature vector construction
  - training pipeline core
  - model trainer factory
  - evidence-strict / paper-mode behavior
  - dataset perturbation / ablation logic

Non-goals honored:
- No physical moves.
- No façade implementation or caller migration in this pass.
- No behavior, dataset/output, DB, or training-logic changes.

## Pass 47 (complete): first minimal ML façade slice (`ready_now` only)

**Goal:** Surface only Pass 46 `ready_now` rows as canonical module aliases with parity checks, no behavior changes.

### Aliases added

| Canonical facade | Alias name | Backing legacy module |
|---|---|---|
| `obsidiandroid.modeling` | `pipeline_core` | `ml_classification.training.pipeline_core` |
| `obsidiandroid.modeling` | `model_trainer_factory` | `ml_classification.training.model_trainer_factory` |
| `obsidiandroid.modeling` | `distribution_reporter` | `ml_classification.ml_utils.distribution_reporter` |
| `obsidiandroid.modeling` | `feature_label_alignment_helper` | `ml_classification.ml_utils.feature_label_alignment_helper` |
| `obsidiandroid.features` | `feature_vector_builder` | `ml_classification.vectorization.feature_vector_builder` |
| `obsidiandroid.labeling` | `classification_label_resolver` | `ml_classification.labeling.classification_label_resolver` |

### Guardrails updated

- `scripts/dev/check_import_surface.py`:
  - imports new facades
  - checks module-object parity (`is`) for each alias
  - checks `import obsidiandroid.<pkg>.<alias>` resolves to backing module
- `tests/test_obsidiandroid_package_surface.py`:
  - added ML facade parity test block for the same alias set

### Explicit deferrals (unchanged)

- All Pass 46 `needs_wrapper` rows
- All Pass 46 `defer` rows (including vendor consensus parsing boundary)
- All Pass 46 `internal_only` rows
- No caller migration in this pass
- No training behavior, dataset/output, evidence-strict/paper-mode, DB, or pipeline relocation changes

## Pass 48 (complete): low-risk ML caller adoption (`ready_now` aliases only)

**Goal:** Adopt Pass 47 canonical ML aliases in a small, controlled outer-caller batch.

### Files migrated (imports only; one-to-one replacements)

| Area | Files |
|---|---|
| Non-parity tests | `tests/test_stage_ablation.py`, `tests/test_model_trainer_factory.py`, `tests/test_feature_vector_builder.py`, `tests/test_classification_label_resolver_taxonomy_audit.py`, `tests/test_distribution_reporter.py`, `tests/test_runtime_policy_cross_run_cleanup.py` |
| Canonical CLI | `src/obsidiandroid/cli/startup_menu.py` |
| Small pipeline stages | `analysis/pipeline/stage_ablation.py`, `analysis/pipeline/stage_modeling.py`, `analysis/pipeline/stage_av_vendor.py` |

### Intentionally deferred in this pass

| File(s) | Reason |
|---|---|
| `tests/test_stage_feature_enrichment_fuse.py` | Mixed import surface (`feature_vector_builder` + `feature_encoder`); `feature_encoder` is Pass 46 `needs_wrapper`, so file left unchanged. |
| Vendor/evaluation inference/parsing modules | Pass 46 marked as `defer` (boundary ambiguity retained). |
| All `ml_classification` internals and `internal_only` rows | Out of scope by policy for low-risk outer adoption. |

### Non-goals honored

- No new façade aliases.
- No caller migration beyond this small batch.
- No ML logic, dataset/output contracts, evidence-strict/paper-mode behavior, DB behavior, or pipeline relocation changes.

## Pass 49 (complete): post-Pass 48 legacy import status/audit

**Goal:** Re-measure remaining legacy import surfaces after Pass 48 and recommend the
next high-ROI migration pass. This pass is **audit/docs only**: no aliases, no caller
migration, no physical moves, and no behavior/training/dataset/output changes.

### Reproducible method

Import counts used an AST scan over repo **`*.py`**, excluding generated/runtime paths
(`.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.pytest_tmp`, `output`, `logs`,
`obsidiandroid.egg-info`, `.ruff_cache`). Focused line scans used **`rg`**:

```bash
rg -n "^(from ml_classification|import ml_classification)" --glob "*.py" --glob "!ml_classification/**" .
rg -n "^(from analysis\.pipeline|import analysis\.pipeline)" --glob "*.py" --glob "!analysis/pipeline/**" .
rg -n "^(from utils|import utils)" --glob "*.py" --glob "!utils/**" .
rg -n "^(from model|import model)" --glob "*.py" --glob "!model/**" .
rg -n "^(from database|import database)" --glob "*.py" --glob "!database/**" .
```

### Import count snapshot

Counts are AST import records; file counts are unique files containing at least one
record for that root package.

| Import root | Records | Files | Interpretation |
|---|---:|---:|---|
| `obsidiandroid` | 548 | 273 | Canonical surface is now the dominant import root. |
| `analysis` | 301 | 75 | Still a large implementation and test surface, especially pipeline/diagnostics. |
| `database` | 45 | 16 | Remaining direct imports are inside repo-root `database/` implementation. |
| `ml_classification` | 88 | 48 | Includes package internals plus remaining external tests/eval/vendor-processing edges. |
| `model` | 37 | 31 | Vendor record / parsed metadata domain remains unfacaded. |
| `utils` | 94 | 51 | Mostly shim parity tests plus a few legacy test patch surfaces. |

### Focused remaining legacy surfaces

| Surface | Current status |
|---|---|
| Direct `database.*` outside `database/` | **0** found. |
| Direct `ml_classification.*` outside `ml_classification/` | **50** records: 9 surfaced-but-not-migrated, 12 `needs_wrapper`, 10 `defer`, 19 `internal_only`. Details are in **`docs/ML_BOUNDARY_PLAN.md`** Pass 49. |
| Direct `analysis.pipeline.*` outside `analysis/pipeline/` | Remains in diagnostics, scripts, `obsidiandroid.cli.main`, and tests. Mix of public-ish stage helpers, manifest/governance internals, and test monkeypatch/contract surfaces. |
| Direct `utils.*` outside `utils/` | Mostly shim/parity tests (`test_obsidiandroid_*_shims`, `test_obsidiandroid_package_surface`) plus a few legacy tests using `utils.export_manager`, `utils.pipeline_entry`, or `utils.family_distribution_report`. |
| Direct `model.*` outside `model/` | Vendor parsing/record domain is still shared across `analysis/vendor_processing`, `analysis/execution`, `ml_classification`, CLI diagnostics, and tests. Boundary belongs in a future vendor/model pass. |

### ML remaining-import classification

See **`docs/ML_BOUNDARY_PLAN.md`** for the per-file Pass 49 table. Summary:

| ML status | Records | Recommended handling |
|---|---:|---|
| `already surfaced alias but not migrated yet` | 9 | Good candidate for Pass 50A. |
| `needs_wrapper` | 12 | Do not surface casually; define wrapper contracts first. |
| `defer` | 10 | Mostly vendor/evaluation ambiguity; needs boundary design. |
| `internal_only` | 19 | Keep on legacy/internal paths unless tests are explicitly refactored. |

### Recommended next pass

Recommend **Pass 50A: second low-risk ML adoption batch**.

Rationale:
- There are still **9** remaining imports that already have Pass 47 canonical aliases.
- Candidate files are low risk when kept to one-to-one import replacements:
  **`analysis/evaluation/model_tuning.py`**, **`analysis/evaluation/random_forest_diagnostics.py`**,
  and straightforward tests that import only surfaced aliases.
- This proves the first ML façade slice in more callers without expanding API surface.

Defer:
- **Pass 50B** vendor/evaluation boundary inventory until surfaced aliases are fully adopted.
- **Pass 50C** utils cleanup until parity-test vs legacy-patch surfaces are split.
- **Pass 50D** pipeline external caller cleanup until pipeline facade submodule coverage is widened or classified.

## Pass 50A (complete): second low-risk ML adoption batch

**Goal:** Migrate only remaining imports that are already covered by Pass 47 aliases,
using one-to-one replacements. No new façade aliases, no physical moves, no caller
migration for mixed/high-risk files, and no behavior/training/dataset/output changes.

### Reproducible method

Before editing, an AST scan over repo **`*.py`** (excluding generated/runtime paths and
**`ml_classification/`** internals) matched only Pass 47 alias keys:

```python
("ml_classification.training", "pipeline_core")
("ml_classification.training", "model_trainer_factory")
("ml_classification.vectorization", "feature_vector_builder")
("ml_classification.labeling", "classification_label_resolver")
("ml_classification.ml_utils", "distribution_reporter")
("ml_classification.ml_utils", "feature_label_alignment_helper")
```

Focused line scan:

```bash
rg -n "^(from ml_classification|import ml_classification)" --glob "*.py" --glob "!ml_classification/**" .
```

### Files migrated

| Area | Files |
|---|---|
| Evaluation helpers | **`analysis/evaluation/model_tuning.py`**, **`analysis/evaluation/random_forest_diagnostics.py`** |
| Tests | **`tests/test_ablation_split_feature_columns.py`**, **`tests/test_export_manager_wiring.py`**, **`tests/test_pipeline_core_low_support_behavior.py`**, **`tests/test_pipeline_core_summary_exports.py`** |

**Pass 63 superseded direct-exec bootstrap:** **`model_tuning`** lives under **`src/obsidiandroid/evaluation/`**
and **does not** mutate **`sys.path`**. At Pass 50A, the file under **`analysis/evaluation/`** prepended
repo **`src/`** when run as a script; use **`pip install -e .`**, **`PYTHONPATH=…/src`**, or a thin wrapper
module if a direct script entry is required.

### Explicit skips

| File | Reason |
|---|---|
| **`tests/test_pipeline_contracts.py`** | Mixed import line/file: surfaced **`pipeline_core`** plus **`model_prediction`** (`internal_only`). |
| **`tests/test_stage_feature_enrichment_fuse.py`** | Mixed file: surfaced **`feature_vector_builder`** plus **`feature_encoder`** (`needs_wrapper`). |
| **`tests/test_training_trainer.py`** | Mixed file: surfaced **`model_trainer_factory`** plus algorithm-specific trainers (`internal_only`). |
| **`analysis/pipeline/runner.py`** | Explicitly out of scope; monkeypatch-sensitive / runtime-sensitive. |

Post-pass remaining surfaced aliases outside **`ml_classification/`**: **3**, all in
the mixed skipped files above. Details are mirrored in **`docs/ML_BOUNDARY_PLAN.md`**.

## Pass 50B (complete): vendor/evaluation boundary inventory

**Goal:** Map the vendor/evaluation/model parsing boundary before exposing anything
new under **`obsidiandroid.vendors`** or **`obsidiandroid.evaluation`**.

This pass is **docs only**: no new aliases, no caller migration, no physical moves,
and no behavior/parser/model/training/dataset/output/DB changes.

### Artifact

- **`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`**

### Reproducible method

Candidate files were listed with:

```bash
find analysis/vendor_processing analysis/evaluation analysis/execution model/vendor model/parsing ml_classification/engine_weights -maxdepth 2 -type f | sort
```

Focused text scan:

```bash
rg -n "vendor_processing|analysis\.evaluation|analysis\.execution|model\.vendor|model\.parsing|ml_classification\.engine_weights|risk_band_config|VendorClassificationRecord|ParsedLabelMetadata" --glob "*.py" --glob "!output/**" --glob "!logs/**" --glob "!**/__pycache__/**" .
```

Import inventory used an AST scan over repo **`*.py`**, excluding generated/runtime
paths (`.git`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.pytest_tmp`,
`output`, `logs`, `obsidiandroid.egg-info`, `.ruff_cache`) and matching these
prefixes:

```python
(
    "analysis.vendor_processing",
    "analysis.evaluation",
    "analysis.execution",
    "model.vendor",
    "model.parsing",
    "model.core.risk_band_config",
    "ml_classification.engine_weights",
)
```

### Inventory snapshot

| Metric | Count |
|---|---:|
| Import records | 81 |
| Proposed **`obsidiandroid.vendors`** records | 60 |
| Proposed **`obsidiandroid.evaluation`** records | 21 |

| Readiness tag | Records | Decision |
|---|---:|---|
| `ready_now` | 1 | Only **`analysis.vendor_processing.vendor_parser_map.get_vendor_parser_map`** is clearly alias-ready. |
| `needs_wrapper` | 37 | Vendor records, parsed metadata, generic parsing, and parser result contracts need stable wrappers. |
| `defer` | 38 | Evaluation/scoring/vendor-specific parser semantics need boundary decisions first. |
| `internal_only` | 5 | Execution builders/runners and record factories should remain implementation details. |
| `monkeypatch_sensitive` | 0 | Static scan found none, but tests still need manual patch-surface review before migration. |

### Boundary conclusions

| Area | Proposed canonical domain | Pass 50B status |
|---|---|---|
| Vendor parser maps | **`obsidiandroid.vendors`** | `ready_now` for the parser-map entrypoint only. |
| Generic/vendor-specific parsing | **`obsidiandroid.vendors`** | Generic parser `needs_wrapper`; vendor-specific parsers `defer`. |
| Vendor record model | **`obsidiandroid.vendors`** | `needs_wrapper`; do not expose raw record internals first. |
| Parsed label metadata | **`obsidiandroid.vendors`** | `needs_wrapper`; part of parser API, not labeling API by default. |
| AV result evaluation | **`obsidiandroid.evaluation`** | `needs_wrapper`/`defer`; result contract needs spec. |
| Engine scoring / engine weights | **`obsidiandroid.evaluation`** | `defer`; scoring policy is research-sensitive and not modeling-owned. |
| Parser quality checks | **`obsidiandroid.evaluation`** plus vendor entrypoints | `defer`; split quality/reporting from parser implementation first. |
| Risk band config | unresolved vendor/evaluation/risk domain | `defer`; appears adjacent but ownership is unsettled. |

### Recommended next choices

If continuing boundary migration, choose a tiny first **`obsidiandroid.vendors`**
facade slice for **`vendor_parser_map`** only. A broader vendors/evaluation facade
is not supported by the audit yet.

If prioritizing visible cleanup over a one-row facade, the stronger next choices are:

- pipeline external caller cleanup for already-approved pipeline facade imports
- utils non-parity test cleanup where tests are not asserting shim behavior

Defer the first **`obsidiandroid.evaluation`** facade slice until AV evaluation,
parser quality, scoring summary, and engine weight contracts are specified.

## Pass 51 (complete): first `obsidiandroid.vendors` facade slice

**Goal:** Implement only the Pass 50B `ready_now` vendor parser-map surface. No
vendor-specific parsers, generic parser wrapper, vendor record model, parsed label
metadata, evaluation aliases, physical moves, parser changes, output changes, or
DB behavior changes.

### Facade added

| Canonical module | Legacy backing module | Notes |
|---|---|---|
| **`obsidiandroid.vendors.vendor_parser_map`** | **`analysis.vendor_processing.vendor_parser_map`** | Thin alias with **`sys.modules`** registration so direct submodule imports preserve module identity. |

### Callers migrated

| Area | File | Change |
|---|---|---|
| Diagnostics script | **`scripts/diagnostics/inspect_vendor_column_opportunities.py`** | Imports **`get_vendor_parser_map`** from **`obsidiandroid.vendors.vendor_parser_map`**. |
| Tests | **`tests/test_vendor_parser_map.py`** | Imports **`vendor_parser_map`** from **`obsidiandroid.vendors`**. |

### Checks updated

- **`scripts/dev/check_import_surface.py`** imports **`obsidiandroid.vendors`** and
  verifies **`obsidiandroid.vendors.vendor_parser_map`** is the same module object as
  **`analysis.vendor_processing.vendor_parser_map`**.
- **`tests/test_obsidiandroid_package_surface.py`** adds the same package-surface
  parity assertion.

### Still deferred

- Generic parser wrapper and `parse_generic_classification`.
- Vendor-specific parser modules.
- `VendorClassificationRecord` and `ParsedLabelMetadata` canonical wrappers.
- `analysis.execution.*` record factories/runners.
- `obsidiandroid.evaluation` facade slice for AV evaluation, parser quality,
  scoring summaries, and engine weights.

## Pass 52 (complete): pipeline facade widening + small outer caller cleanup

**Goal:** Reduce remaining direct **`analysis.pipeline.*`** imports where the target
is a simple top-level pipeline module and the existing **`obsidiandroid.pipeline`**
facade pattern is sufficient. No physical moves, no runner refactor, no manifest /
governance subpackage facade, no behavior changes.

### Facade aliases added

| Canonical attribute | Legacy backing module |
|---|---|
| **`obsidiandroid.pipeline.sample_exports`** | **`analysis.pipeline.sample_exports`** |
| **`obsidiandroid.pipeline.sample_preparation`** | **`analysis.pipeline.sample_preparation`** |
| **`obsidiandroid.pipeline.stage_results_warehouse`** | **`analysis.pipeline.stage_results_warehouse`** |

These follow the existing Pass 45 lazy module-attribute pattern. Direct
**`import obsidiandroid.pipeline.<name>`** is not introduced in this pass; callers use
**`from obsidiandroid.pipeline import <module>`**.

### Callers migrated

| Area | File | Canonical module |
|---|---|---|
| Canonical CLI | **`src/obsidiandroid/cli/main.py`** | existing **`stage_av_vendor`**, **`stage_manifest`**, **`stage_samples`** facade modules |
| Script | **`scripts/check_cohort_foundation.py`** | **`sample_exports`** |
| Script | **`scripts/retrain_models_from_cached_alignment.py`** | **`stage_modeling`** |
| Script | **`scripts/backfill_permission_trends_warehouse.py`** | **`stage_results_warehouse`** |
| Test | **`tests/test_main_metadata_features.py`** | **`sample_preparation`** |
| Test | **`tests/test_parser_quality_contract.py`** | existing **`vendor_metadata_pipeline`** facade module |
| Analysis compatibility wrapper | **`analysis/orchestration/metadata_features.py`** | **`sample_preparation`** |
| Diagnostics helper | **`analysis/diagnostics/hostile_audit/permission_signal_quality.py`** | existing **`stage_feature_enrichment`** facade module |

The two scripts that did not already add repo **`src/`** to **`sys.path`** now do so
before importing **`obsidiandroid.pipeline`**, preserving checkout execution without
an editable install.

### Checks updated

- **`scripts/dev/check_import_surface.py`** verifies the new pipeline facade module
  attributes match their **`analysis.pipeline.*`** backing modules.
- **`tests/test_obsidiandroid_package_surface.py`** verifies the same package-surface
  parity.

### Still deferred

- **`analysis.pipeline.runner`** monkeypatch-sensitive imports.
- **`analysis.pipeline.manifest.*`**, **`governance.*`**, **`permission_trends.*`**,
  **`run_bounds`**, **`runtime_policy`**, and other subdomain modules pending a
  separate boundary/facade decision.

## Pass 53 (complete): utils non-parity test cleanup

**Goal:** Remove remaining **`utils.*`** imports from behavior tests where a canonical
**`obsidiandroid.*`** module already exists. Shim/parity tests and entry-shim tests
stay on legacy paths by design.

### Files migrated

| Test file | Old import | Canonical import |
|---|---|---|
| **`tests/test_export_manager.py`** | **`from utils import export_manager`** | **`from obsidiandroid.reporting import export_manager`** |
| **`tests/test_export_manager_wiring.py`** | **`from utils import export_manager`** | **`from obsidiandroid.reporting import export_manager`** |
| **`tests/test_hostile_regressions.py`** | **`from utils import export_manager`** | **`from obsidiandroid.reporting import export_manager`** |
| **`tests/test_main_stop_after_training.py`** | **`from utils import family_distribution_report`** | **`from obsidiandroid.reporting import family_distribution_report`** |

### Remaining direct `utils.*` imports outside `utils/`

Focused scan:

```bash
rg -n "^(from utils|import utils)" --glob "*.py" --glob "!utils/**" tests scripts src analysis ml_classification model database
```

Remaining rows are intentional:

| File | Reason |
|---|---|
| **`tests/test_obsidiandroid_common_shims.py`** | Shim parity test. |
| **`tests/test_obsidiandroid_governance_shims.py`** | Shim parity test. |
| **`tests/test_pipeline_entry.py`** | Entry-shim parity test for **`utils.pipeline_entry`**. |

Result: non-parity **`utils.*`** test cleanup is complete for the current scan.

## Pass 54 (complete): pipeline governance aliases

**Goal:** Move stable run-integrity governance primitives behind the existing
**`obsidiandroid.governance`** domain instead of leaving outer callers on nested
**`analysis.pipeline.governance.*`** paths. No behavior changes, no physical moves,
and no broad pipeline-governance package export.

### Facade aliases added

| Canonical module | Legacy backing module | Reason |
|---|---|---|
| **`obsidiandroid.governance.exceptions`** | **`analysis.pipeline.governance.exceptions`** | Typed stop/validation exceptions are governance primitives. |
| **`obsidiandroid.governance.integrity`** | **`analysis.pipeline.governance.integrity`** | Run-scoped artifact path enforcement is governance policy, not pipeline stage logic. |

The aliases preserve module identity through **`sys.modules`** registration.
Existing concrete governance modules such as **`artifacts`**, **`run_manifest`**,
**`compliance`**, **`cohort_readiness_report`**, **`cohort_reproducibility`**, and
**`evidence_mode_resolver`** remain canonical implementation modules under
**`src/obsidiandroid/governance/`**.

### Callers migrated

| File | Change |
|---|---|
| **`analysis/orchestration/runtime_reporting.py`** | Imports **`enforce_run_scoped_artifact_paths`** from **`obsidiandroid.governance.integrity`**. |
| **`tests/test_governance_integrity.py`** | Imports **`IntegrityStop`** and integrity helpers from **`obsidiandroid.governance.*`**. |

### Checks updated

- **`scripts/dev/check_import_surface.py`** verifies facade attribute identity and
  direct submodule import identity.
- **`tests/test_obsidiandroid_package_surface.py`** verifies the same package-surface
  parity.

### Still deferred

- **`analysis.pipeline.governance.policy`** and **`readiness`** pending a usage and
  boundary check.
- **`analysis.pipeline.manifest.*`**, **`permission_trends`**, and
  **`artifacts.registry`** pending separate facade decisions.

## Pass 55 (complete): pipeline policy/helper aliases

**Goal:** Continue reducing direct **`analysis.pipeline.*`** imports for stable
top-level helper modules that fit the existing **`obsidiandroid.pipeline`** facade.
No nested manifest/governance/permission-trends facade, no physical moves, no
runner refactor, and no behavior changes.

### Facade aliases added

| Canonical attribute | Legacy backing module | Reason |
|---|---|---|
| **`obsidiandroid.pipeline.contract_filters`** | **`analysis.pipeline.contract_filters`** | Cohort contract filters are stable top-level sample-stage helpers. |
| **`obsidiandroid.pipeline.run_bounds`** | **`analysis.pipeline.run_bounds`** | Typed run-bound snapshot helpers are stable top-level runtime helpers. |
| **`obsidiandroid.pipeline.runtime_policy`** | **`analysis.pipeline.runtime_policy`** | Profile/runtime policy helper surface already has direct tests. |

### Tests migrated

| Test file | Canonical module |
|---|---|
| **`tests/test_runtime_policy_cross_run_cleanup.py`** | **`obsidiandroid.pipeline.runtime_policy`** |
| **`tests/test_main_paper_perturbation_axes.py`** | **`obsidiandroid.pipeline.runtime_policy`** |
| **`tests/test_run_bounds.py`** | **`obsidiandroid.pipeline.run_bounds`** |
| **`tests/test_stage_samples_contract_filters.py`** | **`obsidiandroid.pipeline.contract_filters`** |

### Checks updated

- **`scripts/dev/check_import_surface.py`** verifies the new pipeline facade module
  attributes match their **`analysis.pipeline.*`** backing modules.
- **`tests/test_obsidiandroid_package_surface.py`** verifies the same package-surface
  parity.

### Still deferred

- **`analysis.pipeline.runner`** monkeypatch-sensitive test import.
- **`analysis.pipeline.manifest.*`**, **`permission_trends.*`**,
  **`artifacts.registry`**, and remaining nested domains pending a separate
  boundary/facade decision.

## Pass 56 (complete): pipeline manifest subfacade

**Goal:** Expose stable manifest helper modules through a dedicated
**`obsidiandroid.pipeline.manifest`** subpackage while keeping implementation files
under **`analysis/pipeline/manifest/`**. No physical moves, no manifest behavior
changes, no output/schema changes, and no runner refactor.

### Facade aliases added

| Canonical module | Legacy backing module | Reason |
|---|---|---|
| **`obsidiandroid.pipeline.manifest.hashing`** | **`analysis.pipeline.manifest.hashing`** | Deterministic manifest/evidence hashing helpers. |
| **`obsidiandroid.pipeline.manifest.writer`** | **`analysis.pipeline.manifest.writer`** | Atomic manifest writer helper. |
| **`obsidiandroid.pipeline.manifest.runtime_support`** | **`analysis.pipeline.manifest.runtime_support`** | Manifest runtime path/payload helpers used by stage manifest. |
| **`obsidiandroid.pipeline.manifest.paper_compliance_checks`** | **`analysis.pipeline.manifest.paper_compliance_checks`** | Paper/evidence compliance row builder. |
| **`obsidiandroid.pipeline.manifest.paper_figure_renderers`** | **`analysis.pipeline.manifest.paper_figure_renderers`** | Paper export figure helper surface. |

All aliases preserve module identity through **`sys.modules`** registration.

### Callers migrated

| File | Canonical path |
|---|---|
| **`analysis/pipeline/stage_manifest.py`** | **`obsidiandroid.pipeline.manifest.*`** |
| **`tests/test_manifest_pipeline.py`** | **`obsidiandroid.pipeline.manifest.hashing`**, **`writer`** |
| **`tests/test_paper_compliance_checks.py`** | **`obsidiandroid.pipeline.manifest.paper_compliance_checks`** |
| **`tests/test_stage_manifest.py`** | **`obsidiandroid.pipeline.manifest.paper_compliance_checks`** |
| **`tests/test_paper_figure_renderers.py`** | **`obsidiandroid.pipeline.manifest.paper_figure_renderers`** |

### Checks updated

- **`scripts/dev/check_import_surface.py`** verifies facade attribute identity and
  direct submodule import identity for the manifest aliases.
- **`tests/test_obsidiandroid_package_surface.py`** verifies the same package-surface
  parity.

### Still deferred

- **`analysis.pipeline.manifest.builder`** and **`schema`** until they have concrete
  outer usage that justifies canonical exposure.
- **`analysis.pipeline.permission_trends.*`** and **`analysis.pipeline.artifacts.*`**
  pending separate boundary decisions.
- **`analysis.pipeline.runner`** monkeypatch-sensitive test import.

## Pass 57 (complete): pipeline artifacts and permission-trends subfacades

**Goal:** Finish the remaining non-runner direct **`analysis.pipeline.*`** outer test
imports by exposing stable nested helper modules through canonical pipeline
subpackages. No behavior changes, no physical moves, no report/output changes.

### Facade aliases added

| Canonical package | Aliased modules | Legacy backing package |
|---|---|---|
| **`obsidiandroid.pipeline.artifacts`** | **`paths`**, **`registry`** | **`analysis.pipeline.artifacts`** |
| **`obsidiandroid.pipeline.permission_trends`** | **`bundle_manifest`**, **`constants`**, **`publish_paths`**, **`reporting_support`**, **`sample_permission_data`**, **`stats_core`** | **`analysis.pipeline.permission_trends`** |

All aliases preserve module identity through **`sys.modules`** registration.

### Tests migrated

| Test file | Canonical path |
|---|---|
| **`tests/test_artifact_registry.py`** | **`obsidiandroid.pipeline.artifacts.registry`** |
| **`tests/test_permission_trends_stats_core.py`** | **`obsidiandroid.pipeline.permission_trends.stats_core`** |

### Checks updated

- **`scripts/dev/check_import_surface.py`** verifies facade attribute identity and
  direct submodule import identity for both nested subfacades.
- **`tests/test_obsidiandroid_package_surface.py`** verifies the same package-surface
  parity.

### Remaining direct `analysis.pipeline.*` outside `analysis/pipeline/`

Focused scan:

```bash
rg -n "^(from analysis\.pipeline|import analysis\.pipeline)" --glob "*.py" --glob "!analysis/pipeline/**" .
```

Only **`tests/test_main_stop_after_training.py`** remains, intentionally importing
**`analysis.pipeline.runner`** as a monkeypatch-sensitive runtime surface.

## Pass 59 (complete): physical vendor parser move with compatibility shim

**Goal:** Physically relocate vendor parser implementations into canonical source layout while preserving legacy import compatibility and module identity.

### Physical move

Moved parser modules from **`analysis/vendor_processing/*.py`** to:

- **`src/obsidiandroid/vendors/parsing/*.py`**

### Compatibility approach

- Added **`src/obsidiandroid/vendors/parsing/__init__.py`** canonical package initializer.
- Added **`analysis/vendor_processing/__init__.py`** legacy shim that imports canonical modules and registers legacy names in **`sys.modules`**.
- Kept **`obsidiandroid.vendors.vendor_parser_map`** compatibility by aliasing to **`obsidiandroid.vendors.parsing.vendor_parser_map`**.

Identity contract now holds for key modules:

- **`obsidiandroid.vendors.parsing.vendor_parser_map`**
- **`analysis.vendor_processing.vendor_parser_map`**
- **`obsidiandroid.vendors.vendor_parser_map`**

and for parser helpers:

- **`generic_label_parser`**
- **`parser_defaults`**
- **`parser_confidence_estimator`**

### Canonical caller updates

Migrated active callers to **`obsidiandroid.vendors.parsing`** imports:

- **`src/obsidiandroid/cli/menu/vendor_diagnostics.py`**
- **`analysis/evaluation/vendor_parser_utils.py`**
- **`scripts/diagnostics/inspect_vendor_missing_patterns.py`**

### Validation

- **`python scripts/dev/check_doc_hygiene.py`**
- **`python scripts/dev/check_import_surface.py`**
- **`pytest -q tests/test_obsidiandroid_package_surface.py`**
- **`pytest -q tests/test_vendor_parser_map.py tests/test_vendor_data_determinism.py tests/test_vendor_diagnostics_menu.py tests/test_vendor_metadata_pipeline.py tests/test_parser_quality_contract.py tests/test_engine_normalization.py`**
- **`make ci`**

All passed.

## Pass 58 (complete): ML taxonomy wrapper + vendor/evaluation execution roadmap

**Goal:** Boundary hardening without broad physical moves: one **explicit ML wrapper**
for family taxonomy (**`needs_wrapper`** from **`docs/ML_BOUNDARY_PLAN.md`**), plus a
**practical execution checklist** for vendor vs evaluation canonical packages.

**Explicit non-goals:** No **`analysis/pipeline`** physical relocation; no change to
database implementation/façade policy (**`database.*`** internal, **`obsidiandroid.database`**
outer); no new shim layers under **`utils/`**; no **`sys.modules`** identity alias for
the taxonomy legacy module.

### ML: **`obsidiandroid.labeling.taxonomy`** (wrapper, tagged **`needs_wrapper` → implemented**)

| Public API | Implementation | Contract |
|---|---|---|
| **`normalize_family_name`**, **`is_known_family_name`**, **`canonicalize_family_label`** | Delegates to **`ml_classification.common.malware_family_constants`** | Wrapper functions are **not** the same objects as legacy callables (allows future indirection). |

**Not exported (by design):** **`KNOWN_FAMILIES`**, **`FAMILY_ALIASES`**, **`GENERIC_TOKENS`**, **`CANONICAL_FAMILY_DISPLAY`**. Vendor-oriented **`FAMILY_ALIASES`** remains on the legacy import path in **`generic_label_parser`** until a **`obsidiandroid.vendors`** contract absorbs it (**`defer`**).

**Adoption:** **`tests/test_label_quality_normalization.py`**, **`analysis/vendor_processing/generic_label_parser.py`** (split: taxonomy from wrapper, aliases from legacy).

**Verification:** **`scripts/dev/check_import_surface.py`**, **`tests/test_labeling_taxonomy_wrapper.py`**, **`tests/test_obsidiandroid_package_surface.py`**.

### Vendor / evaluation: roadmap doc expansion

**`docs/VENDOR_EVALUATION_BOUNDARY_PLAN.md`**: added **“Execution roadmap (Pass 58)”** with ordered tables for **`obsidiandroid.vendors`**, **`obsidiandroid.evaluation`**, **`internal_only`**, reporting/paper split, and deferred/coupled items.

### Next milestone hints (not Pass 58)

- ML: wrapper for **`feature_encoder`** (see **`docs/ML_BOUNDARY_PLAN.md`**); **`data_alignment`** and **`feature_schema_audit`** are physically canonical as of **Passes 90** and **89**.
- Vendors: **`needs_wrapper`** generic parser + parsed metadata + record surfaces before vendor-specific parser façades.
- Evaluation: first slice only after **`parse_vendor_classifications`** (or equivalent) I/O contract is frozen.

## Pre-Pass 38: hard-parts roadmap (planning only)

Ranked **design / code-debt** clusters that remain after diagnostics façades (Passes 34–37). Use this to sequence work without “moving files just to move files.”

| Rank | Problem | Why it is hard | Primary locations | Risk if ignored | Prerequisites to fix well | Blocks (migration of) |
|------|---------|----------------|-------------------|-----------------|----------------------------|------------------------|
| 1 | **`app_config` + `RUNTIME_*` global mutable state** | Run-scoped facts live on a process-wide object; hard to reason about ordering, concurrency, and tests; duplicates **`manifest_context`**. | **`config/app_config.py`**, **`config/settings/*`**, **`analysis/pipeline/runner.py`**, **`analysis/pipeline/runtime_policy.py`**, **`ml_classification/**/*`**, diagnostics | Hidden cross-run bleed, brittle tests, blocks safe in-process multi-run | Narrow **context slice** (IDs, dirs, bounds, obs session); explicit clear/reset policy; avoid new `RUNTIME_*` without dual-write plan | **Pipeline** (deep), **ML**, **eval** |
| 2 | **`analysis/pipeline` monolith + `runner` as monkeypatch hub** | Orchestration + policy + IO intertwined; **`analysis.pipeline.runner`** is a stable patch target. | **`analysis/pipeline/*.py`**, **`manifest/*`**, **`main_facade`** | Physical moves break tests and operator entrypoints | Import inventory; shim plan; optional **context** before big moves | **Pipeline** physical move, clean **ML** boundaries |
| 3 | **Dual state: `manifest_context` vs `app_config`** | Two sources of truth for run facts; easy to diverge. | **`runner.py`**, **`stage_manifest.py`**, **`runtime_policy.py`** | Wrong evidence in manifests / audits | Document “authoritative” keys per concern; converge over time | **Governance / evidence** |
| 4 | **`database` vs `obsidiandroid.database` ambiguity** | Two import paths to the same code; collides with mental model of “canonical.” | **`database/*`**, callers in **`analysis/`**, **`scripts/`**, **`tests/`** | Wrong imports in new code; accidental circular deps | **Thin façade** + documented rule: implementation stays top-level until retired | **Database** migration |
| 5 | **`ml_classification` mixed concerns** | Training, vectorization, labeling, eval share a tree without a sharp public API. | **`ml_classification/training/*`**, **`vectorization/*`**, **`labeling/*`**, **`ml_utils/*`** | Façade churn, unclear ownership | Target submodule map under **`obsidiandroid.modeling`** / **`features`** / **`labeling`** (façade-first) | **ML** |
| 6 | **Vendor: parsing / records / scoring spread** | Vendor logic in **`analysis/vendor_processing`**, **`model/`**, **`evaluation`**, **`engine_weights`**. | **`analysis/vendor_processing/*`**, **`model/*`**, **`analysis/evaluation/vendor_*`**, **`ml_classification/engine_weights`** | Duplicated contracts, hard refactors | Boundary doc + single **`obsidiandroid.vendors`** façade plan | **Vendor** |
| 7 | **Diagnostics vs reporting vs governance overlap** | Artifact writers and “paper” narratives touch multiple packages. | **`obsidiandroid.reporting/*`**, **`obsidiandroid.governance/*`**, **`obsidiandroid.diagnostics/*`**, **`analysis/orchestration`** | Misplaced features, review thrash | Short **ADR-style** rules (already aligned with operator stability) | **Diagnostics** “purity” optional |
| 8 | **`utils.export_manager` `sys.modules` alias** | Special case: not a thin shim file; patches may target **`utils.export_manager`**. | **`utils/export_manager.py`**, **`obsidiandroid.reporting.export_manager`** | Subtle test/import bugs if “fixed” carelessly | Dedicated pass: parity tests only, then migrate patch targets | **Reporting** shim retirement |
| 9 | **Shim sunset preconditions** | Retire only when callers, tests, docs meet locked policy. | **`utils/*`**, root **`main.py`** | Premature removal breaks operators | Checklist in **Locked migration policy** | **All** domains |

**Pass 38:** **Complete** — see Pass 38 table above; architecture spec retained below as reference.

---

## Pass 38 (architecture spec reference): `obsidiandroid.database` thin curated facade

This pass is **not** only about import ergonomics. The database boundary involves **connection state**, **environment configuration**, **logical separation between the primary Obsidian/Erebus schema and the Permission Intel schema** (today: same MySQL server, different `database=` names), and future **interop** extensions. Pass 38 defines a **stable canonical surface** without changing runtime behavior.

### High-level goal

Canonical imports:

```text
obsidiandroid.database
obsidiandroid.database.<curated submodule>   # identical ModuleType to database.<same name>
```

**Implementation home (Pass 38):** all logic remains in **`database/*.py`** at repo root. **`obsidiandroid.database`** re-exports **the same modules** documented in tiers below.

**Policy:** **New/internal code → `obsidiandroid.database`** (see **Locked migration policy**). **`from database …`** remains legitimate until a deliberate sunset phase.

### Architectural principles

| Principle | Pass 38 behavior |
|-----------|-------------------|
| **Identity** | Re-export **identical module objects** to **`database.<name>`** (no duplicated implementations). |
| **Connections** | **`database.db_engine`** remains authoritative for pooled/direct connections and Permission Intel connectors. Façade does not alter construction. |
| **Configuration** | **`database.db_config`** holds **`OBSIDIAN_*`-backed constants** (optional dotenv load). **`database.settings`** exposes **`ObsidianConnectionSettings`** / **`load_connection_settings()`**. |
| **Two logical databases** | Primary catalog/Erebus data vs **`PERMISSION_INTEL_DB_NAME`** Permission Intel tables — preserved as today in **`db_engine`** (`_build_connect_kwargs` vs `_build_permission_intel_connect_kwargs`). |
| **Future interop** (Erebus/Scytale, other backends) | **Out of scope** for Pass 38. Document **additive path**: evolve **`database/*`**, then widen **`obsidiandroid.database`** exports; **`ObsidianConnectionSettings`** may grow fields in a later pass — no premature service layer here. |
| **Logging / errors** | Re-export **`database.db_errors`** alongside engine; **`db_engine`** observability unchanged. |

### Non-goals

- Physical relocation of **`database/`** under **`src/`**.
- Repository/service layer injection (no dedicated run-context object layer in Pass 38).
- New env variable names or default database names (unless fixing a documented bug separately).
- Deprecating **`database.*`** imports in tooling or CI in this pass.
- Automatically re-exporting every **`database.db_*`** module (narrow surface by design).

### Curated façade tiers

**Tier A — boundary & health (Pass 38 required)**

| Canonical import | Role |
|------------------|------|
| **`obsidiandroid.database.settings`** | **`ObsidianConnectionSettings`**, **`load_connection_settings()`** |
| **`obsidiandroid.database.db_config`** | Env constants, pooling flags, timeouts, primary + PI DB names |
| **`obsidiandroid.database.db_engine`** | Connection factories, pooling, Permission Intel helpers |
| **`obsidiandroid.database.db_errors`** | Operator-facing summaries |
| **`obsidiandroid.database.split_db_health`** | **`preflight-db` / `-m database.split_db_health`** health entry |

**Tier B — cohort & sample-metadata SQL (Pass 38 required)**

| Canonical import | Role |
|------------------|------|
| **`obsidiandroid.database.cohort_sql_fragments`** | Shared cohort SQL |
| **`obsidiandroid.database.db_sample_metadata_contracts`** | Loader contracts / assertions |
| **`obsidiandroid.database.db_sample_metadata_fetchers`** | Fetch helpers |
| **`obsidiandroid.database.db_sample_metadata_queries`** | Metadata query surface |

**Tier C — auxiliary (same PR if low churn, else Pass 38.1)**

| Canonical import | Role |
|------------------|------|
| **`obsidiandroid.database.db_permission_analysis_queries`** | Permission-analytics queries |
| **`obsidiandroid.database.db_utils`** | Misc helpers |
| **`obsidiandroid.database.schema_map`** | Schema/name map |

**Tier D — narrow AV/analyst modules (Pass 43 subset on façade)**

These **same** **`database.<name>`** module objects are re-exported on **`obsidiandroid.database`** (identity parity with **`check_import_surface`**):

| Canonical import | Role |
|------------------|------|
| **`obsidiandroid.database.db_av_engine_detection_totals`** | Engine-level detection rollup for pipeline / scoring |
| **`obsidiandroid.database.db_av_engine_verdicts`** | Wide verdict fetches |
| **`obsidiandroid.database.db_fetch_av_engine_raw_results`** | Raw per-engine vendor matrix inputs |
| **`obsidiandroid.database.db_sample_malicious_scoring`** | Malicious score enrichment |

Other **`database.db_*`** helpers (e.g. **`db_sample_timelines_queries`**, **`db_extract_av_label_keywords`**, **`db_av_engine_stats`**) remain **implementation-only** until a caller needs **`obsidiandroid.database`** ergonomics — avoid widening the façade by default.

### Enforcement & gates

| Gate | Requirement |
|------|----------------|
| **Import surface** | Extend **`scripts/dev/check_import_surface.py`** to assert each exported submodule **`is`** the **`database.*`** counterpart. |
| **Tests** | Add parity tests in **`tests/test_obsidiandroid_package_surface.py`** for Tier **A+B** (and **C** if included). |
| **CI default** | **`make ci`** (no mandatory live DB socket for pure façade PR). |
| **Connection changes** | If **`db_engine`** / **`db_config`** behavior changes in the **same** PR, run **`make preflight-db`** / **`python -m database.split_db_health`** locally (existing project hygiene). |

### Caller migration & rollback

**Migration:** Façade can land **without** bulk-editing all **`from database`** call sites. Optional: migrate a **small** set of high-visibility internal imports to prove the pattern.

**Rollback:** Revert **`src/obsidiandroid/database/__init__.py`** and façade tests; **`database.*`** callers unaffected.

---

## Next pass suggestions

1. **Database surface:** **`obsidiandroid.database`** now includes **Passes 38 + 43** exports; **`python -m database.split_db_health`** etc. remain valid **`database`** module paths for CLI entry — see **Restructure backlog** for optional widenings (**`db_sample_timelines_queries`**, …).
2. **`obsidiandroid.diagnostics`:** physical move (optional) or remaining **`analysis.diagnostics`** caller sweep in non-test code.
3. **Re-export policy:** New tests → canonical imports; shims only for parity / monkeypatch (**Locked migration policy**).
4. **Move `analysis/pipeline`:** After façade + context plan; keep **`analysis.pipeline.runner`** shim during transition.
5. **Docs:** **`README.md`** / operator-facing quickstarts when **`obsidiandroid.*`** deserves first-class wording for external readers (**`docs/AGENTS.md`** already references the DB façade — Pass 42).
6. **Editable install:** CI already runs **`pip install -e .`** before **`make verify`**; refresh if workflow changes.
