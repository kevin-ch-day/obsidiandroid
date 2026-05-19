## Pass 46: ML boundary inventory and facade spec

This document is the Pass 46 docs-first inventory/spec for `ml_classification` import usage.

Scope of this pass:
- Inventory only (no code moves, no caller migrations, no behavior changes).
- Tag every imported `ml_classification` module/symbol as one of:
  - `ready_now`
  - `needs_wrapper`
  - `defer`
  - `internal_only`
- Propose canonical placement under:
  - `obsidiandroid.modeling`
  - `obsidiandroid.features`
  - `obsidiandroid.labeling`
  - or explicit defer to future `obsidiandroid.vendors` / `obsidiandroid.evaluation`.

Inventory source:
- AST scan across repo `*.py` for `import ml_classification...` and `from ml_classification... import ...`.
- Totals from this scan: 102 import records, 58 unique import targets.

## Caller-group inventory

| Caller group | Files | Import records | Notes |
|---|---:|---:|---|
| pipeline | 4 | 8 | `obsidiandroid.pipeline.runner`, `stage_modeling`, `stage_ablation`, `stage_av_vendor` consume training/vectorization/labeling helpers. |
| evaluation | 2 | 2 | `analysis/evaluation/*` uses trainer factory. |
| diagnostics | 1 | 2 | Feature-drop diagnostics import vendor feature extraction helpers. |
| vendor_processing | 1 | 3 | Generic parser imports family canonicalization constants. |
| CLI | 1 | 1 | Startup menu imports pipeline core launcher. |
| scripts | 0 | 0 | No direct `ml_classification` imports in scripts. |
| tests | 29 | 48 | Broad surface coverage across training/vectorization/labeling/eval helpers. |
| ml_classification internals | 20 | 38 | Internal coupling across builder/labeling/inference/training/reporting. |

## Readiness and canonical placement table

