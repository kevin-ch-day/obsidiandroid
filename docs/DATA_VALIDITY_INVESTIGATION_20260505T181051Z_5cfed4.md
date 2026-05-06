# Data validity & evidence-contract investigation

**Run:** `20260505T181051Z__5cfed4`  
**Scope:** Analysis and traceability only — no model tuning, no hyperparameter changes, no pipeline restructuring, no cohort changes.  
**Purpose:** Surface the largest evidence-contract breaks before tuning or paper edits.

---

## Priority 1 — Evaluation contract / split traceability

### Root cause of `manifest.split.split_hash` ≠ `split_freeze_audit*.csv.split_hash`

| Source | Hash | Meaning |
|--------|------|--------|
| `run_manifest.json` → `split.split_hash` | `ea84c6cad40abba1e6b0fde263cb3cde23e0e50a4021041d27221827b7c827d2` | **Frozen when the pipeline captured `manifest_context["split"]` immediately after headline training**, from `RUNTIME_SPLIT_METADATA` (canonical `obsidiandroid.pipeline.runner`; legacy `analysis.pipeline.runner` is a shim). |
| `split_freeze_audit_20260505T181051Z__5cfed4.csv` (embedded + recomputed from rows) | `b208899b828a407a77991001fd884b9a0e5f840ad823fe7dc2de07488576fa14` | **Hash of train/test assignment actually written into the CSV on disk**, using the algorithm in `_export_split_audit` (see below). |

**Mechanism**

1. **Headline training** trains RF/LR/XGB; each call runs `train_model_factory` → `_export_split_audit`, which computes `split_hash = SHA256(canonical_csv_bytes(sample_id, sha256, split_role sorted by sha256, sample_id))` and writes `split_freeze_audit_<run>.csv`:

```187:214:ml_classification/training/model_trainer_factory.py
    canonical_rows: list[dict[str, str | int]] = []
    for _, row in split_df.iterrows():
        ...
    canonical_rows.sort(key=lambda item: (item["sha256"], item["sample_id"]))
    canonical_bytes = canonicalization.canonical_csv_bytes(
        rows=canonical_rows,
        fieldnames=["sample_id", "sha256", "split_role"],
    )
    split_hash = hashlib.sha256(canonical_bytes).hexdigest()
    ...
    split_df["split_hash"] = split_hash
```

2. **Immediately after headline training**, the runner snapshots this metadata into **`manifest_context["split"]`** (authoritative headline contract at that instant):

```1259:1265:analysis/pipeline/runner.py
        split_meta = getattr(app_config, "RUNTIME_SPLIT_METADATA", None)
        ...
        if isinstance(split_meta, dict):
            manifest_context["split"] = dict(split_meta)
```

3. **Later, the ablation stage** sets `RUNTIME_ABLATION_ACTIVE = True`, which forces `n_features_key = 0` in the split cache key (instead of headline column count):

```73:87:ml_classification/training/model_trainer_factory.py
    ablation_lock = bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False))
    n_features_key = 0 if ablation_lock else int(features_df.shape[1])
    return (
        int(len(features_df)),
        n_features_key,
        index_hash,
        label_hash,
        ...
```

4. Changing `n_features_key` (498 vs **0**) for the **same** row count index and encoded labels ⇒ **different `split_cache_key`** from headline ⇒ **different stratified partitions** whenever a cache miss occurs.

5. Ablation grids run many label matrices; **`_export_split_audit` overwrites `split_freeze_audit_<run>.csv`** each time a *new* split is materialized at the **last** qualifying training call. **`manifest_context["split"]` is not rewritten after ablations**, so the manifest still cites **ea84…** while the CSV on disk ends at **b208…**.

### Which hash is authoritative?

