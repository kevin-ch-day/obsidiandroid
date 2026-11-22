# Controlled permission-trend study v1 (`obsidiandroid.research.trends`)

Historical documentation for the original study. See the [corrected study](TREND_STUDY_V1_2.md) for the current methods and reproduction commands.

Descriptive statistics over the frozen analytical dataset `analytical_dataset_v1.parquet`
(sha256 `affcf710ad0e630f3a1004637be1754a98c4c2b91f1fdb1224c67482557c874d`, registry row
`NOV15_ANALYTICAL_DATASET_V1`). No database access, no provider access, no model fitting; the code refuses
to load a Parquet whose digest differs from the one passed on the command line.

## Inputs (all frozen)
- The Parquet and its `denominators.json` / `pi_identity_catalog_fixture.json` (dangerous tier) from the Lift A packet.
- `PREREGISTRATION.md` (predictions P1–P5, analysis rules, seed 20261115); its sha256 is stamped on every table.
- `config/research/android_platform_event_annotations_v1.json`: contextual markers only, drawn as labeled vertical lines.
- `config/research/trend_study_bands_v1.json`: target-SDK band variants (primary / tight / loose).

## Rules (from the pre-registration)
Unit = permission-profile cluster (`perm_profile_hash`) within year × population, weight 1/cluster size; 2017 excluded via
`trend_year_eligible`; DETECTED_V2 = `det_malicious >= 4 AND source_class_state != 'BENIGN_0'`; BENIGN_SOURCE_V2 =
`label_v2_provenance == 'BENIGN_SOURCE_LABELED'`; benign comparison 2018–2021 on matched year × target-SDK band; 95 % bands by
batch resampling (1,000 resamples, `numpy.random.default_rng(20261115)`); detection reflects engine state at `time_analysis`.

## Reproduce
```bash
python -m obsidiandroid.research.trends run --parquet <path> --digest affcf710ad0e630f3a1004637be1754a98c4c2b91f1fdb1224c67482557c874d \
  --prereg <PREREGISTRATION.md> --annotations config/research/android_platform_event_annotations_v1.json \
  --fixture <pi_identity_catalog_fixture.json> --out <packet dir> [--sensitivity all|S1_raw,S4_floor2,...]
make test-research-trends
```
Requires pyarrow at run time (not a repository dependency; the tests use synthetic frames and never read a Parquet).
Outputs per arm: `T1_*.csv … T8_*.csv` with `*.meta.json` (dataset digest, registry row, denominator entry, n rows, n clusters,
weighting mode, pre-registration hash, arm), `scorecard.csv`, `figures/*.png|svg|csv`, `run_manifest.json` (wall clock).

## Sensitivity arms
S1 weighting (raw / cluster / one-per-cluster × 5 seeds) · S2 2017 included · S3 test-key rows excluded · S4 detection floor 2 / 6 ·
S5 report age ≤ 365 d · S6 time axis = target-SDK or min-SDK band · S7 batch leave-one-out, mh100k only, no mh100k ·
S8 type from v1.1 / AVClass class token · S9 band widths tight / loose and an explicitly wrong unmatched reference arm ·
S10 casefolded permission identity · S11 signer clusters as the unit.

Outputs never contain certificate common names: only thumbprint hashes and cluster sizes.
