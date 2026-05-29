# Android Pattern Information Metrics

This note turns the remaining Android repair surfaces into measurable pattern
problems instead of ad hoc token cleanup.

## Main Quantitative Findings

### Residual unresolved-family token tail is diffuse

- total rows: `116`
- distinct tokens: `66`
- entropy: `5.8144` bits
- normalized entropy: `0.9619`
- HHI: `0.0214`

Interpretation:

- the residual token tail is highly diffuse
- there is no single dominant missing-family token left
- this is no longer a good surface for broad family creation

### Missing-resolution package lane is concentrated

- total rows: `59`
- distinct package clusters: `19`
- entropy: `2.9656` bits
- normalized entropy: `0.6981`
- HHI: `0.2226`

Interpretation:

- `missing_resolved_family` is structurally concentrated
- it is mainly a package-cluster / low-context backlog problem
- this is where package-level review and suppression have the most leverage

### VT tail purity explains current policy decisions

- `genericfca` is high-entropy / multi-family noise
- `jiagu` splits between blank and `gigabud`, consistent with packer/tooling
- `boogr` is extremely distributed across many governed families
- `spybanker` and `fklz` look “pure” only because they are self-referential or singleton, not because they are trustworthy family tokens

## Why This Matters

The math says:

1. stop looking for one big missing family token in `resolved_but_no_authority_family`
2. keep focusing risk reduction on concentrated package clusters in `missing_resolved_family`
3. keep using policy holds for noisy VT tails rather than promoting them into family authority
4. treat the false-positive review surface as a structural regex problem, especially for legitimate installer/admin-tool churn

## SQL

Use:

- [android_pattern_information_metrics.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/android_pattern_information_metrics.sql)