| Question | Answer |
|----------|--------|
| Headline RF train/test assignment for Macro-F1=0.9703? | **`ea84c6ca…`** (manifest / post-headline-training `RUNTIME_SPLIT_METADATA`) describes the headline contract — **provided** you still possess the CSV that matched that hash. |
| What the CSV on disk proves today? | **`b208899b…`** — aligns with **an ablation-time** split, **not** the headline hash in the manifest. |
| **Operational truth** today | **`split_audit_path` in the manifest points at a file whose embedded hash contradicts `manifest.split.split_hash`** — the evidence bundle is **self-inconsistent**. |

### Can we prove headline RF vs `full_fused` / `family_id` used the **same test `sample_id` set?

**No from current artifacts alone.** Reasons:

1. Headline vs ablation **`split_cache_key` differ on `n_features_key`** (`498` vs `0`) even when encoded labels coincide.  
2. The only row-level ledger file (`split_freeze_audit_*.csv`) has been overwritten and now matches **`b208…`**, while the manifest freezes **`ea84…`**.

**Consequence:** Comparisons between headline RF Macro-F1 and ablation **`full_fused` + `family_id`** Macro-F1 (251 test rows reported in both summaries) share **counts** but **not provably the same identities** unless a headline-only split export is reconstructed or regenerated.

---

### Priority 1 — Comparison table (as requested)

Values are artifact-backed; placeholders mark **lost or not exported** columns.

| Field | Headline RF (model comparison leaderboard) | Ablation `full_fused` + `family_id` + RF (`ablation_summary_*.csv`) |
|-------|--------------------------------------------|----------------------------------------------------------------------|
| **Label field (operational)** | **`family_id`** first in alignment priority when both `family_id` and `family_canonical` exist (`extract_aligned_labels`); labels carried as numeric **string ids** (`"13"`, `"44"`… in RF metadata classes). **`experiment_contract_snapshot` says `family_canonical` — contradicts operational default.** | **`family_id`** via `forced_label_column="family_id"` in `_prepare_training_inputs`. |
| **Active class count** | **19** (`model_comparison_summary_*`, RF metadata `num_classes`) | **Treat as 19** for family task after low-support masking (same min-support pathway as headline); ablation summaries do not restate encoder class count separately. |
| **train_n** | **750** | **750** (`samples_tested` + symmetry with same pool size 1001) |
| **test_n** | **251** | **251** |
| **Train `sample_id` hash** | **Not present** — headline-specific row list tied to **`ea84…`** is **not retained** once CSV overwritten. Derive via repro or new export keyed to manifest hash. | **Same gap** unless ablation emits per-experiment audits. Current CSV matches **`b208…`** last writer. |
| **Test `sample_id` hash** | Same | Same |
| **Split hash recorded** | **`ea84c6cad40abba1e6b0fde263cb3cde23e0e50a4021041d27221827b7c827d2`** (`run_manifest.json`, `experiment_contract_snapshot*.json`, `experiment_registry*.json`) | **On-disk audit file `b208899b…`** — mismatch with manifest headline hash. |

| Field | Headline RF | Ablation row |
|-------|-------------|--------------|
| **Split hash authority** | `run_manifest.json` **`split`** block (captures headline training-era metadata) — **⚠ inconsistent with CSV path it names** | **Intent:** per `_build_split_cache_key` + stratify; **On disk:** **`b208…`** CSV |
| **Post-prune column count** | **498** (`pipeline_stage_summary.md`, `run_evidence_index.md`) | **412** fitted columns (`ablation_feature_schema_audit.csv`, `full_fused__lt_family_id` × RF). |
| **Post-prune column hash** | **Not official in manifests.** **Derived surrogate:** `SHA256` of newline-joined sorted `feature_name` with `retained_for_training=True` in `feature_column_survival.latest.csv` → **`aa266fcff8a4c395fd59cacf74b3f5fa6cf351235bde1a4361b12578a001eadc`**. | **No column-name export found** for fitted ablation schemas in this run; **needs explicit artifact** (`fit_columns` blob per experiment). |
| **Fusion pre-prune column hash (contract)** | `modality_method_contract.json` → `fusion_modality.feature_columns_hash` **`89e562d75ed480d71532ba323e3f7d5b4cae34751c0014a77507c9cc996e416e`** | Same underlying fused source before ablation-specific pruning differs. |
| **Macro-F1** | **0.9702989992463676** | **0.9232261890156628** |
| **Confusion matrix path** | **`random_forest` metadata cites** `confusion_matrix_random_forest.png` (**file missing**) —see Priority 2. | **Ablation summary CSV references** `confusion_matrix_full_fused__lt_family_id__random_forest.png` — **this file is absent** in the run’s `conf_matrices/` dir (only two PNGs saved: `*_permissions_grouped*` and `confusion_matrix_primary.png`). **Evidence chain broken** unless matrices were pruned or redirected. |

