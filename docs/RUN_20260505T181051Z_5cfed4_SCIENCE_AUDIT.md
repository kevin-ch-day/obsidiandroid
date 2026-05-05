# Science & methodology audit: run `20260505T181051Z__5cfed4`

**Scope:** Read-only review of completed pipeline outputs. No code, model, tuning, or restructuring changes were made for this document.

**Run root:** `/home/secadmin/Laughlin/GitHub/obsidiandroid/output/runs/20260505T181051Z__5cfed4/`

**Profile / mode (from evidence index):** `research_all_malicious`, paper/evidence mode **off** (`paper_safe_status`: NOT_APPLICABLE).

**Pipeline verdict (from evidence index + observability):** `PASS` (including ablation, research validity, hostile audit). **Partial failures:** none (`diagnostics/partial_failures.md`).

---

## Executive summary

The run presents a **high headline Macro-F1 on a 19-class family task** (Random Forest **0.9703**, `n_test=251`) while ablation **`full_fused`** on family targets tops out around **0.923–0.924** Macro-F1 on the **same test count** but with a **smaller fitted column set (412 vs 498)** and, critically, **train/test membership that is not guaranteed to match** the headline path because split caching hashes the **encoded label vector** (see `run_observability_summary.json`). Vendor **parsed-metadata** ablation (`vendor_full`, **23** columns) is **near chance**; **multi-engine detection binaries** (`vendor_detection_binary_only`, **60** columns) are **strong**, which likely **redefines** what “vendor features” meant in an older paper table. **416** taxonomy consistency rows are dominated by **type slug alignment** (cohort coarse type vs paper-facing `type_slug` often **`banker`**), not by family slug disagreement. **Leakage assessment** flags **AV-label-informed** features (`Parsed Family`, `Threat Class`, `Malware Type` per `modality_method_contract.json`), so behavioral claims must be scoped carefully.

---

## 1. What exact scientific task is the main model solving?

| Question | Evidence-backed answer |
|----------|------------------------|
| **Primary supervised target** | `leakage_assessment.txt` states **ground truth label source: `family_id`**. The headline `model_comparison_summary_*.csv` does not restate the column name; treat **`family_id`** as the operational headline label unless a manifest override is introduced in a future run. |
| **How many classes in the headline task?** | **`19`** active classes in the model comparison table (`Classes=19` for RF/LR/XGB), with **`251`** test samples. |
| **39 families vs 19 classes** | The **prepared cohort** carries **`39`** distinct families (`distinct_families_canonical` / `family_id` in `recommended_findings.md` / cohort population table). After **min-family-support** gating, **`1001`** rows remain in the trainable pool (`cohort_funnel.md`, `run_observability_summary.json`). The **headline classifier evaluates `19` families** (supported subset for the primary task), not all 39. Macro-F1 is **only over those active classes** on the test shard. |

**Artifacts:** `output/runs/20260505T181051Z__5cfed4/diagnostics/leakage_assessment.txt`, `.../diagnostics/model_comparison_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/cohort_funnel.md`, `.../diagnostics/run_observability_summary.json`, `.../run_evidence_index.md`.

---

## 2. Why Macro-F1 **0.9703** (main RF) vs **~0.923** (`full_fused` + `family_id` + RF)?

**Reported numbers**

- Main: RF **Macro-F1 = 0.9703**, accuracy **0.9801**, `Samples=251`, `Classes=19` — `model_comparison_summary_20260505T181051Z__5cfed4.csv`.
- Ablation: `full_fused` + `family_id` + RF **macro_f1_score = 0.9232261890156628**, `samples_tested=251` — `ablation_summary_20260505T181051Z__5cfed4.csv` (lines 89–90).

**These are not apples-to-apples without additional reconciliation.**

