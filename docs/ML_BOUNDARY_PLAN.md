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
| pipeline | 4 | 8 | `runner`, `stage_modeling`, `stage_ablation`, `stage_av_vendor` consume training/vectorization/labeling helpers. |
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
| `ml_classification.labeling::classification_label_resolver` | pipeline, tests | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.labeling.classification_label_resolver` | Canonical label resolution entrypoint; research-critical taxonomy contract. |
| `ml_classification.ml_utils::distribution_reporter` | pipeline, tests | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.modeling.distribution_reporter` | Training/eval artifact utility used by outer callers. |
| `ml_classification.ml_utils::feature_label_alignment_helper` | pipeline | `ready_now` (**surfaced Pass 47**) | `obsidiandroid.modeling.feature_label_alignment_helper` | Alignment contract between features and labels; outer-call surface exists. |
| `ml_classification.training::data_alignment` | tests | `needs_wrapper` | `obsidiandroid.modeling.data_alignment` | Public-ish contract but currently coupled to internal training expectations. |
| `ml_classification.training::feature_schema_audit` | tests | `needs_wrapper` | `obsidiandroid.features.feature_schema_audit` | Useful public check, but wrapper should stabilize output contract. |
| `ml_classification.vectorization.feature_encoder::encode_features` | tests | `needs_wrapper` | `obsidiandroid.features.feature_encoder` | Feature encoding likely reusable; wrapper should lock defaults and params. |
| `ml_classification.vectorization.feature_engine_selection::get_top_engines_by_score` | tests | `needs_wrapper` | `obsidiandroid.features.feature_engine_selection` | Candidate API, but currently helper-shaped and threshold-sensitive. |
| `ml_classification.labeling::label_field_normalizer` | tests, internals | `needs_wrapper` | `obsidiandroid.labeling.label_field_normalizer` | Label normalization is research-critical; wrapper should freeze accepted input schema. |
| `ml_classification.labeling::label_format_generator` | tests | `needs_wrapper` | `obsidiandroid.labeling.label_format_generator` | External behavior should be documented before export. |
| `ml_classification.labeling.label_format_generator::generate_label` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_format_generator` | Same as above; function-level alias can follow module wrapper. |
| `ml_classification.labeling.label_input_validator::validate_label_resolution_inputs` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_input_validator` | Validation contract matters; currently internal. |
| `ml_classification.labeling.label_builder_wrapper::build_structured_label_output` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_builder_wrapper` | Output schema needs explicit versioning before broad adoption. |
| `ml_classification.labeling.label_postprocessor::summarize_prediction_results` | internals | `needs_wrapper` | `obsidiandroid.labeling.label_postprocessor` | Summary semantics should be stabilized first. |
| `ml_classification.common.malware_family_constants::canonicalize_family_label` | tests, vendor processing | `needs_wrapper` → **Pass 58 wrapper** | `obsidiandroid.labeling.taxonomy` | Implemented as delegated functions in **`obsidiandroid.labeling.taxonomy`** (not a ``sys.modules`` alias); behavior locked to legacy. |
| `ml_classification.common.malware_family_constants::normalize_family_name` | tests, vendor processing, internals | `needs_wrapper` → **Pass 58 wrapper** | `obsidiandroid.labeling.taxonomy` | Same as above. |
| `ml_classification.common.malware_family_constants::is_known_family_name` | tests, vendor processing, internals | `needs_wrapper` → **Pass 58 wrapper** | `obsidiandroid.labeling.taxonomy` | Same as above. |
| `ml_classification.common.malware_family_constants::FAMILY_ALIASES` | vendor processing | `defer` | `obsidiandroid.vendors` (future) | Vendor parsing and taxonomy alias data overlap; avoid leaking mutable alias maps through labeling facade. |
| `ml_classification.common.malware_family_constants::GENERIC_TOKENS` | internals | `internal_only` | n/a | Internal heuristic token list. |
| `ml_classification.common::malware_family_constants` | internals | `internal_only` | n/a | Package-level internal coupling import. |
| `ml_classification.inference.label_consensus_engine::resolve_consensus_label` | tests, internals | `defer` | `obsidiandroid.vendors` / `obsidiandroid.evaluation` (future) | Vendor consensus parsing boundary is ambiguous; do not force into labeling facade in Pass 46. |
| `ml_classification.inference.malware_type_engine::infer_malware_type` | internals | `defer` | `obsidiandroid.evaluation` (future) | Inference policy depends on broader eval semantics. |
| `ml_classification.inference.threat_class_engine::infer_threat_class` | internals | `defer` | `obsidiandroid.evaluation` (future) | Same ambiguity as above. |
| `ml_classification.inference.signal_health_checker::analyze_signal_health` | internals | `defer` | `obsidiandroid.evaluation` (future) | Diagnostic metric engine, not yet stable public API. |
| `ml_classification.inference::signal_health_checker` | internals | `internal_only` | n/a | Namespace-level import. |
| `ml_classification.vectorization.feature_vendor_extractor::extract_vendor_fields` | diagnostics | `defer` | `obsidiandroid.vendors` (future) | Vendor feature extraction belongs with vendor domain boundary work. |
| `ml_classification.vectorization.feature_vendor_extractor::merge_vendor_features` | diagnostics | `defer` | `obsidiandroid.vendors` (future) | Same as above. |
| `ml_classification.engine_weights::classification_weight_utils` | tests | `defer` | `obsidiandroid.evaluation` (future) | Engine weighting touches evaluation/vendor policy. |
| `ml_classification.engine_weights::compute_reliability_score` | tests | `defer` | `obsidiandroid.evaluation` (future) | Same as above. |
| `ml_classification.engine_weights::engine_weights_utils` | tests | `defer` | `obsidiandroid.evaluation` (future) | Same as above. |
| `ml_classification.ml_utils::ml_eval_engine` | tests, internals | `defer` | `obsidiandroid.evaluation` (future) | Evaluation API should align with future `obsidiandroid.evaluation` boundary. |
| `ml_classification.ml_utils::ml_comparator_summary` | tests, internals | `defer` | `obsidiandroid.evaluation` (future) | Comparison/reporting semantics are evaluation-facing. |
| `ml_classification.reporting::ml_report_builder` | internals | `defer` | `obsidiandroid.evaluation` / `obsidiandroid.reporting` (future) | Boundary unresolved between evaluation outputs and reporting packaging. |
| `ml_classification.ml_utils::accuracy_band_utils` | tests, internals | `internal_only` | n/a | Helper-level utility; wrapper not yet justified. |
| `ml_classification.ml_utils::dataset_splitter` | internals | `internal_only` | n/a | Internal train/test split helper. |
| `ml_classification.ml_utils::feature_alignment_utils` | internals | `internal_only` | n/a | Internal helper; overlaps with feature_label_alignment_helper surface. |
| `ml_classification.ml_utils::ml_result_analyzer` | internals | `internal_only` | n/a | Internal post-processing helper. |
| `ml_classification.ml_utils::ml_result_validator` | internals | `internal_only` | n/a | Internal validation helper. |
| `ml_classification.training.model_trainer_factory::reset_runtime_training_caches` | pipeline | `internal_only` | n/a | Runtime cache reset is internal operational control, not public API. |
| `ml_classification.training::training_helpers` | tests | `internal_only` | n/a | Internal training helper surface. |
| `ml_classification.training::model_prediction` | tests | `internal_only` | n/a | Internal prediction helper module. |
| `ml_classification.training::train_model_executor` | tests, internals | `internal_only` | n/a | Internal orchestration details; unstable API surface. |
| `ml_classification.training.ml_trainers::random_forest_trainer` | tests | `internal_only` | n/a | Algorithm-specific trainers stay internal for now. |
| `ml_classification.training.ml_trainers::balanced_random_forest_trainer` | tests | `internal_only` | n/a | Internal trainer module. |
| `ml_classification.training.ml_trainers::logistic_regression_trainer` | tests | `internal_only` | n/a | Internal trainer module. |
| `ml_classification.training.ml_trainers::svm_trainer` | tests | `internal_only` | n/a | Internal trainer module. |
| `ml_classification.training.ml_trainers::xgboost_trainer` | tests | `internal_only` | n/a | Internal trainer module. |
| `ml_classification.builder.classification_row_builder::build_classification_row` | tests, internals | `internal_only` | n/a | Builder internals coupled to current record schema. |
| `ml_classification.builder.prediction_utils::extract_prediction_components` | internals | `internal_only` | n/a | Internal helper logic. |
| `ml_classification.builder.prediction_utils` | tests | `internal_only` | n/a | Internal module import. |
| `ml_classification.builder::prediction_utils` | tests | `internal_only` | n/a | Package-level internal import. |
| `ml_classification.builder.sample_classification_builder` | tests | `internal_only` | n/a | Internal builder orchestration module. |
| `ml_classification.builder::sample_classification_builder` | tests, internals | `internal_only` | n/a | Package-level internal import. |
| `ml_classification.builder::classification_constants` | internals | `internal_only` | n/a | Internal constants. |
| `ml_classification.builder::vendor_record_selector` | tests | `internal_only` | n/a | Internal builder selector helper. |
| `ml_classification.labeling.label_field_normalizer::DEFAULT_TYPE` | tests | `internal_only` | n/a | Constant-level internal coupling; avoid exporting raw constants first. |

## Research-critical contract map

| Contract area | Current implementation anchors | Proposed boundary owner | Status (Pass 46) | Notes |
|---|---|---|---|---|
| Label normalization | `ml_classification.labeling.label_field_normalizer`, `label_format_generator`, `classification_label_resolver` | `obsidiandroid.labeling` | `needs_wrapper` / partial `ready_now` | Keep resolver ready; wrap normalizer/format generator with explicit schema contract. |
| Family/type taxonomy resolution | `ml_classification.common.malware_family_constants`, `classification_label_resolver` | `obsidiandroid.labeling.taxonomy` | **Pass 58:** public normalize / known / canonicalize via wrapper; raw sets/maps still `internal_only` or `defer` | Export function-level taxonomy API, not raw constants maps/tokens. ``FAMILY_ALIASES`` remains vendor-adjacent (**defer** to ``obsidiandroid.vendors``). |
| Vendor consensus parsing | `ml_classification.inference.label_consensus_engine` | defer to `obsidiandroid.vendors` / `obsidiandroid.evaluation` | `defer` | Boundary intentionally unresolved; do not force under labeling in Pass 46. |
| Feature vector construction | `ml_classification.vectorization.feature_vector_builder` | `obsidiandroid.features` | `ready_now` | Strong first-slice candidate. |
| Training pipeline core | `ml_classification.training.pipeline_core` | `obsidiandroid.modeling` | `ready_now` | Stable outer usage via CLI/pipeline/tests. |
| Model trainer factory | `ml_classification.training.model_trainer_factory` | `obsidiandroid.modeling` | `ready_now` | Stable boundary for trainer selection and configuration handoff. |
| Evidence-strict / paper-mode behavior | Mostly `analysis.pipeline.runtime_policy`, `analysis/pipeline/stage_*`, plus training helpers | primarily pipeline/governance (not ML facade) | `defer` | Behavior owned by pipeline/governance policy; avoid relocating into ML facade. |
| Dataset perturbation and ablation logic | `analysis/pipeline/stage_ablation.py`, related ML callers | pipeline facade / future modeling hooks | `defer` | Keep in pipeline domain for now; expose only ML primitives needed by stage code. |

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
  - `analysis/pipeline/stage_modeling.py`
  - `analysis/pipeline/stage_ablation.py`
- `obsidiandroid.modeling.model_trainer_factory`
  - `analysis/pipeline/stage_modeling.py`
  - `tests/test_stage_ablation.py`
  - `tests/test_model_trainer_factory.py`
  - `tests/test_runtime_policy_cross_run_cleanup.py`
- `obsidiandroid.modeling.distribution_reporter`
  - `analysis/pipeline/stage_ablation.py`
  - `tests/test_distribution_reporter.py`
- `obsidiandroid.modeling.feature_label_alignment_helper`
  - `analysis/pipeline/stage_av_vendor.py`
- `obsidiandroid.features.feature_vector_builder`
  - `analysis/pipeline/stage_ablation.py`
  - `analysis/pipeline/stage_modeling.py`
  - `tests/test_feature_vector_builder.py`
- `obsidiandroid.labeling.classification_label_resolver`
  - `analysis/pipeline/stage_modeling.py`
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
| `analysis/pipeline/runner.py` | legacy import path; canonical implementation is `obsidiandroid.pipeline.runner` (tests may still monkeypatch `analysis.pipeline.runner`) |
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
| `tests/test_pipeline_contracts.py` | `pipeline_core` | Same line/file also imports `model_prediction` (`internal_only`). |
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

**Caller adoption (initial)**

| File | Change |
|---|---|
| **`tests/test_label_quality_normalization.py`** | Imports taxonomy helpers from **`obsidiandroid.labeling.taxonomy`**. |
| **`analysis/vendor_processing/generic_label_parser.py`** | Imports **`normalize_family_name`** / **`is_known_family_name`** from taxonomy; keeps **`FAMILY_ALIASES`** from legacy until vendor façade owns alias data (**`defer`**). |

**Checks**

- **`scripts/dev/check_import_surface.py`**: verifies module path under **`src/obsidiandroid/labeling/taxonomy.py`** and normalization parity smoke vs legacy.
- **`tests/test_labeling_taxonomy_wrapper.py`**: behavioral parity vs legacy; asserts wrapper functions are **not** identical to legacy objects (explicit non-alias contract).

### Next ML wrapper candidates (still `needs_wrapper`, not Pass 58)

Prefer explicit wrappers (or frozen façade modules) before additional alias-only surfaces:

- **`data_alignment`** (modeling) — stabilize label-merge contract vs training internals.
- **`feature_schema_audit`**, **`feature_encoder`** (features) — document inputs/outputs and defaults.
- **Label normalization stack** (`label_field_normalizer`, `label_format_generator`, …) — schema/versioned contracts.
