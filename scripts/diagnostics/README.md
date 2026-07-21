# Diagnostics scripts (`scripts/diagnostics/`)

Operator inspection and analysis helpers that live in this package. Run from the **repository root** so imports resolve (`obsidiandroid`, `database`, `config`, …).

## Inspect modules (formerly top-level `data_inspect/`)

The canonical implementations are **here**. Import them as **`scripts.diagnostics.<module>`** (or run **`python scripts/diagnostics/<script>.py`**). Repo-root **`data_inspect/`** was removed; migrate off-repo scripts from `from data_inspect import …` to **`scripts.diagnostics`**.

| Module | Role |
|--------|------|
| [`inspect_complexity_hotspots.py`](inspect_complexity_hotspots.py) | Complexity hotspots |
| [`inspect_engine_score_matrix.py`](inspect_engine_score_matrix.py) | Engine score matrix |
| [`inspect_module_size_hotspots.py`](inspect_module_size_hotspots.py) | Module/function size |
| [`inspect_vendor_column_opportunities.py`](inspect_vendor_column_opportunities.py) | Vendor columns |
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
| [`generate_type_permission_pattern_report.py`](generate_type_permission_pattern_report.py) | Read-only malware-type permission-pattern report from an existing run's `permission_trends` tables (complete type accounting, provisional/final status, prevalence, lift, family balance, banker/dropper, **protection/governance lane stratification**); does not query production. Contract: [`docs/TYPE_PERMISSION_PATTERN_REPORT.md`](../../docs/TYPE_PERMISSION_PATTERN_REPORT.md), [`docs/PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](../../docs/PERMISSION_GOVERNANCE_LANE_CONTRACT.md) |
| [`generate_type_permission_pairwise_report.py`](generate_type_permission_pairwise_report.py) | Phase-2 pairwise permission co-occurrence from aligned features + permission audit (AOSP/OEM/Google + protection lanes, within/cross-lane pairs, family-aware support, FDR, explicit suppression); no DB; no three-way mining |
| [`generate_type_permission_interpretation.py`](generate_type_permission_interpretation.py) | Concise evidence-qualified interpretation (banker/RAT/spyware/adware + banker-vs-dropper cautions) from generated type/pairwise diagnostics; offline only |
| [`generate_type_permission_main_comparison.py`](generate_type_permission_main_comparison.py) | High-ROI main-type differential: side-by-side FB discriminators, strong/moderate pairs, SW→FB collapse ledger |
| [`generate_dominant_family_robustness.py`](generate_dominant_family_robustness.py) | Leave-dominant-family robustness (ClayRat/Godfather/…) + banker vs RAT dangerous contrast; offline only |
| [`generate_live_corpus_family_context.py`](generate_live_corpus_family_context.py) | Governed live-corpus family inventory, external-evidence matrix, type-assignment audit, static hypothesis validation, and type-level dominant-family profile robustness; offline only. Contract: [`docs/LIVE_CORPUS_FAMILY_CONTEXT_CONTRACT.md`](../../docs/LIVE_CORPUS_FAMILY_CONTEXT_CONTRACT.md) |
| [`generate_type_permission_protection.py`](generate_type_permission_protection.py) | Protection/governance lane stratification, lane-decomposed dominant-family sensitivity, protection-aware pairwise enrichment, app-defined identity-risk; offline only. Contracts: [`docs/PERMISSION_GOVERNANCE_LANE_CONTRACT.md`](../../docs/PERMISSION_GOVERNANCE_LANE_CONTRACT.md), [`docs/PERMISSION_GOVERNANCE_FIELD_CONTRACT.md`](../../docs/PERMISSION_GOVERNANCE_FIELD_CONTRACT.md) |
| [`generate_permission_authority_enrichment.py`](generate_permission_authority_enrichment.py) | Post-run read-only Permission Intel protection-authority enrichment + enriched protection recompose; does not overwrite artifact-only reports. Contract: [`docs/PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md`](../../docs/PERMISSION_AUTHORITY_ENRICHMENT_CONTRACT.md) |
| [`generate_package_balanced_permission_analysis.py`](generate_package_balanced_permission_analysis.py) | Package-balanced / hierarchical permission sensitivity from frozen run + enrichment; offline only. Contract: [`docs/PACKAGE_BALANCED_PERMISSION_CONTRACT.md`](../../docs/PACKAGE_BALANCED_PERMISSION_CONTRACT.md) |
| [`generate_package_balance_attribution.py`](generate_package_balance_attribution.py) | Attributes RAT package-balance shifts, banker collisions, and source-batch×package coupling; offline only. Contract: [`docs/PACKAGE_BALANCE_ATTRIBUTION_CONTRACT.md`](../../docs/PACKAGE_BALANCE_ATTRIBUTION_CONTRACT.md) |
| [`generate_type_guard_suppression_audit.py`](generate_type_guard_suppression_audit.py) | Read-only audit of `type_guard_family_suppressed` rows in `prediction_errors_*.csv` (raw vs post-guard pairs; not holdout CM) |
| [`generate_research_hygiene_pack.py`](generate_research_hygiene_pack.py) | Holdout confidence calibration (ECE/Brier/support tiers) + split class accounting (206/169/132/train-only) + read-only Core Results v1 artifact map; no DB/Core writes |

The optional Zimperium IOC source is pinned as a Git submodule. Materialize it
only when running its coverage diagnostic:

```bash
git submodule update --init research/external_iocs/Zimperium-IOC
```

## Supported diagnostic entrypoints

The diagnostic scripts in this directory are the only supported command paths.
The former top-level wrappers were removed to keep one authoritative entrypoint
per diagnostic.

Database- or state-changing maintenance commands live under
[`scripts/maintenance/`](../maintenance/README.md), not in this directory.

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