1. **Different feature column counts (strong signal)**  
   - Main training stage: **`498`** columns post-prune (`pipeline_stage_summary.md`, `run_evidence_index.md`).  
   - Ablation schema audit: `full_fused__lt_family_id` uses **`412`** fit columns for RF — `ablation_feature_schema_audit.csv`.  
   So **`full_fused` in ablation is not the same column set as the production headline matrix** for this run.

2. **Train/test split may differ (strong signal)**  
   `run_observability_summary.json` → `ablation.cohort_gap_summary.train_test_split_cache_scoping` states that cached splits hash, among other things, the **encoded label vector**, and that **different ablation label targets do not reuse each other’s y assignments**. The headline path uses a **19-class** task; ablation `family_id` rows are reported in a context where **label stats still list 39 classes** for `family_id` in the ablation block of the same JSON. Even when **`samples_tested` both equal 251**, the **identity of test rows** can differ if the split key differs. **This is the leading explanation for a ~0.05 Macro-F1 gap** alongside the **86-column** feature mismatch.

3. **Same nominal test size ≠ same evaluation**  
   Do not equate `251` vs `251` without a **frozen `sample_id` list** or **split hash** tied to both tables.

4. **Label target alignment**  
   For `full_fused`, `family_canonical_default` and `family_id` ablation rows are **pairwise identical** in Macro-F1 in this CSV (e.g. RF **0.923226** for both), which is consistent with **parallel encoding** or **equivalent mapping** for this cohort—but the **headline 19-class task** is still a **different decision problem** than a **39-way family_id ablation** unless the ablation pipeline applies the **same support filter** and **same class mask**.

**Bottom line:** The discrepancy is **expected** until **one** frozen evaluation is defined: **same `sample_id` train/test**, **same post-prune column list**, **same class mask**, **same label column**.

**Artifacts:** `.../diagnostics/model_comparison_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/ablation_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/ablation_feature_schema_audit.csv`, `.../diagnostics/run_observability_summary.json`, `.../diagnostics/pipeline_stage_summary.md`.

---

## 3. Reconciling ablation vendor results with a prior paper table (“vendor moderate”)

**Current run (family targets, `n_test=251`)**

| Experiment (RF Macro-F1, `family_id`) | Value | Fit columns (schema audit) |
|--------------------------------------|-------|----------------------------|
| `vendor_full` | **~0.068** | **23** |
| `vendor_detection_binary_only` | **~0.805** | **60** |
| `permissions_raw` | **~0.924** | (permission-only block; see ablation summary) |

**Interpretation**

- **`vendor_full`** here is **not** “everything we know from AV.” It is a **narrow encoded vendor-metadata slice** (23 columns), against a **cohort where vendor merge authority is sparse** (see §4). Performance near **majority / weak baselines** is plausible.
- **`vendor_detection_binary_only`** carries **much richer detection geometry** (62 columns for `type_slug` targets) and matches the intuition of “AV engines say malware / family-ish structure” far better than parsed vendor strings.
- **Parser / gate reality:** `parser_quality.latest.csv` shows many vendors **`excluded_low_mapped`** with **low inclusion**—so **parsed vendor metadata is systematically downgraded** in this profile.

**Conclusion:** The “contradiction” with an older paper is **most likely definitional** (what was called “Vendor” vs current `vendor_full`), plus **stale numbers**, not a bare logical inconsistency. **`vendor_detection_binary_only` is the fairer successor** to an informal “AV / vendor signal” claim unless the paper explicitly meant **parsed family/type fields**.

**Artifacts:** `.../diagnostics/ablation_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/ablation_feature_schema_audit.csv`, `.../diagnostics/parser_quality.latest.csv`, `.../diagnostics/recommended_findings.md`.

---

## 4. `vendor_merge_n = 53`

**Where it appears**

- **`53`** = `vendor_merge_authority_unique_count` in `feature_build_coverage.latest.json`; note `vendor_merge_equals_final_index: false`.
- **`vendor_feature_rows: 53`** in `cohort_funnel.md` (aligned with manifest context in `recommended_findings.md`).
- JSON **row authority note** (`feature_build_coverage.latest.json`): fused matrix is **cohort-governed**; **vendor-only rows are unknown / zero-filled** when expanding to cohort.