---

## Priority 2 — Confusion matrix provenance

### What happened

`_export_confusion_matrix_provenance` resolves a path via `_find_primary_confusion_matrix`:

```1496:1428:analysis/pipeline/stage_manifest.py
def _find_primary_confusion_matrix(*, run_root: Path, top_model: str, evidence_mode: bool = False) -> Path | None:
    cm_dir = run_root / "conf_matrices"
    ...
    if evidence_mode:
        rf_candidate = cm_dir / "confusion_matrix_random_forest.png"
        ...
    ...
    with_suffix = list(cm_dir.glob(f"confusion_matrix_*{top_model}.png"))
    if with_suffix:
        return sorted(with_suffix)[0]
```

This run operated with **`paper_mode` / strict evidence routing off**, so **`evidence_mode` is False** and the exporter takes **`sorted(with_suffix)[0]`** — lexicographic first match — not `confusion_matrix_random_forest.png`.

**On disk** under `conf_matrices/` only two PNGs exist:

| File | Size | SHA-256 |
|------|------|---------|
| `confusion_matrix_permissions_grouped__lt_family_canonical_default__random_forest.png` | 366712 | `dc3c79228137dca9264f01509026d0c2c5b13b3156b43ae4f441721db137894e` |
| `confusion_matrix_primary.png` | 366712 | **identical** |

**`cmp` / `sha256sum`:** **byte-identical** — same matrix image saved twice.

**Provenance CSV** points to the **ablation-style filename** (`permissions_grouped__lt_family_canonical_default…`) because it sorts first lexicographically before `confusion_matrix_primary.png`.

**Headline RF metadata** (`models/random_forest/random_forest_classifier_model_metadata.json`) lists:

`"confusion_matrix_path": ".../confusion_matrix_random_forest.png"` — **that file does not exist** in the run directory.

### Which matrix matches Macro-F1=0.9703?

The **evaluation metrics** in RF metadata (**accuracy/macro-F1/samples_tested=251**) are consistent with leaderboard CSVs. Visually exported PNG **`confusion_matrix_primary.png`** (duplicate of provenance-selected file) is the **promoted** graphic; filenames are misleading.

### Is provenance mixing ablation and headline?

**Yes.** Filename encodes **`permissions_grouped` ablation** while metrics are headline RF scores — **semantic mismatch**.

### Ablation confusion matrices on disk

`ablation_summary_<run>.csv` records many `conf_matrices/confusion_matrix_<experiment>__lt_<target>_<model>.png` paths, but this run’s **`conf_matrices/` directory contains only the two headline-related PNGs above** — **ablation figures are not retained** (or were never written to this folder). Treat ablation matrix paths in the CSV as **stale references** unless reproduced.

### Correction report summary

