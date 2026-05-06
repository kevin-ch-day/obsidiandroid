# Pass 50B: vendor/evaluation boundary inventory

This document is the Pass 50B docs-only inventory for the vendor, evaluation, and
model parsing boundary. It intentionally does not add aliases, migrate callers,
move files, or change parser/model/training/output/DB behavior.

**Pass 63 update (code, not a re-audit):** Evaluation **implementation** modules that previously lived as **`analysis/evaluation/<module>.py`** files are now under **`src/obsidiandroid/evaluation/`**. Legacy imports **`analysis.evaluation.<module>`** remain valid via **`analysis/evaluation/__init__.py`** (**`sys.modules`** identity to the canonical module).

**Pass 64 update (code, not a re-audit):** Vendor parser **runtime** modules that previously lived as **`analysis/execution/<module>.py`** files are now under **`src/obsidiandroid/vendors/execution/`**. Legacy **`analysis.execution.<module>`** imports remain valid via **`analysis/execution/__init__.py`**. **Pipeline** physical layout (runner/stages/manifest internals) remains deferred.

**Pass 65 update (code, not a re-audit):** Run **diagnostics** (including **`research_validity/`**, **`hostile_audit/`**, and leaf diagnostics modules) that previously lived under **`analysis/diagnostics/`** are now under **`src/obsidiandroid/diagnostics/`**. Legacy **`analysis.diagnostics.*`** remains valid via **`analysis/diagnostics/__init__.py`** (**`sys.modules`** identity).

**Plan refresh (2026-05, documentation only):** Passes **59** / **63** / **64** / **65** mean **`analysis/vendor_processing/`**, **`analysis/evaluation/`**, **`analysis/execution/`**, and **`analysis/diagnostics/`** are **no longer leaf implementation trees** — each is a **package-only shim** (**`__init__.py`** + **`sys.modules`** registration). Implementations live under **`src/obsidiandroid/`**. The **Import inventory** table below remains the **Pass 50B static snapshot** (useful for *who imports whom*); **Current source path** for those modules should be read as “**legacy import prefix; file is under `obsidiandroid.…`**.” A full row-by-row rescan is optional.

The summary metrics and boundary narrative below were written for the pre-move layout; treat **readiness tags** as **conceptual** until a dedicated re-audit reruns the AST scan.

## Scope

Inventoried implementation areas:

- `analysis/vendor_processing/*`
- `analysis/evaluation/vendor_*`
- `analysis/evaluation/av_*`
- `analysis/execution/vendor_*`
- `model/vendor/*`
- `model/parsing/*`
- `model/core/risk_band_config.py` where it appears in vendor/evaluation flows
- `ml_classification/engine_weights/*`
- Imports from those areas used by pipeline, diagnostics, tests, scripts, CLI, and ML internals

Readiness tags:

| Tag | Meaning |
|---|---|
| `ready_now` | Thin canonical alias could be introduced with low risk. |
| `needs_wrapper` | Candidate canonical concept exists, but a stable contract wrapper should be designed first. |
| `defer` | Boundary or semantics are not stable enough for a facade slice yet. |
| `internal_only` | Implementation detail; do not expose as canonical surface. |
| `monkeypatch_sensitive` | Test/runtime patch surface should stay on implementation path until explicitly refactored. |

## Reproducible audit method

Candidate files were listed with:

```bash
find analysis/vendor_processing analysis/evaluation analysis/execution model/vendor model/parsing ml_classification/engine_weights -maxdepth 2 -type f | sort
```

Focused text scan:

```bash
rg -n "vendor_processing|analysis\.evaluation|analysis\.execution|model\.vendor|model\.parsing|ml_classification\.engine_weights|risk_band_config|VendorClassificationRecord|ParsedLabelMetadata" --glob "*.py" --glob "!output/**" --glob "!logs/**" --glob "!**/__pycache__/**" .
```

Import inventory used an AST scan over repo `*.py`, excluding generated/runtime paths:
`.git`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, `.pytest_tmp`, `output`,
`logs`, `obsidiandroid.egg-info`, and `.ruff_cache`.