| Import target (module::symbol) | Primary callers | Status | Proposed canonical placement | Rationale |
|---|---|---|---|---|
| `ml_classification.training::pipeline_core` | CLI, pipeline, tests | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.modeling.pipeline_core` | Stable orchestration entry for training flow; already used by outer layers. |
| `ml_classification.training::model_trainer_factory` | pipeline, evaluation, tests | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.modeling.model_trainer_factory` | Core trainer selection boundary; high outer usage and clear ownership. |
| `ml_classification.vectorization::feature_vector_builder` | pipeline, tests | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.features.feature_vector_builder` | Direct feature construction API with clear domain fit. |
| `ml_classification.labeling::classification_label_resolver` | pipeline, tests | `ready_now` (**surfaced Pass 47**; physically moved **Pass 86**) | `obsidiandroid.labeling.classification_label_resolver` | Canonical label resolution entrypoint; research-critical taxonomy contract; legacy path is now an identity shim. |
| `ml_classification.ml_utils::distribution_reporter` | pipeline, tests | `ready_now` (**surfaced Pass 47**; physically moved **Pass 87**) | `obsidiandroid.modeling.distribution_reporter` | Training/eval artifact utility used by outer callers; the legacy package is now retired. |
| `ml_classification.ml_utils::feature_label_alignment_helper` | pipeline | `ready_now` (**surfaced Pass 47**; physically moved **Pass 87**) | `obsidiandroid.modeling.feature_label_alignment_helper` | Alignment contract between features and labels; outer-call surface exists; the legacy package is now retired. |
| `ml_classification.training::data_alignment` | tests, training internals | `needs_wrapper` → physically moved **Pass 90** | `obsidiandroid.modeling.data_alignment` | Label/feature alignment contract now lives on the canonical modeling surface; legacy training path is an identity shim. |
| `ml_classification.training::feature_schema_audit` | tests, training internals | `needs_wrapper` → physically moved **Pass 89** | `obsidiandroid.features.feature_schema_audit` | Feature schema audit helper now lives on the canonical feature surface; legacy training path is an identity shim. |
| `ml_classification.vectorization.feature_encoder::encode_features` | tests | `needs_wrapper` | `obsidiandroid.features.feature_encoder` | Feature encoding likely reusable; wrapper should lock defaults and params. |
| `ml_classification.vectorization.feature_engine_selection::get_top_engines_by_score` | tests | `needs_wrapper` | `obsidiandroid.features.feature_engine_selection` | Candidate API, but currently helper-shaped and threshold-sensitive. |
| `ml_classification.labeling::label_field_normalizer` | tests, internals | `needs_wrapper` | `obsidiandroid.labeling.label_field_normalizer` | Label normalization is research-critical; wrapper should freeze accepted input schema. |
| `ml_classification.labeling::label_format_generator` | tests | `needs_wrapper` | `obsidiandroid.labeling.label_format_generator` | External behavior should be documented before export. |
| `ml_classification.labeling.label_format_generator::generate_label` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_format_generator` | Same as above; function-level alias can follow module wrapper. |
| `ml_classification.labeling.label_input_validator::validate_label_resolution_inputs` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_input_validator` | Validation contract matters; currently internal. |
| `ml_classification.labeling.label_builder_wrapper::build_structured_label_output` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_builder_wrapper` | Output schema needs explicit versioning before broad adoption. |
| `ml_classification.labeling.label_postprocessor::summarize_prediction_results` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_postprocessor` | Summary semantics should be stabilized first. |
| `ml_classification.common.malware_family_constants::canonicalize_family_label` | tests, vendor processing | `needs_wrapper` → **Pass 58 wrapper**; implementation moved **Pass 85** | `obsidiandroid.labeling.taxonomy` | Public wrapper remains **`obsidiandroid.labeling.taxonomy`**; backing implementation now lives at **`obsidiandroid.labeling.malware_family_constants`** with legacy identity shim. |
| `ml_classification.common.malware_family_constants::normalize_family_name` | tests, vendor processing, internals | `needs_wrapper` → **Pass 58 wrapper**; implementation moved **Pass 85** | `obsidiandroid.labeling.taxonomy` | Same as above. |
| `ml_classification.common.malware_family_constants::is_known_family_name` | tests, vendor processing, internals | `needs_wrapper` → **Pass 58 wrapper**; implementation moved **Pass 85** | `obsidiandroid.labeling.taxonomy` | Same as above. |
| `ml_classification.common.malware_family_constants::FAMILY_ALIASES` | vendor processing | `defer` → physically canonical **Pass 85** | `obsidiandroid.labeling.malware_family_constants` | Raw alias map remains an implementation table; canonical vendor parser may import it directly, but public callers should prefer taxonomy wrapper functions. |
| `ml_classification.common.malware_family_constants::GENERIC_TOKENS` | internals | `internal_only` → physically canonical **Pass 85** | `obsidiandroid.labeling.malware_family_constants` | Internal heuristic token list; not part of the public taxonomy wrapper API. |
| `ml_classification.common::malware_family_constants` | internals | `internal_only` → legacy shim **Pass 85** | `obsidiandroid.labeling.malware_family_constants` | Legacy path preserved for ML internals until broader ML migration. |
| `ml_classification.inference.label_consensus_engine::resolve_consensus_label` | tests, internals | `defer` → physically moved **Pass 97** | `obsidiandroid.inference.label_consensus_engine` | Vendor consensus parsing remains a distinct inference domain; legacy path is now an identity shim. |
| `ml_classification.inference.malware_type_engine::infer_malware_type` | internals | `defer` → physically moved **Pass 97** | `obsidiandroid.inference.malware_type_engine` | Inference policy stays outside `obsidiandroid.labeling`; legacy path is now an identity shim. |
| `ml_classification.inference.threat_class_engine::infer_threat_class` | internals | `defer` → physically moved **Pass 97** | `obsidiandroid.inference.threat_class_engine` | Same domain split as above. |
| `ml_classification.inference.signal_health_checker::analyze_signal_health` | internals | `defer` → physically moved **Pass 97** | `obsidiandroid.inference.signal_health_checker` | Diagnostic metric engine moved with inference helpers; legacy path is now an identity shim. |
| `ml_classification.inference::signal_health_checker` | internals | `internal_only` → legacy facade **Pass 100** | `obsidiandroid.inference.signal_health_checker` | Namespace-level compatibility import resolves to the canonical submodule. |
| `ml_classification.vectorization.feature_vendor_extractor::extract_vendor_fields` | diagnostics | `defer` | `obsidiandroid.vendors` (future) | Vendor feature extraction belongs with vendor domain boundary work. |
| `ml_classification.vectorization.feature_vendor_extractor::merge_vendor_features` | diagnostics | `defer` | `obsidiandroid.vendors` (future) | Same as above. |
| `ml_classification.engine_weights::classification_weight_utils` | tests | `defer` → physically moved **Pass 98** | `obsidiandroid.engine_weights.classification_weight_utils` | Engine weighting kept out of modeling; canonical package is `obsidiandroid.engine_weights`, with legacy identity shim. |
| `ml_classification.engine_weights::compute_reliability_score` | tests | `defer` → physically moved **Pass 98** | `obsidiandroid.engine_weights.compute_reliability_score` | Same as above. |
| `ml_classification.engine_weights::engine_weights_utils` | tests | `defer` → physically moved **Pass 98** | `obsidiandroid.engine_weights.engine_weights_utils` | Same as above. |
| `ml_classification.ml_utils::ml_eval_engine` | tests, internals | `defer` → physically moved **Pass 94** | `obsidiandroid.evaluation.ml_eval_engine` | Evaluation implementation now lives under the canonical evaluation package; legacy path is an identity shim. |
| `ml_classification.ml_utils::ml_comparator_summary` | tests, internals | `defer` → physically moved **Pass 94** | `obsidiandroid.evaluation.ml_comparator_summary` | Comparison/reporting semantics are evaluation-facing and now physically canonical. |
| `ml_classification.reporting::ml_report_builder` | internals | `defer` → physically moved **Pass 94** | `obsidiandroid.evaluation.ml_report_builder` | Classification metrics/report builder is evaluation-owned; legacy reporting path is an identity shim. |
| `ml_classification.ml_utils::accuracy_band_utils` | tests, internals | `internal_only` → physically moved **Pass 94** | `obsidiandroid.evaluation.accuracy_band_utils` | Helper remains evaluation-internal but no longer lives under `ml_classification`. |
| `ml_classification.ml_utils::dataset_splitter` | internals | `internal_only` → physically moved **Pass 94** | `obsidiandroid.modeling.dataset_splitter` | Internal train/test split helper now lives with modeling; legacy path is an identity shim. |
| `ml_classification.ml_utils::feature_alignment_utils` | internals | `internal_only` → physically moved **Pass 88** | `obsidiandroid.modeling.feature_alignment_utils` | Implementation helper for canonical `feature_label_alignment_helper`; not promoted as a public facade entry. |
| `ml_classification.ml_utils::ml_result_analyzer` | internals | `internal_only` → physically moved **Pass 91** | `obsidiandroid.modeling.ml_result_analyzer` | Internal post-processing helper for training/evaluation display; canonical location prepares the training subtree move without promoting a broad public contract. |
| `ml_classification.ml_utils::ml_result_validator` | internals | `internal_only` → physically moved **Pass 91** | `obsidiandroid.modeling.ml_result_validator` | Internal result-structure validator; canonical location prepares the training subtree move while preserving legacy monkeypatch/import identity. |
| `ml_classification.training.model_trainer_factory::reset_runtime_training_caches` | pipeline | `internal_only` → physically moved **Pass 92** | `obsidiandroid.modeling.model_trainer_factory` | Runtime cache reset is internal operational control, exposed via canonical modeling module. |
| `ml_classification.training::training_helpers` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.training_helpers` | Internal training helper surface now lives under canonical modeling; legacy path is an identity shim. |
| `ml_classification.training::model_prediction` | tests | `internal_only` → physically moved **Pass 91** | `obsidiandroid.modeling.model_prediction` | Internal prediction helper module; canonical location keeps prediction/result helpers together ahead of larger training migration. |
| `ml_classification.training::train_model_executor` | tests, internals | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.train_model_executor` | Internal orchestration details; legacy path is an identity shim. |
| `ml_classification.training.ml_trainers::random_forest_trainer` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.ml_trainers.random_forest_trainer` | Algorithm-specific trainer remains internal but physically canonical; the legacy trainer package is now retired. |
| `ml_classification.training.ml_trainers::balanced_random_forest_trainer` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.ml_trainers.balanced_random_forest_trainer` | Internal trainer module; the legacy trainer package is now retired. |
| `ml_classification.training.ml_trainers::logistic_regression_trainer` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.ml_trainers.logistic_regression_trainer` | Internal trainer module; the legacy trainer package is now retired. |
| `ml_classification.training.ml_trainers::svm_trainer` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.ml_trainers.svm_trainer` | Internal trainer module; the legacy trainer package is now retired. |
| `ml_classification.training.ml_trainers::xgboost_trainer` | tests | `internal_only` → physically moved **Pass 93** | `obsidiandroid.modeling.ml_trainers.xgboost_trainer` | Internal trainer module; the legacy trainer package is now retired. |
| `ml_classification.builder.classification_row_builder::build_classification_row` | tests, internals | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.classification_row_builder` | Builder internals remain internal but physically canonical. |
| `ml_classification.builder.prediction_utils::extract_prediction_components` | internals | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.prediction_utils` | Internal helper logic; legacy path is an identity shim. |
| `ml_classification.builder.prediction_utils` | tests | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.prediction_utils` | Internal module import now resolves to canonical implementation. |
| `ml_classification.builder::prediction_utils` | tests | `internal_only` → legacy facade **Pass 100** | `obsidiandroid.classification_builder.prediction_utils` | Package-level compatibility import resolves to canonical implementation. |
| `ml_classification.builder.sample_classification_builder` | tests | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.sample_classification_builder` | Internal builder orchestration module now physically canonical. |
| `ml_classification.builder::sample_classification_builder` | tests, internals | `internal_only` → legacy facade **Pass 100** | `obsidiandroid.classification_builder.sample_classification_builder` | Package-level compatibility import resolves to canonical implementation. |
| `ml_classification.builder::classification_constants` | internals | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.classification_constants` | Internal constants now live with classification builder implementation. |
| `ml_classification.builder::vendor_record_selector` | tests | `internal_only` → physically moved **Pass 96** | `obsidiandroid.classification_builder.vendor_record_selector` | Internal builder selector helper; legacy path is an identity shim. |
| `ml_classification.labeling.label_field_normalizer::DEFAULT_TYPE` | tests | `internal_only` → physically moved **Pass 95** | `obsidiandroid.labeling.label_field_normalizer` | Constant-level internal coupling remains internal but now lives under canonical labeling implementation. |