**What it means**

- **53** is the count of samples with **authoritative vendor-merge rows** before reindexing to the full **1226**-row governed cohort—not the number of test/train rows.
- **Sparse vendor records + parser gates + join policy** explain **53**; it is **not** the cohort size.

**`vendor_detection_binary_only` vs 53**

- Observability lists **`vendor_detection_binary_only`** with **`raw_matrix_ids: 1226`** — same cohort height as other ablations (`run_observability_summary.json`). So **detection binaries are defined on the full cohort row index**, not limited to **53** merge keys.
- **`vendor_full`** still **zero-fills** most rows: only **53** carry non-authoritative-merge vendor features; the rest are **structurally missing** for that modality. That **dominates** the weak **`vendor_full`** result.

**Zero-fill caveat:** Any claim “vendor-only performance = vendor signal strength” must state that **most samples see all-zero vendor metadata**, i.e. the model sees **presence/absence of vendor-parse signal**, not a dense vendor tensor.

**Artifacts:** `.../diagnostics/feature_build_coverage.latest.json`, `.../diagnostics/cohort_funnel.md`, `.../diagnostics/run_observability_summary.json`.

---

## 5. Permission feature contribution

**Scale (fusion contract)**

- **399** permission columns in fused matrix; **408** raw permission features listed in modality contract with grouping counts (`dangerous_count`, `normal_count`, `oem_count`, `total_count`) — `modality_method_contract.json`.
- Fusion **560** total columns (**24** AV/vendor encoded, **399** permission, remainder “other” **137** per contract).

**Survival after pruning (`feature_column_survival.latest.csv`)**

- **`perm__*` columns:** **399**; **`retained_for_training=True`:** **380** (computed from CSV).
- **Highest `nonzero_count_final_training`** among retained `perm__` features (counts are on the **post-support-filter** training universe):  
  **`perm__total_count` (971)** → **`perm__normal_count` (970)** → **`perm__android_permission_internet` (951)** → **`perm__dangerous_count` (864)** → **`perm__android_permission_wake_lock` (853)** → **`perm__android_permission_receive_boot_completed` (797)** → **`perm__android_permission_access_network_state` (792)** → **`perm__android_permission_foreground_service` (779)** → **`perm__android_permission_read_phone_state` (614)** → **`perm__android_permission_read_sms` (586)** → **`perm__oem_count` (537)**.

**Plausibility**

- **`INTERNET`, `WAKE_LOCK`, `RECEIVE_BOOT_COMPLETED`, `READ_SMS`, `READ_PHONE_STATE`** are **standard Android banking / spyware / staged loader motifs**.  
- **Aggregate counts** (`total_count`, `dangerous_count`, `normal_count`, `oem_count`) dominate prevalence—consistent with **broad behavioral clustering**, not a single magic permission.

**Label-likeness / artifacts**

- This run does **not** ship per-feature RF importances in the listed artifact set; “most predictive” is proxied by **nonzero prevalence after leakage/low-info prune**, not causal importance.
- Separate **taxonomy / type ambiguity** (§7–8) can make permission signals **proxy for campaign type**; that is **not necessarily leakage**, but it **limits** “permission-only proves APK behavior independent of taxonomy.”

**Artifacts:** `.../diagnostics/modality_method_contract.json`, `.../diagnostics/feature_column_survival.latest.csv`, `.../diagnostics/permission_training_survival_20260505T181051Z__5cfed4.csv` (408 permission rows + header = 409 lines).

---

## 6. Leakage risk (`leakage_assessment.txt` + `feature_contract.json`)

**Documented assessments**

- `leakage_assessment.txt`: **Parsed Family**, **Threat Class**, **Malware Type** **used in features**; **leakage risk classification: AV-label-informed classification**. Ground truth: **`family_id`**.

