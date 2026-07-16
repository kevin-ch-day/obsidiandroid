# Diagnostics scripts (`scripts/diagnostics/`)

Operator inspection and analysis helpers that live in this package. Run from the **repository root** so imports resolve (`obsidiandroid`, `database`, `config`, …).

## Inspect modules (formerly top-level `data_inspect/`)

The canonical implementations are **here**. Import them as **`scripts.diagnostics.<module>`** (or run **`python scripts/diagnostics/<script>.py`**). Repo-root **`data_inspect/`** was removed; migrate off-repo scripts from `from data_inspect import …` to **`scripts.diagnostics`**.

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
| [`export_label_authority_vendor_evidence.py`](export_label_authority_vendor_evidence.py) | Parser-enriched long-form vendor-label evidence export for label-authority rollout |
| [`label_authority_schema_readiness.py`](label_authority_schema_readiness.py) | Read-only Erebus readiness audit for the label-authority schema pack |
| [`report_family_type_authority_coverage.py`](report_family_type_authority_coverage.py) | Authority bucket / gap / conflict / temporal-coverage report from the proposed family-type authority view |
| **(Alert logs emitted by authority coverage)** | Running the authority coverage diagnostic also emits targeted structured logs: `label_authority_alerts.log` and `temporal_readiness_alerts.log` |
| [`report_logging_engine_usage.py`](report_logging_engine_usage.py) | Static audit of structured logger categories, event coverage, missing event IDs, and failure events without explicit severity |
| [`report_log_surface.py`](report_log_surface.py) | Inventory repo/runtime log files and recommend what to keep, prune, or cover with diagnostics instead of new log categories |
| [`report_run_log_issues.py`](report_run_log_issues.py) | Summarize latest-run warning hotspots, stage timing hotspots, authority/temporal alert counts, and missing error-log coverage |
| [`report_label_noise_candidates.py`](report_label_noise_candidates.py) | Read-only label-risk scoring from vendor evidence and current governed family truth |
| [`summarize_label_authority_vendor_evidence.py`](summarize_label_authority_vendor_evidence.py) | Summarize parser-enriched evidence and emit family-alias review candidates |
| [`report_android_missing_resolution_triage.py`](report_android_missing_resolution_triage.py) | Read-only Android/APK missing-resolution triage report and CSV export (includes `android_missing_resolution_vt_tail_latest.csv` and per-lane `android_missing_resolution_lane_*_latest.csv` worklists) |
| [`report_vt_false_positive_review_triage.py`](report_vt_false_positive_review_triage.py) | Suppression-aware VT false-positive triage report and CSV export |
| [`report_android_policy_held_token_risk.py`](report_android_policy_held_token_risk.py) | Read-only policy-held Android family-token risk report and CSV export |
| [`report_missing_primary_label_triage.py`](report_missing_primary_label_triage.py) | Suppression-aware missing-primary label triage, schema-versioned summary, review-only authority-backed proposals, and a separate human-review template; never writes catalog labels |
| [`validate_missing_primary_backfill_review.py`](validate_missing_primary_backfill_review.py) | Read-only validator for a human-reviewed primary-label ledger; verifies proposal identity and membership hashes and never writes catalog labels |
| [`report_taxonomy_type_lifecycle_gaps.py`](report_taxonomy_type_lifecycle_gaps.py) | Read-only worklist for active family mappings that point to retired taxonomy types; never reactivates or remaps records |
| [`report_profile_family_mapping_debt.py`](report_profile_family_mapping_debt.py) | Profile-scoped family-mapping debt breakdown (blank vs policy-held vs true catalog lag; emits `profile_policy_held_slug_worklist_latest.csv`) |
| [`report_blank_resolved_family_triage.py`](report_blank_resolved_family_triage.py) | Blank-resolved Android family debt outside the missing-resolution triage view (includes singleton provenance lane + package-cluster drill-down exports) |
| [`report_backlog_debt_operator_summary.py`](report_backlog_debt_operator_summary.py) | Consolidated live backlog/debt operator summary (JSON + Markdown) |
| [`report_vendor_verdict_debt.py`](report_vendor_verdict_debt.py) | Read-only vendor-verdict debt report that buckets malicious labels into family-ready, overlap, generic-signal, and provenance-noise classes and exports vendor/token/sample pressure CSVs |
| [`report_zimperium_ioc_repo_coverage.py`](report_zimperium_ioc_repo_coverage.py) | Optional external IOC inventory (`research/external_iocs/Zimperium-IOC/`); exits cleanly with empty exports when the tree is absent |

## Canonical diagnostics migrated from top-level `scripts/`

These scripts now live here canonically. Repo-root wrappers are kept so older menu paths,
operator habits, and docs links do not break immediately.

| Canonical script | Compatibility wrapper |
|--------|------|
| [`diagnose_alignment_gap.py`](diagnose_alignment_gap.py) | `scripts/diagnose_alignment_gap.py` |
| [`report_feature_lineage.py`](report_feature_lineage.py) | `scripts/report_feature_lineage.py` |
| [`report_feature_matrix_gap.py`](report_feature_matrix_gap.py) | `scripts/report_feature_matrix_gap.py` |
| [`report_output_inventory.py`](report_output_inventory.py) | `scripts/report_output_inventory.py` |
| [`trace_feature_builder_drops.py`](trace_feature_builder_drops.py) | `scripts/trace_feature_builder_drops.py` |
| [`check_run_integrity.py`](check_run_integrity.py) | `scripts/check_run_integrity.py` |

## Other operator scripts still intentionally top-level

Warehouse backfills, output cleanup, cohort gate checks, and retrain helpers remain at
[`scripts/`](../README.md) paths until a separate operations/maintenance pass.

## Research diagnostics

See **`scripts/research/`** for publication and structural bundles.

| Script | Role |
|--------|------|
| [`summarize_run_research_health.py`](summarize_run_research_health.py) | Read-only digest: leakage line, cohort lock, feature authority / vendor merge, split-freeze hygiene, stage summary vs finalization artifacts (`--run-id`, `--latest`, `--json`). Includes an **output navigator**: bucket counts from `artifact_inventory.json`, checklist of routing/research files, optional largest-on-disk paths (`--tour`). Adds **metrics parity**: headline vs ablation `full_fused` `feature_column_hash`, plus **taxonomy** top `type_mapping_mismatch` (`cohort` → `label-implied`) pairs from mismatch CSV when present. |
| **(Pipeline / manifest)** | After a full run, diagnostics also include **`headline_vs_ablation_contract_comparison_*.{md,csv}`** and **`taxonomy_type_authority_review_*.{md,csv}`** (operator dashboard + research validity bundle). |

Pipeline staging: [`docs/pipeline_staging_guide.md`](../../docs/pipeline_staging_guide.md).
