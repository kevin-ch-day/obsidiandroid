# Advanced Pattern Metrics

Date: `2026-05-27`

This pass extends the earlier concentration audit with:

- Theil index
- Pareto mass share
- Jensen-Shannon divergence
- Mutual information

The goal is to separate:

1. diffuse residual token debt that should not drive broad taxonomy changes
2. concentrated package/provenance debt that should be worked as clustered review
3. remaining false-positive review structure that is still operationally meaningful

The rerunnable SQL pack is:

- [database/sql/android_pattern_advanced_metrics.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/android_pattern_advanced_metrics.sql)

Interpretation guidance:

- Higher entropy / lower HHI:
  - more diffuse problem
  - less suitable for broad one-shot cleanup
- Higher Theil:
  - more inequality / concentration in a few buckets
- Higher top-1 / top-3 / top-5 mass:
  - more of the problem is sitting in a few dominant clusters
- Higher Jensen-Shannon divergence:
  - the missing-resolution package distribution really differs from the base Android package distribution
- Higher mutual information:
  - the two variables are structurally coupled, not just coincidentally associated

External context:

- SciPy defines Jensen-Shannon distance as the square root of Jensen-Shannon divergence and emphasizes its bounded, metric behavior:
  - https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html
- scikit-learn documents mutual information as a measure of dependence between variables / clusterings:
  - https://scikit-learn.org/0.18/modules/generated/sklearn.metrics.mutual_info_score.html
  - https://sklearn.org/1.6/modules/generated/sklearn.feature_selection.mutual_info_classif.html
- DOJ uses HHI as a standard concentration measure, which is useful here as a compact way to express “how concentrated is the remaining debt?”
  - https://www.justice.gov/atr/herfindahl-hirschman-index

## Live Results

### 1. Residual unresolved-family token tail is still diffuse

`resolved_but_no_authority_family`

- rows: `116`
- distinct tokens: `66`
- entropy: `5.8144`
- normalized entropy: `0.9619`
- HHI: `0.0214`
- Theil T: `0.2300`
- top-1 share: `0.0690`
- top-3 share: `0.1293`
- top-5 share: `0.1810`

Interpretation:

- this tail is still highly diffuse
- broad new-family creation is mathematically unjustified
- most remaining value is in suppression, review routing, or one-off research, not in a single hidden dominant token

### 2. Missing-resolution package lane is concentrated

`missing_resolved_family_packages`

- rows: `59`
- distinct clusters: `19`
- entropy: `2.9656`
- normalized entropy: `0.6981`
- HHI: `0.2226`
- Theil T: `1.2824`
- top-1 share: `0.3729`
- top-3 share: `0.7119`
- top-5 share: `0.7627`

Interpretation:

- this is a concentrated queue
- the top 3 clusters account for over `71%` of the lane
- this remains a cluster/provenance problem, not a taxonomy-discovery problem

### 3. The missing-resolution package distribution is genuinely different from the Android base

Jensen-Shannon divergence:

- `android_pkg_base_vs_missing_jsd = 0.8811 bits`

Interpretation:

- the missing-resolution package distribution is not just a random slice of the Android corpus
- it is structurally different enough to justify a dedicated queue and policy treatment

### 4. Package blankness is only weakly informative at the whole authority-bucket level

Mutual information:

- `authority_bucket_vs_package_blankness_mi = 0.0178 bits`

Interpretation:

- package blankness matters a lot for the `missing_resolved_family` lane, but it does not strongly separate the full authority-bucket universe by itself
- this is a useful warning against overgeneralizing the blank-package pattern beyond the specific backlog slice

### 5. The effective false-positive review queue still has strong structural shape

Mutual information:

- `effective_fp_platform_vs_regex_bucket_mi = 0.6564 bits`

Effective FP label concentration:

- rows: `59`
- distinct labels: `36`
- entropy: `4.3970`
- normalized entropy: `0.8505`
- HHI: `0.0991`
- Theil T: `0.7729`
- top-1 share: `0.2712`
- top-3 share: `0.4237`
- top-5 share: `0.4746`

Interpretation:

- the effective FP queue is not random residue
- platform and label-shape are still meaningfully coupled
- there is still enough concentration to mine more exact-label or shape-based QA improvements

### 6. Package-prefix lift confirms the dominant low-context clusters

Highest support-weighted lift:

- `com.ubnt`: `166.39`
- `com.frontrow`: `94.52`
- `net.telewebion`: `64.52`
- `<blank>`: `37.17`

Interpretation:

- the previously identified package clusters remain the dominant structural anomaly
- `<blank>` is still a real cluster, but it is much less extreme than the repeated legit-looking app clusters

## Operational Conclusion

The advanced metrics sharpen the repair strategy:

1. `resolved_but_no_authority_family` is too diffuse for another broad family-authority push.
2. `missing_resolved_family` remains concentrated enough for targeted package/provenance handling.
3. the effective false-positive queue still has structured residue and is worth continued QA cleanup.
4. the biggest hidden pattern is no longer “missing family names”; it is “concentrated provenance/noise clusters versus diffuse residual token debt.”