```python
from __future__ import annotations

import ast
from pathlib import Path

TARGET_PREFIXES = (
    "analysis.vendor_processing",
    "analysis.evaluation",
    "analysis.execution",
    "model.vendor",
    "model.parsing",
    "model.core.risk_band_config",
    "ml_classification.engine_weights",
)

EXCLUDE = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".pytest_tmp",
    "output",
    "logs",
    "obsidiandroid.egg-info",
    ".ruff_cache",
}

for path in sorted(Path(".").rglob("*.py")):
    if any(part in EXCLUDE for part in path.parts):
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(TARGET_PREFIXES):
                    print(path, node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(TARGET_PREFIXES):
                for alias in node.names:
                    print(path, node.lineno, node.module, alias.name)
```

The readiness/domain tags below were then assigned conservatively from source
ownership and caller context. No generated CSV was committed.

## Inventory summary

| Metric | Count |
|---|---:|
| Import records | 81 |
| Proposed `obsidiandroid.vendors` records | 60 |
| Proposed `obsidiandroid.evaluation` records | 21 |

| Readiness tag | Records | Interpretation |
|---|---:|---|
| `ready_now` | 1 | Only the parser map entrypoint is clearly alias-ready today. |
| `needs_wrapper` | 37 | Vendor records, parsed metadata, generic parsing, and parser result contracts need stable wrappers. |
| `defer` | 38 | Evaluation/scoring/vendor-specific parser semantics need boundary decisions first. |
| `internal_only` | 5 | Execution builders/runners and record factories should remain implementation details. |
| `monkeypatch_sensitive` | 0 | No row was tagged this way in the static scan, but test patch surfaces should still be reviewed before caller migration. |

| Caller group | Records | Notes |
|---|---:|---|
| `analysis` | 36 | Core vendor/evaluation implementation plus pipeline and diagnostics callers. |
| `scripts` | 16 | Diagnostics scripts mostly exercise parser maps and vendor-specific parsers. |
| `tests` | 13 | Contract tests mix public-ish behavior with internal parser/record surfaces. |
| `ml_classification` | 7 | ML builder/inference/labeling code consumes vendor records. |
| `model` | 5 | Record objects and parsed metadata import each other. |
| `src` | 4 | Canonical CLI still reaches into unfacaded vendor/evaluation implementation. |

## Boundary answers

### What is vendor parsing?

Vendor parsing is the domain that turns raw AV/vendor classification strings into
structured parsed-label data. It includes:

- parser maps such as `analysis.vendor_processing.vendor_parser_map`
- generic parsing entrypoints such as `parse_generic_classification`
- vendor-specific parsers such as Avast, Bitdefender, Kaspersky, Microsoft, Tencent,
  ZoneAlarm, Alibaba, AhnLab, and related parser default/confidence helpers
- parsed label metadata currently represented by `model.parsing.parsed_label_metadata.ParsedLabelMetadata`
- vendor record domain objects currently represented by `model.vendor.record_core.VendorClassificationRecord`

Candidate canonical home: `obsidiandroid.vendors`.

Pass 50B finding: only the parser map entrypoint is cleanly `ready_now`. Generic
parsing, parsed metadata, and vendor records are good candidates, but they should
be exposed through deliberate wrappers that freeze schema and return contracts.
Vendor-specific parser modules should stay deferred until parser API shape is stable.

### What is evaluation?

Evaluation is the domain that summarizes and scores AV/model/parser outcomes. It
includes:

- AV result fetching and evaluation summaries
- parser quality checks and parser matching utilities
- engine scoring summaries
- vendor score calculators and summary builders
- model/AV comparison outputs
- engine weight/reliability scoring

Candidate canonical home: `obsidiandroid.evaluation`.

Pass 50B finding: evaluation is not ready for a broad facade. Several functions are
public-ish, but result schema, scoring ownership, and the split between parser
quality, model evaluation, and reporting need wrapper decisions first.

### What is labeling?

Labeling is normalized malware family/type/taxonomy resolution and label field
normalization. The already surfaced `classification_label_resolver` remains the
right first canonical labeling API.

Pass 50B finding: vendor parsing can produce labels, but it should not be folded
into `obsidiandroid.labeling`. Labeling should own normalized taxonomy concepts;
vendor parsing should own how AV strings are parsed into candidate label metadata.

### What is modeling?

Modeling remains ML training/model orchestration and model helper surfaces:

- training pipeline core
- model trainer factory
- feature vector construction through the features facade
- distribution/model evaluation helpers already surfaced in the ML facade

Pass 50B finding: `ml_classification.engine_weights` is closer to AV/evaluation
policy than model training. Do not add engine weights to `obsidiandroid.modeling`
unless a future audit proves they are truly model-orchestration APIs.