## Research-critical contract map

| Contract area | Current implementation anchors | Proposed boundary owner | Status (Pass 46) | Notes |
|---|---|---|---|---|
| Label normalization | `ml_classification.labeling.label_field_normalizer`, `label_format_generator`, `classification_label_resolver` | `obsidiandroid.labeling` | `needs_wrapper` / partial `ready_now` | Keep resolver ready; wrap normalizer/format generator with explicit schema contract. |
| Family/type taxonomy resolution | `obsidiandroid.labeling.malware_family_constants`, `classification_label_resolver` | `obsidiandroid.labeling.taxonomy` | **Pass 58:** public normalize / known / canonicalize via wrapper; **Pass 85:** constants implementation canonical under labeling | Export function-level taxonomy API for normal callers; raw constants maps/tokens are implementation tables despite their canonical module location. |
| Vendor consensus parsing | `ml_classification.inference.label_consensus_engine` | defer to `obsidiandroid.vendors` / `obsidiandroid.evaluation` | `defer` | Boundary intentionally unresolved; do not force under labeling in Pass 46. |
| Feature vector construction | `ml_classification.vectorization.feature_vector_builder` | `obsidiandroid.features` | `ready_now` | Strong first-slice candidate. |
| Training pipeline core | `ml_classification.training.pipeline_core` | `obsidiandroid.modeling` | `ready_now` | Stable outer usage via CLI/pipeline/tests. |
| Model trainer factory | `ml_classification.training.model_trainer_factory` | `obsidiandroid.modeling` | `ready_now` | Stable boundary for trainer selection and configuration handoff. |
| Evidence-strict / paper-mode behavior | Mostly `obsidiandroid.pipeline.runtime_policy`, **`obsidiandroid.pipeline.stage_*`**, plus training helpers (legacy **`analysis.pipeline.*`** names are shims) | primarily pipeline/governance (not ML facade) | `defer` | Behavior owned by pipeline/governance policy; avoid relocating into ML facade. |
| Dataset perturbation and ablation logic | `obsidiandroid.pipeline.stage_ablation`, related ML callers | pipeline facade / future modeling hooks | `defer` | Keep in pipeline domain for now; expose only ML primitives needed by stage code. |

