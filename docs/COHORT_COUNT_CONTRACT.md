# Cohort count contract

Canonical family/type identity metrics for operator, observability, claim, and
diagnostic surfaces. Ambiguous phrases such as “visible families” must not be
used when the treatment of `unknown` is unclear.

Contract module: `obsidiandroid.reporting.cohort_count_contract`  
Version: `1.0.0`

## Metrics

| Metric | Includes `unknown`? | Typical all-current value | Source stage |
|--------|---------------------|---------------------------|--------------|
| `governed_known_family_count` | No | 206 | Prepared cohort / analysis snapshot; blank + `unknown` excluded |
| `observed_family_label_count_including_unknown` | Yes | 207 | Same surface; blank/null normalized to `unknown` |
| `unknown_family_sample_count` | n/a (samples) | 226 | Rows whose family label is blank/null/`unknown` |
| `governed_known_type_count` | No | 14 | Prepared cohort; blank + `unknown` excluded |
| `observed_type_slug_count_including_unknown` | Yes | 15 | Blank/null normalized to `unknown` |
| `unknown_type_sample_count` | n/a (samples) | 275 | Rows whose `type_slug` is blank/null/`unknown` |
| `training_target_classes` | No | 169 | After authority + support filtering; train split labels |
| `held_out_evaluated_classes` | No | 132 | Held-out / test split known family labels |
| `train_only_classes` | No | 37 | Train − held-out |

Illustrative values above came from one completed all-current diagnostic
prepared cohort (`output/runs/allcurrent_diagnostic`, run id
`20260721T231415Z__e0c43b` at documentation time; prior instance
`20260721T142432Z__07f657` is retained under
`output/runs/_archived/completed/allcurrent_diagnostic/`). The contract itself is
run-independent: always recompute from the active analysis snapshot / prepared
cohort artifacts and do not hard-code run ids or counts into callers.

## Operator copy

Prefer:

```text
Known governed families: 206
Observed family labels: 207 including `unknown`
Known governed types: 14
Observed type_slug values: 15 including `unknown`
Training target classes: 169
Held-out evaluated classes: 132
Train-only classes: 37
```

## Authority / filtering stages

1. **Prepared cohort / analysis snapshot** — post SQL + Python preparation; before train/test split.
2. **Taxonomy target surface** — `unique_classes` on `family_id` / `type_slug` excludes blank/`unknown` (aligns with known governed counts).
3. **Training targets** — after label-authority alignment and support gates; excludes `unknown`.
4. **Held-out evaluation** — known labels present in the test/holdout split.

## Offline use

```python
from obsidiandroid.reporting.cohort_count_contract import (
    resolve_cohort_counts_from_snapshot,
    format_family_type_count_lines,
)

counts = resolve_cohort_counts_from_snapshot(snapshot_csv)
print("\n".join(format_family_type_count_lines(counts)))
```

No database access is required for offline composers.