### What should remain internal?

Keep these on implementation paths for now:

- `analysis.execution.*` runner/processor/factory modules
- vendor record builders/factories
- vendor-specific parser internals
- parser matching helpers while contracts are unstable
- raw parser defaults/confidence internals
- tests that patch or assert implementation details

## Boundary decision table

| Area | Current anchors | Proposed canonical domain | Readiness | Decision |
|---|---|---|---|---|
| Vendor parsing | `analysis.vendor_processing.vendor_parser_map`, `generic_label_parser`, vendor-specific parsers | `obsidiandroid.vendors` | `ready_now` for parser map; `needs_wrapper`/`defer` for the rest | Start with parser-map alias only if a tiny facade slice is desired. Wrap generic parser before exposing it. Defer vendor-specific modules. |
| Vendor record model | `model.vendor.record_core.VendorClassificationRecord`, `model.vendor.feature_engine` | `obsidiandroid.vendors` | `needs_wrapper` | Stable concept, but expose through wrapper/schema contract rather than raw record internals first. |
| Parsed label metadata | `model.parsing.parsed_label_metadata.ParsedLabelMetadata` | `obsidiandroid.vendors` | `needs_wrapper` | Treat as part of parser API, not labeling API, until normalized taxonomy boundaries are explicit. |
| AV result evaluation | `analysis.evaluation.av_results_fetcher`, `evaluate_av_classifications` | `obsidiandroid.evaluation` | `needs_wrapper`/`defer` | Candidate evaluation surface, but stabilize input/result contracts first. |
| Engine scoring | `analysis.evaluation.engine_scoring_summary`, `vendor_score_calculator`, `vendor_summary_builder` | `obsidiandroid.evaluation` | `defer` | Scoring policy is research-sensitive; do not expose casually. |
| Parser quality checks | `analysis.evaluation.vendor_parser_utils`, `vendor_parser_matching`, parser health scripts | `obsidiandroid.evaluation` plus `obsidiandroid.vendors` entrypoints | `defer` | Split quality/reporting from parser implementation before facade work. |
| Risk band config | `model.core.risk_band_config.RiskBandConfig`, `analysis/risk_band/assign_risk_band.py` | `obsidiandroid.vendors` or future risk domain | `defer` | Appears in adjacent vendor/evaluation flow but ownership is not settled. Do not attach to modeling. |
| Engine weights | `ml_classification.engine_weights.*` | `obsidiandroid.evaluation` | `defer` | Treat as evaluation/scoring policy for now, not modeling. Needs contract/spec before exposure. |

## Execution roadmap (Pass 58): practical domain assignment

This section turns the inventory into an **ordered checklist** for façade and wrapper
work. Each row should carry an explicit tag when implemented: **`ready_now`**,
**`needs_wrapper`**, **`defer`**, **`internal_only`**, **`monkeypatch_sensitive`**.

Treat **`obsidiandroid.reporting`** and **`obsidiandroid.governance`** as **already
partial** canonical homes for paper/manifest/export surfaces; this table only scopes
vendor/evaluation-heavy code.

### A) Canonical target: **`obsidiandroid.vendors`**

Owns “raw AV/vendor string → structured vendor-side interpretation,” without lumping
that into **`obsidiandroid.labeling`** (taxonomy normalization for known families lives
under **`obsidiandroid.labeling.taxonomy`** after Pass 58).

| Execution order | Item | Current anchor(s) | Tag today | Notes |
|---:|---|---|---|---|
| 1 | Parser map entry | `obsidiandroid.vendors.parsing.vendor_parser_map` (legacy shim at `analysis.vendor_processing.vendor_parser_map`) | **moved (Pass 59)** | Physical module moved to canonical package; legacy path preserved with identity shim. |
| 2 | Generic parser contract | `generic_label_parser.parse_generic_classification`, related | **`needs_wrapper`** | Freeze parsed output shape before canonical export. Pass 58: **taxonomy helpers** consumed from **`obsidiandroid.labeling.taxonomy`**; **`FAMILY_ALIASES`** still imported from legacy until a **vendors-local** alias contract exists. |
| 3 | Parsed label metadata | `model.parsing.parsed_label_metadata.ParsedLabelMetadata` | **`needs_wrapper`** | Part of parser/record API, not labeling taxonomy. |
| 4 | Vendor classification record | `model.vendor.record_core.VendorClassificationRecord` | **`needs_wrapper`** | Expose via wrapper or protocol, not raw internal fields first. |
| 5 | Vendor feature engine helpers | `model.vendor.feature_engine` | **`needs_wrapper`** | Coupled to records; ship after record wrapper story. |
| 6 | Vendor-specific parser modules | `obsidiandroid.vendors.parsing/*_parser.py` (legacy shim path still valid) | **partially moved (Pass 59)** | Physical relocation complete; API/wrapper exposure still deferred. |
| 7 | Risk band config | `model.core.risk_band_config`, `analysis/risk_band/*` | **`defer`** | Ownership split between vendor policy and evaluation not settled. |