## Pass 47 slice recommendation (derived from readiness table)

Recommended first implementation slice (no file moves):
- `obsidiandroid.modeling` aliases:
  - `pipeline_core`
  - `model_trainer_factory`
  - `distribution_reporter`
  - `feature_label_alignment_helper`
- `obsidiandroid.features` alias:
  - `feature_vector_builder`
- `obsidiandroid.labeling` alias:
  - `classification_label_resolver`

Deferred from initial slice:
- vendor consensus / inference engines
- engine weighting + eval comparators
- raw taxonomy constant maps
- algorithm-specific trainer modules
- builder internals

## Pass 47 implementation status

Implemented exactly the six `ready_now` aliases above, with identity/parity checks in:
- `scripts/dev/check_import_surface.py`
- `tests/test_obsidiandroid_package_surface.py`

Still deferred in Pass 47 (unchanged):
- all `needs_wrapper` rows
- all `defer` rows (including vendor consensus parsing)
- all `internal_only` rows

## Pass 48 adoption status (outer callers)

Adopted in real outer callers (imports only; no behavior changes):

- `obsidiandroid.modeling.pipeline_core`
  - `src/obsidiandroid/cli/startup_menu.py`
  - `src/obsidiandroid/pipeline/stage_modeling.py`
  - `src/obsidiandroid/pipeline/stage_ablation.py`
