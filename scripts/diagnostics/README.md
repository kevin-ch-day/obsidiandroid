# Diagnostics scripts (`scripts/diagnostics/`)

Operator inspection and analysis helpers that live in this package. Run from the **repository root** so imports resolve (`analysis`, `database`, `config`, …).

## Inspect modules (migrated from top-level `data_inspect/`)

The canonical implementations are **here**. **`data_inspect/`** at the repo root keeps thin compatibility shims (`from data_inspect import …`) for existing imports.

| Module | Role |
|--------|------|
| [`inspect_av_pipeline_results.py`](inspect_av_pipeline_results.py) | AV pipeline output inspection |
| [`inspect_classification_results.py`](inspect_classification_results.py) | Classification outputs |
| [`inspect_complexity_hotspots.py`](inspect_complexity_hotspots.py) | Complexity hotspots |
| [`inspect_engine_score_matrix.py`](inspect_engine_score_matrix.py) | Engine score matrix |
| [`inspect_module_size_hotspots.py`](inspect_module_size_hotspots.py) | Module/function size |
| [`inspect_parsed_data.py`](inspect_parsed_data.py) | Parsed data |
| [`inspect_vendor_column_opportunities.py`](inspect_vendor_column_opportunities.py) | Vendor columns |
| [`inspect_vendor_feature_results.py`](inspect_vendor_feature_results.py) | Vendor features |
| [`inspect_vendor_missing_patterns.py`](inspect_vendor_missing_patterns.py) | Missing patterns |
| [`inspect_vendor_parser_health.py`](inspect_vendor_parser_health.py) | Parser health |

## Other operator scripts (still under `scripts/`)

Alignment, lineage, inventory, and cohort tooling remain at [`scripts/`](../README.md) paths (e.g. `diagnose_alignment_gap.py`, `report_output_inventory.py`).

## Research diagnostics

See **`scripts/research/`** for publication and structural bundles.

Pipeline staging: [`docs/pipeline_staging_guide.md`](../../docs/pipeline_staging_guide.md).