### B) Canonical target: **`obsidiandroid.evaluation`**

Owns scoring, comparative summaries, parser quality **as evaluation artifacts** (not
vendor parsing internals). Nothing here should be a **`sys.modules`** alias until
input/output contracts are explicit.

| Execution order | Item | Current anchor(s) | Tag today | Notes |
|---:|---|---|---|---|
| 1 | AV classification parsing entry | `vendor_classification_parser.parse_vendor_classifications` | **`needs_wrapper`** | First good evaluation-facing seam if I/O is frozen. |
| 2 | AV result fetch + evaluation helpers | `av_results_fetcher`, `evaluate_av_classifications`, … | **`defer`** | Couples DB, records, and reporting; needs spec. |
| 3 | Engine / vendor scoring | `engine_scoring_summary`, `vendor_score_calculator`, `vendor_summary_builder` | **`defer`** | Research-sensitive policy; do not façade casually. |
| 4 | Parser quality / matching | `vendor_parser_utils`, `vendor_parser_matching` | **`defer`** | Split “quality metric” vs “parser implementation” before export. |
| 5 | Engine weights | `ml_classification.engine_weights.*` | **`defer`** | Belongs with evaluation policy, not **`obsidiandroid.modeling`**. |
| 6 | RF / model diagnostics helpers | `analysis/evaluation/random_forest_diagnostics`, … | **`defer`** | Decide overlap with **`obsidiandroid.reporting`** exports first. |

### C) **`internal_only`** — stay on implementation paths

Keep on **`analysis.execution.*`**, record factories/runners, and vendor parser
internals until wrappers above exist. **`monkeypatch_sensitive`** call sites stay on
their current import paths until a deliberate patch-target migration plan exists.

### D) **`obsidiandroid.reporting`** / paper outputs

Place **LaTeX, confusion/family distro printers, workbook/export packaging** here (many
already canonical). Boundary rule: evaluation computes **scores/metrics objects**;
reporting formats them for manuscripts and operator dashboards. **`ml_classification.reporting.ml_report_builder`**
remains **`defer`** until that split is written down.

### E) **`defer` / too coupled for this quarter**

- **Public** evaluation façade (documented stable I/O for scoring, parser quality exports, AV evaluation helpers) until parser + scoring **contracts** exist — *physical* modules already live under **`obsidiandroid.evaluation`** (Pass **63**).
- Vendor-specific parser **API surface** (beyond imports working) without generic/metadata wrappers — *implementations* live under **`obsidiandroid.vendors.parsing`** (Pass **59**).
- **`obsidiandroid.labeling`** owning vendor consensus (`label_consensus_engine`) —
  stays **`defer`** to vendors/evaluation per ML boundary plan.

## Pass 51 implementation status (historical)

Implemented the first vendor facade slice:

- `obsidiandroid.vendors.vendor_parser_map` aliases
  `analysis.vendor_processing.vendor_parser_map`.
- `scripts/dev/check_import_surface.py` verifies facade attribute identity and direct
  submodule import identity.
- `tests/test_obsidiandroid_package_surface.py` verifies the same package-surface
  parity.
- `scripts/diagnostics/inspect_vendor_column_opportunities.py` now imports
  `get_vendor_parser_map` from the canonical path.
- `tests/test_vendor_parser_map.py` now imports `vendor_parser_map` from
  `obsidiandroid.vendors`.

## Open work after physical migration (Passes 59–64; updated 2026-05)

**Done (physical):** Vendor parser leaf modules (**Pass 59**), evaluation glue modules (**Pass 63**), vendor parser runtime / execution (**Pass 64**). Legacy **`analysis.*`** import paths remain valid via identity shims.