- `obsidiandroid.modeling.model_trainer_factory`
  - `src/obsidiandroid/pipeline/stage_modeling.py`
  - `tests/test_stage_ablation.py`
  - `tests/test_model_trainer_factory.py`
  - `tests/test_runtime_policy_cross_run_cleanup.py`
- `obsidiandroid.modeling.distribution_reporter`
  - `src/obsidiandroid/pipeline/stage_ablation.py`
  - `tests/test_distribution_reporter.py`
- `obsidiandroid.modeling.feature_label_alignment_helper`
  - `src/obsidiandroid/pipeline/stage_av_vendor.py`
- `obsidiandroid.features.feature_vector_builder`
  - `src/obsidiandroid/pipeline/stage_ablation.py`
  - `src/obsidiandroid/pipeline/stage_modeling.py`
  - `tests/test_feature_vector_builder.py`
- `obsidiandroid.labeling.classification_label_resolver`
  - `src/obsidiandroid/pipeline/stage_modeling.py`
  - `tests/test_classification_label_resolver_taxonomy_audit.py`

Deferred in Pass 48:
- `tests/test_stage_feature_enrichment_fuse.py` remains mixed (`feature_vector_builder` + `feature_encoder`);
  `feature_encoder` is `needs_wrapper`, so this file was intentionally left unchanged.
- Vendor/evaluation ambiguity remains deferred as documented in Pass 46.

## Pass 49 remaining-import status audit

Pass 49 is an audit/status pass only: no new aliases, no caller migration, no physical
moves, and no behavior changes.

### Reproducible scan method

Import counts used an AST scan over repo `*.py`, excluding generated/runtime paths:

```bash
python - <<'PY'
from __future__ import annotations
import ast
from pathlib import Path
from collections import Counter, defaultdict
root = Path(".")
exclude = {".git",".venv","venv","__pycache__",".pytest_cache",".pytest_tmp","output","logs","obsidiandroid.egg-info",".ruff_cache"}
targets = ("obsidiandroid","analysis","database","ml_classification","model","utils")
counts = Counter()
files = defaultdict(set)
for path in root.rglob("*.py"):
    if any(part in exclude for part in path.parts):
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in targets:
                    counts[top] += 1
                    files[top].add(rel)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in targets:
                for _alias in node.names:
                    counts[top] += 1
                    files[top].add(rel)
for target in targets:
    print(target, counts[target], len(files[target]))
PY
```

Focused line scans used:

```bash
rg -n "^(from ml_classification|import ml_classification)" --glob "*.py" --glob "!ml_classification/**" .
rg -n "^(from analysis\.pipeline|import analysis\.pipeline)" --glob "*.py" --glob "!analysis/pipeline/**" .
rg -n "^(from utils|import utils)" --glob "*.py" --glob "!utils/**" .
rg -n "^(from model|import model)" --glob "*.py" --glob "!model/**" .
rg -n "^(from database|import database)" --glob "*.py" --glob "!database/**" .
```