| Item | Status |
|------|--------|
| **Expected headline artifact** | `confusion_matrix_random_forest.png` (per model metadata expectation) |
| **Actual files present** | `confusion_matrix_primary.png` ⊗ duplicate of `permissions_grouped__lt_…__random_forest.png`; **missing** `confusion_matrix_random_forest.png` |
| **Byte identity** | The two existing PNGs are **identical** |
| **Code writing provenance** | `finalize_run_manifest_stage` → `_export_confusion_matrix_provenance` (`analysis/pipeline/stage_manifest.py`) |
| **Suggested fix direction** *(decision deferred — investigation only)* | (1) Save headline matrix explicitly as `confusion_matrix_random_forest.png`. (2) Change `_find_primary_confusion_matrix` non-evidence branch to **`confusion_matrix_primary.png` first**. (3) Persist provenance **`split_hash`** and **`feature_fit_hash`** beside every matrix. |

---

## Priority 3 — True held-out test errors (headline RF)

### Facts

| Artifact | What it counts | Comparable to headline test RMSE / errors? |
|----------|----------------|-----------------------------------------------|
| `prediction_errors_<run>.csv` + `taxonomy_consistency_summary_*.json` | **`family_canonical_expected` vs taxonomy `predicted_family`** across **rows_evaluated=1001** | **No** |
| `confusion_within_vs_cross_type_<run>.csv` | Built from **`model_results["prediction_metadata"]` over pooled predictions**, not constrained to test rows (`_build_type_confusion_summary`). | **No** — **total_error=8** ≠ headline test miscount (below). |

### Headline test error **count** (from official metrics)

- `accuracy = 0.9800796812749004`, `samples_tested = 251` → **expected wrong predictions on test ≈ 5** (251 × (1 − accuracy) ≈ **4.999**).

### Nearest row-level proxy in this run: `misclassified_samples_by_type_<run>.csv`

Source: **full-cohort** prediction keys (see `stage_permission_trends_report._build_type_confusion_summary`). **Eight** rows — **must not** be read as “test errors.”

**Joining** those eight IDs to **on-disk** `split_freeze_audit` (which is **ablation-era** `b208…`, not headline `ea84…`) yields:

| split_role (⚠ not headline) | Count |
|----------------------------|------:|
| train | 6 |
| test | 2 |

The **two** IDs marked `test` under **ablation** split: **15397**, **20428** (Zanubis→Irata, Coper→TrickMo by family id map).

**Because the split file no longer matches headline hash, this join is not headline-safe.**

### Confidence

- **Per-sample test confidences** for misclassified test rows are **not exported** in CSV/JSON diagnostics checked.  
- **Per-family** mean confidence exists: `per_family_performance_spread_<run>.csv` (`avg_confidence`) — **aggregate**, not error slice.  
- **Recovery path:** load `random_forest_classifier_model.joblib`, rebuild **headline** `X_test, y_test` with **headline** split (once restored), call `predict_proba` — **not done here** (requires split export or repro).

### Overlap with taxonomy mismatches

- Intersection of **misclassified** `sample_id` set with `taxonomy_consistency_mismatches_*.csv`: **{15373}** only (1/8).

### Permission / vendor coverage for misclassified (cohort coverage audit)

| sample_id | has_vendor_features | in_permission_feature_matrix |
|-----------|---------------------|-------------------------------|
| 540 | False | True |
| 10053 | False | True |
| 15373 | False | False |
| 15397 | False | False |
| 20340 | False | True |
| 20428 | False | False |
| 20610 | False | True |
| 20614 | False | True |

Interpretation lines up with cohort reality: vendor gate rows **sparse** (53); failures are overwhelmingly **within bank malware** classes by type.

---

## Priority 4 — Feature signal semantics (vendor vs nonzero counts)

### Row coverage (`feature_modality_coverage_audit.latest.csv`, 1226 cohort rows)

| Flag | True | False |
|------|-----:|------:|
| `vendor_parser_gate_passed` | **53** | 1173 |
| `has_vendor_features` | **53** | 1173 |
| `in_permission_feature_matrix` | **1185** | **41** |

### Why `feature_column_survival` shows ~1001 `nonzero_count_final_training` on `parsed_family_*`

After cohort expansion, vendor columns **`NaN` → unknown sentinel**:

