# Controlled permission-trend study v1.2 (supersedes v1.1) (`obsidiandroid.research.trends`)

Descriptive statistics over the frozen analytical dataset `analytical_dataset_v1.parquet`
(sha256 `affcf710ad0e630f3a1004637be1754a98c4c2b91f1fdb1224c67482557c874d`, registry row
`NOV15_ANALYTICAL_DATASET_V1`). No database access, no provider access, no model fitting; the code refuses
to load a Parquet whose digest differs from the one passed on the command line.

v1.1 is the separately versioned correction of the v1 study (results packet `2026-11-15_trend_study_v1`, draft PR #24) and of
the sealed descriptive report D0 (`2026-11-15_descriptive_report_d0`). Neither sealed packet nor the pre-registration is
edited; the corrections respond to the independent D0 verification (`2026-11-15_d0_verification/REVIEW.md`) and the
retrospective audit (`2026-11-15_independent_retrospective_audit_20261116T011238Z/REVIEW.md`).

## v1.2 corrections (after Codex's verification `2026-11-16_source_type_lineage_verification_20261116T044315Z`)

| # | Defect in v1.1 | v1.2 behaviour | Where |
|---|---|---|---|
| 1 | matched (T4) bootstrap recomputed profile weights **within SDK band**, with fixed capacities and bands dropping out of draws; registered rule 3 is profile within year and population | `matched_malware_bootstrap_registered`: one year-level batch draw, profile weights recomputed within year × population and applied to every band, re-standardization; capacities reported **both** fixed (`*_fixed_capacity` columns) and recomputed (default columns) because rule 5 is silent; `unit_mass_check` emitted; the v1.1 design survives only as arm S14 | `matching.py` |
| 2 | P3 reported a point gap only | `fixed_target_gap_bootstrap`: target fixed on the original rows, paired batch-resampled interval with recomputed weights, additive profile decomposition, fixed-target leave-one-batch-out; written to `P3_fixed_target_detail.json` and into the scorecard evidence | `matching.py`, `study.py` |
| 3 | manifests carried no code identity | `code_commit` in every manifest | `study.py`, `cli.py` |

## What v1.1 corrects (each recorded in table metadata and `selection_ledger.json`)

| # | Defect in D0 / v1 | v1.1 behaviour | Where |
|---|---|---|---|
| 1 | Bootstrap kept original design weights; a repeated batch carried > 1 mass per profile | `cluster_unit_recomputed`: cluster weights are recomputed on every resampled population, unit mass per represented cluster (`unit_mass_check` = 0 is emitted) | `bootstrap.cluster_unit_bands`, `matching.matched_malware_band_bootstrap` |
| 2 | Weights computed before the 2017 eligibility filter (D0) | Weights are always computed on the filtered population (already so in v1; now asserted by the 2017 series test) | `weighting`, `study._filter` |
| 3 | Year range hard-coded 2011–2026; the 2010 detected row vanished | Year range derived from the data; T1 asserts that its row sum equals the detected population | `study.run_study` (T1, T7, TB) |
| 4 | Missing / placeholder metadata (`n_clusters = 0`, capacities that did not describe the computed population) | Every table carries unit, estimand, estimator, denominator, n_rows and a real n_clusters; T4 strata keep both capacity definitions | `study._meta`, `matching.strata` |
| 5 | Unregistered ≥ 1 % dangerous-permission cutoff | Primary reports the full registered dangerous tier (unobserved permissions appear with `observed_any = False`); the cutoff is the explicit, non-registered arm S12 | `study._dangerous_universe` |
| 6 | Heatmaps turned not-ranked cells into zeros | Heatmaps keep unmeasured cells missing (grey) and their CSV keeps NaN; TB heatmap measures every displayed year for the union of per-year top-10 | `figures.fig_heatmap`, TB |
| — | "REAL" stability label | `SIGN_STABLE_BAND_EXCLUDES_ZERO` / `SIGN_STABLE_BAND_INCLUDES_ZERO` / `COMPOSITION_DEPENDENT`; verdict rows `VERDICT_STABLE` / `VERDICT_ARM_DEPENDENT` / `VERDICT_DEGENERATE_IN_FLIPPING_ARMS`; every row notes that sign stability is not a significance test | `stability.py` |
| — | Builder progress log used estimated clocks | `started_utc` / `finished_utc` from the system clock in every manifest | `study`, `cli` |

D0 table mapping: a → T1, b → TB, c → T4 (+ `T4_strata`), d → T7, e → T6, f → `scorecard` (+ `series_*.csv`). T2, T3, T5, T8
are additional tables and are marked `registered_table: false` where they are not in the pre-registration.

## Inputs (all frozen)
- The Parquet and its `denominators.json` / `pi_identity_catalog_fixture.json` (dangerous tier) from the Lift A packet.
- `PREREGISTRATION.md` (predictions P1–P5, analysis rules, seed 20261115); its sha256 is stamped on every table.
- `config/research/android_platform_event_annotations_v1.json`: contextual markers only, drawn as labeled vertical lines.
- `config/research/trend_study_bands_v1.json`: target-SDK band variants (primary / tight / loose).

## Rules (from the pre-registration)
Unit = permission-profile cluster (`perm_profile_hash`) within year × population, weight 1/cluster size recomputed on each
resampled population; 2017 excluded via `trend_year_eligible`; DETECTED_V2 = `det_malicious >= 4 AND source_class_state !=
'BENIGN_0'`; BENIGN_SOURCE_V2 = `label_v2_provenance == 'BENIGN_SOURCE_LABELED'`; benign comparison 2018–2021 on matched
year × target-SDK band with dictionary-conditioned capacities; 95 % bands by batch resampling (1,000 resamples,
`numpy.random.default_rng(20261115)`); detection reflects engine state at `time_analysis`.

## Reproduce
```bash
python -m obsidiandroid.research.trends run --parquet <path> --digest affcf710ad0e630f3a1004637be1754a98c4c2b91f1fdb1224c67482557c874d \
  --prereg <PREREGISTRATION.md> --annotations config/research/android_platform_event_annotations_v1.json \
  --fixture <pi_identity_catalog_fixture.json> --out <packet dir> [--sensitivity all|S1_raw,S4_floor2,...]
python -m obsidiandroid.research.trends.stability --primary <out>/primary --sensitivity <out>/sensitivity --out STABILITY.csv
make test-research-trends
```
Requires pyarrow at run time (not a repository dependency; the tests use synthetic frames and never read a Parquet).
Outputs per arm: `selection_ledger.json` (every filter step with row counts, the dangerous-tier selection rule and omissions,
the stored-group cross-check), `T1_*.csv … T8_*.csv`, `TB_top30_per_year.csv` with `*.meta.json` (dataset digest, registry
row, denominator entry, unit, estimand, estimator, n rows, n clusters, weighting mode, pre-registration hash, arm,
registered-arm flag), `scorecard.csv`, `figures/*.png|svg|csv`, `run_manifest.json` (UTC start/finish, wall clock).

## Sensitivity arms
S1 weighting (raw / cluster / one-per-cluster × 5 seeds) · S2 2017 included · S3 test-key rows excluded · S4 detection floor 2 / 6 ·
S5 report age ≤ 365 d · S6 time axis = target-SDK or min-SDK band · S7 batch leave-one-out, mh100k only, no mh100k ·
S8 type from v1.1 / AVClass class token · S9 band widths tight / loose and an explicitly wrong unmatched reference arm ·
S10 casefolded permission identity · S11 signer clusters as the unit · **S12 (new, exploratory)** v1's ≥ 1 % dangerous cutoff ·
**S13 (new)** fixed-design bootstrap weights (the D0 / v1 estimator) so the effect of the estimator correction is visible.
Only the primary arm is pre-registered; every other arm carries `registered_arm: false`.

Outputs never contain certificate common names: only thumbprint hashes and cluster sizes.