**`feature_contract.json`**

- Large **`encoder_mappings`** include vendor-scoped tokens such as **`parsed_family_<vendor>`** and **`malware_type_<vendor>`**—these are **direct encodings of vendor-produced family/type strings**, i.e. **high coupling** between AV narrative and supervised label.

**Checklist vs user questions**

| Risk | Status in this artifact bundle |
|------|--------------------------------|
| Family names embedded in features | **Yes** — parsed-family encoders per vendor in `feature_contract.json`. |
| Type names embedded | **Yes** — `malware_type_*` mappings. |
| Vendor parsed family/type fields | **Yes** — explicit in modality contract (`fields`) and encoder mappings. |
| Package-name-derived leakage | **Not evidenced** in files opened for this audit; requires column-name review beyond encoder headers. |
| Duplicate SHA/package lineage leakage | **Not evidenced** from these diagnostics alone. |
| Time leakage | **Random split-style evaluation** (`train=750`, `test=251`); **no year-holdout** evidenced in run outputs; `paper_claim_audit.md` flags temporal claims as unsupported. |
| Train/test contamination | Split is **deterministic-split-audit**, but **ablation vs headline** split keys may differ (§2). |
| SMOTE | **No `SMOTE` string** located under this run directory in a quick grep of `*.json/md/txt/csv` — **no SMOTE placement to analyze from artifacts**. |

**Artifacts:** `.../diagnostics/leakage_assessment.txt`, `.../diagnostics/feature_contract.json`, `.../diagnostics/modality_method_contract.json`, `.../diagnostics/paper_claim_audit.md`.

---

## 7. Taxonomy mismatches (`taxonomy_consistency_mismatches_20260505T181051Z__5cfed4.csv`)

**Volume**

- **416** data rows (**417** lines incl. header).  
- **`mismatch_reason`:** **`type_mapping_mismatch` = 410**, **`type_label_missing` = 6**.

**What `type_mapping_mismatch` is doing here**

- Rows show **`cohort_raw_type_slug`** (e.g. `adware`, `stealer`, `sms-trojan`, `rat`) vs **`label_type_slug`** dominated by **`banker`**, with `type_slug_expected` tracking cohort-facing type and **`type_match=False`**.  
- **`label_family_match=True`** on the sampled rows—this is **primarily a type-axis inconsistency** between **cohort coarse type** and **paper-facing / label taxonomy type**, not family slug noise.

**Dominant patterns (computed from CSV)**

- Top **`family_canonical_expected`:** **applite (152)**, **pixpirate (120)**, **joker (80)**, **spynote (35)**, **xrat (20)**, …  
- Top **`cohort_raw_type_slug`:** **adware (152)**, **stealer (120)**, **sms-trojan (80)**, **rat (55)**, **banker (9)**.  
- Most common **`(type_slug_expected, label_type_slug)`:** **`(adware, banker)` 152**, **`(stealer, banker)` 112**, **`(sms-trojan, banker)` 79**, **`(rat, banker)` 54**, **`(stealer, spyware)` 7**.

**`type_label_missing` (6 rows)**

- Examples: **`rat/android.irata`**, **`rat/android.pixpirate`**, **`trojan/android.spynote[bi]`** with **`label_type_slug` empty** but cohort raw type present—suggests **missing label-parser coverage** or **taxonomy join gap** on those classification strings.

**Paper-facing impact**

- Any claim about **`type_slug` distribution** or **type-conditioned family metrics** must **surface this table** or a successor audit. Family-headline metrics can still **look strong** while **type metadata is systematically skewed**.

**Artifact:** `.../diagnostics/taxonomy_consistency_mismatches_20260505T181051Z__5cfed4.csv`.

---

## 8. Prediction errors (`prediction_errors_20260505T181051Z__5cfed4.csv`)

**Volume:** **8** rows (8 errs + header).

**Pattern**