**Still open (contracts / hygiene, not “move files”):**

- Generic parser **wrapper** and a frozen **`parse_generic_classification`** contract.
- **`VendorClassificationRecord`** and **`ParsedLabelMetadata`**: stable **`obsidiandroid.vendors`**-level wrappers (types still authoritative in **`model.*`** until then).
- **Evaluation façade**: explicit public I/O for **`vendor_classification_parser`**, parser-quality exports, scoring summaries; **`ml_classification.engine_weights`** policy ownership aligned with evaluation (see execution roadmap above).
- **Callers**: prefer **`obsidiandroid.evaluation`** and **`obsidiandroid.vendors.execution`** in new code; migrate stragglers opportunistically (**`rg`** is enough; the Pass 50B table is not maintained row-by-row).

## Import inventory

| Caller file | Imported module/symbol | Current source path | Proposed canonical domain | Readiness |
|---|---|---|---|---|
| `analysis/diagnostics/feature_builder_drop_trace.py` | `analysis.evaluation::vendor_classification_parser` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/evaluate_av_classifications.py` | `analysis.evaluation::vendor_classification_inspector` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/evaluate_av_classifications.py` | `analysis.evaluation.vendor_classification_parser::parse_vendor_classifications` | `analysis/evaluation/vendor_classification_parser.py` | `obsidiandroid.evaluation` | `needs_wrapper` |
| `analysis/evaluation/vendor_classification_parser.py` | `analysis.evaluation::vendor_parser_utils` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/vendor_classification_parser.py` | `analysis.execution::av_parser_executor` | `analysis/execution/` | `obsidiandroid.vendors` | `internal_only` |
| `analysis/evaluation/vendor_classification_parser.py` | `analysis.evaluation::vendor_score_calculator` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/vendor_classification_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/evaluation/vendor_classification_parser.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/evaluation/vendor_feature_extractor.py` | `analysis.evaluation::evaluate_av_classifications` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/vendor_parser_utils.py` | `analysis.vendor_processing::vendor_parser_map` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `analysis/evaluation/vendor_parser_utils.py` | `analysis.vendor_processing::generic_label_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `analysis/evaluation/vendor_parser_utils.py` | `analysis.evaluation::vendor_parser_matching` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/vendor_parser_utils.py` | `analysis.evaluation::av_results_fetcher` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/evaluation/vendor_summary_builder.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/execution/av_parser_executor.py` | `analysis.execution::vendor_parser_runner` | `analysis/execution/` | `obsidiandroid.vendors` | `internal_only` |
| `analysis/execution/vendor_classification_processor.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/execution/vendor_classification_processor.py` | `analysis.execution::vendor_record_factory` | `analysis/execution/` | `obsidiandroid.vendors` | `internal_only` |
| `analysis/execution/vendor_classification_processor.py` | `analysis.evaluation::vendor_summary_builder` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/execution/vendor_parser_runner.py` | `analysis.execution::vendor_classification_processor` | `analysis/execution/` | `obsidiandroid.vendors` | `internal_only` |
| `analysis/execution/vendor_record_factory.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/execution/vendor_record_factory.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/pipeline/stage_modeling.py` | `analysis.evaluation::engine_scoring_summary` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/pipeline/vendor_metadata_pipeline.py` | `analysis.evaluation::vendor_feature_extractor` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `analysis/risk_band/assign_risk_band.py` | `model.core.risk_band_config::RiskBandConfig` | `model/core/risk_band_config.py` | `obsidiandroid.vendors` | `defer` |
| `analysis/vendor_processing/ahnlab_v3_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/alibaba_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/avast_mobile_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/bitdefender_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/bitdefenderfalx_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/generic_label_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/ikarus_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/k7gw_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/kaspersky_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/microsoft_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/tencent_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `analysis/vendor_processing/zonealarm_parser.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/builder/classification_row_builder.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/builder/record_enrichment.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/builder/vendor_record_selector.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/inference/label_consensus_engine.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/inference/signal_health_checker.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/labeling/label_field_normalizer.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `ml_classification/labeling/label_format_generator.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `model/vendor/record_builder.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `model/vendor/record_builder.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `model/vendor/record_core.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `model/vendor/record_core.py` | `model.vendor.feature_engine::compute_all_features` | `model/vendor/feature_engine.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `model/vendor/record_validator.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `scripts/diagnostics/inspect_vendor_column_opportunities.py` | `analysis.vendor_processing.vendor_parser_map::get_vendor_parser_map` | `analysis/vendor_processing/vendor_parser_map.py` | `obsidiandroid.vendors` | `ready_now` (migrated Pass 51) |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::avast_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::avast_mobile_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::bitdefender_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::bitdefenderfalx_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::ikarus_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::k7gw_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::kaspersky_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::lionic_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::microsoft_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::tencent_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::zonealarm_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::alibaba_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::ahnlab_v3_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_missing_patterns.py` | `analysis.vendor_processing::generic_label_parser` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `scripts/diagnostics/inspect_vendor_parser_health.py` | `analysis.evaluation.vendor_classification_parser::parse_vendor_classifications` | `analysis/evaluation/vendor_classification_parser.py` | `obsidiandroid.evaluation` | `needs_wrapper` |
| `src/obsidiandroid/cli/menu/vendor_diagnostics.py` | `analysis.vendor_processing::vendor_parser_map` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `defer` |
| `src/obsidiandroid/cli/menu/vendor_diagnostics.py` | `analysis.vendor_processing.generic_label_parser::parse_generic_classification` | `analysis/vendor_processing/generic_label_parser.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `src/obsidiandroid/cli/menu/vendor_diagnostics.py` | `model.parsing.parsed_label_metadata::ParsedLabelMetadata` | `model/parsing/parsed_label_metadata.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `src/obsidiandroid/cli/startup_menu.py` | `analysis.evaluation::engine_scoring_summary` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_classification_builder.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `tests/test_engine_weights.py` | `ml_classification.engine_weights::engine_weights_utils` | `ml_classification/engine_weights/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_engine_weights.py` | `ml_classification.engine_weights::classification_weight_utils` | `ml_classification/engine_weights/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_engine_weights.py` | `ml_classification.engine_weights::compute_reliability_score` | `ml_classification/engine_weights/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_export_manager_wiring.py` | `analysis.evaluation::evaluate_av_classifications` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_export_manager_wiring.py` | `analysis.evaluation::vendor_feature_extractor` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_parser_quality_contract.py` | `analysis.evaluation::vendor_parser_utils` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_random_forest_diagnostics.py` | `analysis.evaluation::random_forest_diagnostics` | `analysis/evaluation/random_forest_diagnostics.py` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_sample_classification_builder.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |
| `tests/test_vendor_data_determinism.py` | `analysis.execution.vendor_record_factory::create_vendor_record` | `analysis/execution/vendor_record_factory.py` | `obsidiandroid.vendors` | `internal_only` |
| `tests/test_vendor_parser_dynamic.py` | `analysis.evaluation::vendor_parser_utils` | `analysis/evaluation/` | `obsidiandroid.evaluation` | `defer` |
| `tests/test_vendor_parser_map.py` | `analysis.vendor_processing::vendor_parser_map` | `analysis/vendor_processing/` | `obsidiandroid.vendors` | `ready_now` (migrated Pass 51) |
| `tests/test_vendor_record_indexing.py` | `model.vendor.record_core::VendorClassificationRecord` | `model/vendor/record_core.py` | `obsidiandroid.vendors` | `needs_wrapper` |

## Pass 51 recommendation (superseded for physical layout)

Pass **51** scoped the first vendor **façade** slice (`obsidiandroid.vendors.vendor_parser_map`). Passes **59**, **63**, and **64** later **physically** moved parser, evaluation, and vendor-execution **implementations** into **`src/obsidiandroid/`**. Remaining gaps are **wrapper contracts** and **documented public APIs**, not “where the files live.” See **Open work after physical migration** above.

## Pass 59 implementation status

Physical parser move completed:

- `analysis/vendor_processing/*.py` moved to `src/obsidiandroid/vendors/parsing/*.py`.
- `analysis/vendor_processing/__init__.py` now acts as a legacy compatibility shim via `sys.modules`.
- `obsidiandroid.vendors.vendor_parser_map` now resolves through `obsidiandroid.vendors.parsing.vendor_parser_map`.

Still deferred (unchanged from a **types / API** perspective):

- `model.vendor` and `model.parsing` physical moves.
- Evaluation **public façade** (stable I/O) for scoring / parser-quality / AV helpers — modules already under **`obsidiandroid.evaluation`**.
- Wrapper contracts for `VendorClassificationRecord` and `ParsedLabelMetadata`.