### Remaining `ml_classification` imports outside `ml_classification/`

Pass 49 found **50** direct import records outside the implementation package:

| Status | Records | Notes |
|---|---:|---|
| `already surfaced alias but not migrated yet` | 9 | Mostly tests plus two evaluation tools; good candidate for a second low-risk adoption batch. |
| `needs_wrapper` | 12 | Data alignment, feature schema/encoder/selection, label normalizer/format/taxonomy function APIs. |
| `defer` | 10 | Vendor feature extraction, vendor consensus, engine weights, eval comparators. |
| `internal_only` | 19 | Trainer internals, builder internals, low-level prediction/training helpers, runtime cache reset. |

File-level classification:

| File | Classification |
|---|---|
| `analysis/evaluation/model_tuning.py` | legacy import path; implementation is canonical `obsidiandroid.evaluation.model_tuning` |
| `analysis/evaluation/random_forest_diagnostics.py` | legacy import path; implementation is canonical `obsidiandroid.evaluation.random_forest_diagnostics` |
| `analysis/pipeline/runner.py` | identity shim on disk; canonical implementation is **`src/obsidiandroid/pipeline/runner.py`** (`obsidiandroid.pipeline.runner`; tests may still monkeypatch **`analysis.pipeline.runner`**) |
| `analysis/diagnostics/feature_builder_drop_trace.py` | defer (`feature_vendor_extractor`) |
| `analysis/vendor_processing/generic_label_parser.py` | mixed: needs_wrapper taxonomy functions + deferred `FAMILY_ALIASES` |
| `tests/test_ablation_split_feature_columns.py` | already surfaced alias but not migrated yet |
| `tests/test_export_manager_wiring.py` | already surfaced alias but not migrated yet |
| `tests/test_pipeline_core_low_support_behavior.py` | already surfaced alias but not migrated yet |
| `tests/test_pipeline_core_summary_exports.py` | already surfaced alias but not migrated yet |
| `tests/test_stage_feature_enrichment_fuse.py` | mixed: surfaced `feature_vector_builder` + needs_wrapper `feature_encoder`; skip for now |
| `tests/test_training_trainer.py` | mixed: surfaced `model_trainer_factory` + internal trainer modules; skip or partial-only with care |
| Other remaining `tests/test_*` ML imports | needs_wrapper, defer, or internal_only per Pass 46 table |

### Recommended next pass

Recommend **Pass 50A: second low-risk ML adoption batch**.

Scope should stay limited to imports already surfaced in Pass 47 and left over after
Pass 48, especially:

- `analysis/evaluation/model_tuning.py`
- `analysis/evaluation/random_forest_diagnostics.py`
- straightforward tests that import only surfaced aliases

Skip mixed files unless the surfaced import can be changed without pulling in
`needs_wrapper`, `defer`, or `internal_only` APIs.

## Pass 50A adoption status

Pass 50A used only aliases already surfaced in Pass 47. It migrated a small batch of
one-to-one imports and did not add aliases, change behavior, or touch
`analysis.pipeline.runner`.

### Reproducible focused inventory

Before editing, surfaced candidates were identified with an AST scan over repo `*.py`
excluding generated/runtime paths and `ml_classification/` internals. Candidate keys:

```python
{
    ("ml_classification.training", "pipeline_core"),
    ("ml_classification.training", "model_trainer_factory"),
    ("ml_classification.vectorization", "feature_vector_builder"),
    ("ml_classification.labeling", "classification_label_resolver"),
    ("ml_classification.ml_utils", "distribution_reporter"),
    ("ml_classification.ml_utils", "feature_label_alignment_helper"),
}
```

Focused remaining-line check:

```bash
rg -n "^(from ml_classification|import ml_classification)" --glob "*.py" --glob "!ml_classification/**" .
```

### Files migrated

