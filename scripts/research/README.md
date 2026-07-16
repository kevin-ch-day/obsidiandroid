# Research and publication scripts

These commands create or validate evidence and publication artifacts from
existing run outputs. They are not part of normal pipeline execution and do
not replace a run's manifest, metrics, or frozen experimental contract.

Run them from the repository root after selecting an explicit run or run ID.

| Script | Purpose |
| --- | --- |
| `check_evidence_bundle.py` | Validate the required evidence package for one or more run IDs. |
| `export_publication_tables.py` | Export publication-ready CSV and LaTeX tables from a selected run. |
| `generate_claim_artifact_map.py` | Generate a claim-to-artifact scaffold from run manifests. |
| `generate_structural_diagnostics.py` | Generate publication-facing structural diagnostics from existing artifacts. |
| `mark_legacy_publication_exports.py` | Mark old partial publication exports as non-authoritative. |
| `compare_av_feature_scopes.py` | Validate a paired `all_observed` versus `lifecycle_included` AV experiment before interpreting Macro-F1 deltas. |

Use the run-scoped artifacts under `output/runs/<run_id>/` as the source of
truth. These scripts may write derived exports, but they do not establish or
alter experimental results.

## Paired AV binary-feature scope comparison

`compare_av_feature_scopes.py` is intentionally a post-run validator, not a
tuning command.  Run a baseline with `av_binary_feature_engine_scope:
all_observed`, then a candidate with `lifecycle_included`, using the same
frozen cohort, split ledger, label field, and model configuration.  Compare
only completed run roots:

```bash
python scripts/research/compare_av_feature_scopes.py \
  --baseline-run-root output/runs/<baseline-run> \
  --candidate-run-root output/runs/<candidate-run> \
  --output-dir output/diagnostics/av_scope_comparison
```

The command exits nonzero and suppresses score interpretation if the cohort,
split, label, model configuration, or leakage-safety contracts do not match.
Its output is an audit of a paired experiment; it does not validate an older
run that predates the AV-scope contract.