```348:349:ml_classification/vectorization/feature_vector_builder.py
        unk = _unknown_like_code(col, encoder_mappings)
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(unk)
```

Unknown token codes are drawn from **`feature_contract.json` encoder_mappings** (`_unknown_like_code` prefers `"unknown"`). Example: **`parsed_family_alibaba` maps `"unknown"` → `20`** — **nonzero**.

Therefore **`nonzero_count_final_training`** answers “**≠ numeric 0**”, **not** “has non‑unknown categorical signal.” That statistic is **misleading** for categorical vendor modalities.

### **Meaningful signal count** — empirical computation (aligned fused matrix vs gate)

Aligned matrix: `aligned_features_<run>.csv.gz` (1226×560).

| Feature | `unknown` code | Rows `!= 0` (misleading) | Rows **`!= unknown`** |
|---------|---------------|--------------------------|-----------------------|
| `parsed_family_alibaba` | **20** | 1225 | **47** |
| `parsed_family_drweb` | **20** | 1218 | **32** |
| `malware_type_alibaba` | **2** | 1219 | **47** |

Counts **≠ unknown** coincide with **`vendor_parser_gate_passed`** rows (~53) conceptually (**47 aligns with gated vendor coverage for that vendor-specific column**, not strictly 53 per column).

### Grouped modality template (coverage → metrics)

For each modality group interpret:

| Quantity | Recommendation |
|----------|---------------|
| **Row coverage** | Use `feature_modality_coverage_audit` |
| **`nonzero` on categoricals with unknown code** | **Do not use** as “signal presence” |
| **`non-missing` / `meaningful`** | Count rows where value **≠ unknown sentinel** from `feature_contract.json` (and optionally intersect **gate-pass** rows) |
| **Sentinel** | `unknown` (or first label key in `_unknown_like_code`) |
| **Caveat** | Integer **0** also possible when no `"unknown"` key exists (**fallback**) |

---

## Priority 5 — Label / taxonomy authority

### `family_canonical` vs `family_id`

| Artifact | Assertion |
|---------|-----------|
| `experiment_contract_snapshot_<run>.json` | `target_task.label_field`: **`family_canonical`** |
| `leakage_assessment.txt` | **Ground truth label source:** **`family_id`** |
| **`extract_aligned_labels` default priority** | **`["family_id", "family_canonical", "family_name"]`** — **`family_id` wins** when column exists |

Operational headline training therefore uses **`family_id` string tokens** internally; **`label_name_map`** may attach **`family_canonical`** display names**. This **resolves leakage text vs contract**: both refer to consistent rows, **but prose must not claim headline is “canonical-only” supervision** unless the pipeline is forced onto `family_canonical`.

### `family_canonical_default` ablation label

The tuple `("family_canonical_default", None)` still invokes alignment with **`forced_label_column=None`**, so **`family_id` wins** whenever present — slug name is misleading vs actual column priority.

### Taxonomy mismatches CSV — executive read

410 / 416 rows = **`type_mapping_mismatch`** — **`type_slug_expected` (cohort / structural type)** vs **`label_type_slug` extracted from `classification_label`**, flagged when both are canonical slug tokens but disagree (dominant mismatch: granular cohort types **`adware`, `stealer`, `sms-trojan`, `rat`** paired with **`label_type_slug = banker`**).

**Operational meaning:** taxonomy join / label-string typing disagrees with cohort type field — **not** “model confused two families” by itself.

**Paper-facing risk:** **High** for **type distribution** or **type-conditioned** claims unless **416 audited rows** are addressed or claims caveated. Many rows still `appears_in_paper_facing_summaries=True` in this run’s export mode.

**What to do with 416 rows:**  
1) Define **authoritative type** (cohort `type_slug` vs reverse-parsed classifier string).  
2) Fix mapping table or downgrade paper claims until mismatch rate materially drops under strict gates.

---

## Priority 6 — Feature-set glossary (current → old paper language)