| File | Legacy import | Canonical import |
|---|---|---|
| `analysis/evaluation/model_tuning.py` | `from ml_classification.training import model_trainer_factory` | `from obsidiandroid.modeling import model_trainer_factory` |
| `analysis/evaluation/random_forest_diagnostics.py` | `from ml_classification.training import model_trainer_factory` | `from obsidiandroid.modeling import model_trainer_factory` |
| `tests/test_ablation_split_feature_columns.py` | `from ml_classification.training import model_trainer_factory` | `from obsidiandroid.modeling import model_trainer_factory` |
| `tests/test_export_manager_wiring.py` | `from ml_classification.training import pipeline_core` | `from obsidiandroid.modeling import pipeline_core` |
| `tests/test_pipeline_core_low_support_behavior.py` | `from ml_classification.training import pipeline_core` | `from obsidiandroid.modeling import pipeline_core` |
| `tests/test_pipeline_core_summary_exports.py` | `from ml_classification.training import pipeline_core` | `from obsidiandroid.modeling import pipeline_core` |

Legacy `analysis/evaluation/model_tuning.py` historically added repo `src/` to `sys.path` for direct
script execution. The canonical module (`obsidiandroid.evaluation.model_tuning`) is intended to be
run as `python -m obsidiandroid.evaluation.model_tuning` (or via editable install / `PYTHONPATH=src`).

### Remaining surfaced candidates after Pass 50A

Only mixed files remain:

| File | Surfaced import left | Why skipped |
|---|---|---|
| `tests/test_pipeline_contracts.py` | `pipeline_core` | Previously mixed with `model_prediction`; `model_prediction` is canonical as of **Pass 91**. |
| `tests/test_stage_feature_enrichment_fuse.py` | `feature_vector_builder` | Same file imports `feature_encoder` (`needs_wrapper`). |
| `tests/test_training_trainer.py` | `model_trainer_factory` | Same file imports algorithm-specific trainers (`internal_only`). |

Post-pass remaining external `ml_classification` import classification:

| Status | Records |
|---|---:|
| `already surfaced alias but not migrated yet` | 3 |
| `needs_wrapper` | 12 |
| `defer` | 10 |
| `internal_only` | 18 |
| mixed/unclassified constant-level internal | 1 |

## Pass 58: taxonomy wrapper slice (`needs_wrapper` first)

**Goal:** Ship one deliberate **wrapper** (not a module identity alias) for family
taxonomy normalization, plus tests and import-surface checks, without expanding raw
constants exports.

**Implemented**

| Canonical surface | Type | Legacy backing | Notes |
|---|---|---|---|
| **`obsidiandroid.labeling.taxonomy`** | Wrapper module (**`needs_wrapper`** resolved) | `ml_classification.common.malware_family_constants` | Public: **`normalize_family_name`**, **`is_known_family_name`**, **`canonicalize_family_label`**. Intentionally **not** exporting **`KNOWN_FAMILIES`**, **`FAMILY_ALIASES`**, **`GENERIC_TOKENS`**, **`CANONICAL_FAMILY_DISPLAY`**. |
| **`obsidiandroid.labeling.malware_family_constants`** | Physical constants implementation (**Pass 85**) | Legacy shim at **`ml_classification.common.malware_family_constants`** | Raw maps/sets live canonically here for implementation use; public callers should still use **`taxonomy`** wrapper functions. |

**Caller adoption (initial)**

| File | Change |
|---|---|
| **`tests/test_label_quality_normalization.py`** | Imports taxonomy helpers from **`obsidiandroid.labeling.taxonomy`**. |
| **`analysis/vendor_processing/generic_label_parser.py`** | Imports **`normalize_family_name`** / **`is_known_family_name`** from taxonomy; imports **`FAMILY_ALIASES`** from canonical constants (**Pass 85**). |

**Checks**

- **`scripts/dev/check_import_surface.py`**: verifies module path under **`src/obsidiandroid/labeling/taxonomy.py`** and normalization parity smoke vs **`ml_classification`** shims where still enforced.
- **`tests/test_labeling_taxonomy_wrapper.py`**: behavioral parity vs **`obsidiandroid.labeling.malware_family_constants`**; asserts wrapper functions are **not** identical to the underlying implementations (explicit non-alias contract).

### Next ML wrapper candidates (still `needs_wrapper`, not Pass 58)

Prefer explicit wrappers (or frozen façade modules) before additional alias-only surfaces:

- **`feature_encoder`** (features) — document inputs/outputs and defaults. **`feature_schema_audit`** moved in Pass 89 with the existing audit-row contract preserved.
- **Label normalization stack** (`label_field_normalizer`, `label_format_generator`, …) — schema/versioned contracts.