- All eight have **`type_slug_expected=banker`** and **`label_type_slug=banker`**.  
- **True families** include **coper, joker, zanubis, trickmo, bankbot, flubot**; **predictions** are other **banker-adjacent** families (**Joker, TrickMo, Irata, Vultur, Coper**).  
- This is classic **within-type confusion** among **financial trojans**.

**Confidence**

- The CSV contains **no confidence / probability columns** — cannot summarize confidence from this artifact.

**Interpretation axes**

- **Structural similarity:** High—same **`banker`** type bucket.  
- **Taxonomy ambiguity:** Possibly—see taxonomy audit (`label_type_slug` vs cohort raw types elsewhere).  
- **Low support:** Cannot assert per-class support from this file alone.  
- **Model weakness:** **8 / 251** test errors (**~3.2%** mismatch rate) aligns with headline accuracy **~98%**.

**Artifact:** `.../diagnostics/prediction_errors_20260505T181051Z__5cfed4.csv`.

---

## 9. Model comparison & tuning

**Headline leaderboard** (`model_comparison_summary_*.csv`)

| Model | Macro-F1 | Accuracy | Samples | Classes |
|-------|----------|----------|---------|---------|
| **RandomForest** | **0.9703** | **0.9801** | 251 | 19 |
| LogisticRegression | 0.9421 | 0.9641 | 251 | 19 |
| XGBoost | 0.9324 | 0.9602 | 251 | 19 |

**Why RF tends to win on the headline family task**

- **Nonlinear** interactions among **sparse binary permissions** plus **heterogeneous modalities** suit tree ensembles when **linear separators** leave margin on the table.

**Where LR wins in ablations**

- Example: `full_fused` + **`type_slug`** → LR **Macro-F1 = 0.954256**, RF **0.930454**, XGB **0.927323** (`ablation_summary_*.csv` lines 92–94). Fewer (**6**) type classes plus **mostly linearly separable** geometry can favor **LR**.

**Should XGB stay in full ablation?**

- **Cost:** Ablation stage **~1502 s** logged (`pipeline_stage_summary.md`) for this run—the dominant slice of **~1687 s** overall (`run_summary.json`). Dropping XGB in **dev profiles** will materially shorten turnaround if **`RF+LR`** answers the scientific question.

**Paper model roster**

- For prose clarity: **`RF + LR`** as **primary nonlinear + calibrated linear** is defensible; XGB adds **marginal leaderboard rank** here at **integration cost**.

**Artifacts:** `.../diagnostics/model_comparison_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/ablation_summary_20260505T181051Z__5cfed4.csv`, `.../diagnostics/pipeline_stage_summary.md`, `.../run_summary.json`.

---

## 10. Paper-safe claims table