Abbreviated roster (counts from `ablation_feature_schema_audit.csv` + modality contract):

| Current `feature_set` | Meaning | Typical fit cols | Row coverage caveats | AV-label-informed? | Old paper “bucket” analogue |
|----------------------|---------|------------------|----------------------|---------------------|----------------------------|
| `vendor_full` | Encoded Parsed Family / Malware Type / Threat Class tensors | ~**23** | Vendor tensor sparse; gated | **High** (`vendor_label_leakage_audit` notes semantic leakage risk) | **Not** coarse “engines agree malware” — **parsed strings** |
| `vendor_detection_binary_only` | Engine detection geometry (binary / wide) | **60–62** | Full cohort index after reindex | Partially (detection outcome, not family name) | **Closest** to informal “AV / vendor signal strength” in many reader’s heads |
| `vendor_consensus_scores_only` | Narrow consensus scalars | **5** | Sparse / weak | Contextual | Old “consensus score only” |
| `permissions_raw` | Raw permission indicators | many | 1185/1226 in perm matrix | No | “Permissions” |
| `permissions_grouped` | Grouped counts + structure | fewer | same | No | “Permissions (grouped)” |
| `full_fused` | Permissions + metadata + vendor encodings (+ other) — post ablation pruning | **412–431** by target | cohort reindexed | Mixed | “Fused / multimodal” |

**Recommendation for paper reconciliation:** redefine tables to **name** `vendor_detection_binary_only` when historical text meant **engine-level** malware signal; **`vendor_full`** when text meant **vendor-parsed taxonomy strings**.

---

## Consolidated blocker list (for the follow‑up decision)

1. **`split_audit_path` / `manifest.split_hash` / on-disk CSV** — **triple break** — fix evidence export sequencing or split versioning (headline vs ablation) before trusting any stratified comparator.  
2. **Confusion matrix filenames + provenance** — pointer uses **first glob match** lexicographically; **`confusion_matrix_random_forest.png` missing**.  
3. **`misclassified_samples_by_type` / `prediction_errors`** — pooled or taxonomy-scope; **not** headline test auditing. True test error table requires **headline-split restoration** plus prediction export or joblib inference.  
4. **Vendor categorical `nonzero` counts** — replace with **`!= unknown sentinel`** semantics in any scientific narrative.  
5. **Contract naming** (`family_canonical` headline target vs actual `family_id` priority).

---

### Primary artifact references

```
output/runs/20260505T181051Z__5cfed4/run_manifest.json
output/runs/20260505T181051Z__5cfed4/diagnostics/split_freeze_audit_20260505T181051Z__5cfed4.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/experiment_contract_snapshot_20260505T181051Z__5cfed4.json
output/runs/20260505T181051Z__5cfed4/diagnostics/confusion_matrix_provenance_20260505T181051Z__5cfed4.csv
output/runs/20260505T181051Z__5cfed4/conf_matrices/confusion_matrix_primary.png
output/runs/20260505T181051Z__5cfed4/conf_matrices/confusion_matrix_permissions_grouped__lt_family_canonical_default__random_forest.png
output/runs/20260505T181051Z__5cfed4/models/random_forest/random_forest_classifier_model_metadata.json
output/runs/20260505T181051Z__5cfed4/diagnostics/misclassified_samples_by_type_20260505T181051Z__5cfed4.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/feature_modality_coverage_audit.latest.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/feature_column_survival.latest.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/aligned_features_20260505T181051Z__5cfed4.csv.gz
output/runs/20260505T181051Z__5cfed4/diagnostics/modality_method_contract.json
output/runs/20260505T181051Z__5cfed4/diagnostics/ablation_feature_schema_audit.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/ablation_summary_20260505T181051Z__5cfed4.csv
output/runs/20260505T181051Z__5cfed4/diagnostics/taxonomy_consistency_mismatches_20260505T181051Z__5cfed4.csv
```

---

*End of investigation (analysis only).*