| claim | supported by which artifact | confidence | caveat | needs more work |
|-------|---------------------------|------------|--------|----------------|
| Pipeline completed successfully for this run | `run_evidence_index.md`, `run_observability_summary.json`, `partial_failures.md` | High | Evidence mode OFF | No |
| Headline RF Macro-F1 **0.9703** on **`n_test=251`**, **`19`** classes | `model_comparison_summary_20260505T181051Z__5cfed4.csv` | High | Exact label column inferred from **`leakage_assessment.txt` (`family_id`)**—manifest should eventually echo | Yes (manifest echo) |
| Cohort **`1226`** prepared → **`1001`** post family-support train pool → **`750/251`** split | `cohort_funnel.md`, `run_observability_summary.json` | High | “Train pool” ≠ “all cohort rows evaluated” | No |
| Fused permission count **399** + AV/vendor **24** = **560** pre-prune cols | `modality_method_contract.json` | High | Contract is run-scoped | No |
| Post-prune headline training uses **498** columns | `pipeline_stage_summary.md`, `run_evidence_index.md` | High | Ablation **`full_fused`** uses **412** cols (`ablation_feature_schema_audit.csv`) | Yes (unify definitions) |
| **`vendor_merge_authority`** touches **53** samples; cohort zero-fill elsewhere | `feature_build_coverage.latest.json`, `cohort_funnel.md` | High | Sparse modality | No |
| **`vendor_full` ≪ `vendor_detection_binary_only`** on family tasks | `ablation_summary_*.csv`, `ablation_feature_schema_audit.csv` | High | Definitions differ (**23 vs 60** cols) | No (for prose) |
| **`permissions_raw` ≈ `full_fused` RF Macro-F1 ~0.924** → permissions carry most marginal family signal vs this fused ablation slice | `ablation_summary_*.csv` | Medium | **`full_fused` ≠ headline 498-col path** | Yes |
| Taxonomy **`type_slug`** vs cohort raw types: **416** audited rows (**410 type_mapping**) | `taxonomy_consistency_mismatches_*.csv` | High | Mostly **banker label_type** vs granular cohort types | Yes (taxonomy policy) |
| Features include **vendor parsed family/type** → **AV-label-informed** | `leakage_assessment.txt`, `modality_method_contract.json`, `feature_contract.json` | High | Limits “pure APK behavior” wording | Yes (claim wording) |
| Temporal / 2026 outlook claims | *(none bundled)* | Low | **`paper_claim_audit.md`** marks unsupported | Yes |
| SMOTE-safe placement | *(not found)* | N/A | No SMOTE mention in grep of run outputs | Yes if SMOTE enabled elsewhere |

---

## 11. Things that do not make sense yet (prioritized)

| Issue | Why it matters | What would resolve it |
|-------|----------------|------------------------|
| **Headline Macro-F1 0.9703 vs `full_fused` ~0.923** | Same **`n_test=251`** invites false reconciliation | Emit **frozen `sample_id` lists** + **split hash** for both paths; align **498 vs 412** column manifests |
| **`vendor_merge_n=53` + weak `vendor_full`** | Readers infer “vendor should help” | Glossary:**`vendor_full` ≠ detection tensor**; report **density** (% nonzero rows per vendor column) |
| **Old paper “vendor moderate” vs current collapse** | Reviewer mistrust | Map old feature block → today’s **`vendor_detection_binary_only`**; archive stale table |
| **416 taxonomy rows / `banker` type skew** | Type-level claims unreliable | Decide authoritative type source; patch mapping or abstain |
| **`39` cohort families vs `19` headline classes** | Misread as inconsistency | Always pair **`n_classes_active`** with **support policy** |
| **Leakage wording vs strength** | Ethics / science framing | Decide whether parsed vendor labels are **admitted artifacts** or **disallowed** |

---

## Supplemental diagnostics (lightly used here)

| Artifact | Role in this audit |
|----------|--------------------|
| `diagnostics/engine_scoring_summary.csv` | Engine coverage / tiers; contextual for vendor gates, not headline F1. |
| `diagnostics/vendor_gate_top10_pre_gate.latest.csv` | “Leakage safe score raw” leaderboard—methodological sanity, not supervised metrics. |

---

## Open questions before tuning or paper edits

1. **Single evaluation contract:** One JSON manifest that binds **`sample_id` train/test**, **`label_column`**, **`class_mask`**, **`post_prune column list hash`** for headline + every ablation row cited in the paper.

2. **Define “vendor” for readers:** Parsed metadata (`vendor_full`) vs **engine detection binaries** (`vendor_detection_binary_only`) vs **scores** (`vendor_consensus_scores_only`)—three different scientific claims.

3. **Taxonomy SOP:** How **`type_slug`** relates to **`cohort_raw_type_slug`** when they disagree (**410 rows**).

4. **Leakage stance:** Either **disclose AV-label-informed** features as deliberate **privileged information** modeling, or **strip** parsed vendor labels for a **strict APK-only** claim.

5. **Ablation cost policy:** Whether **dev** profiles should default to **`RF+LR`** only given **~25 min** ablation stage time on this host.

---

*End of audit (analysis only).*
