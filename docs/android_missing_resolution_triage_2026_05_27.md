# Android Missing-Resolution Triage

This view turns the unresolved Android/APK authority backlog into a live
operator surface.

## Why It Exists

The remaining `missing_resolved_family` rows are no longer a family-token
discovery problem. They are mostly a package/provenance backlog with a tiny
VT-tail residue.

The live triage view:

- keeps blank-package backlog rows visible
- groups repeated package clusters together
- isolates the few rows with VT tails
- prevents low-context backlog rows from being mistaken for family-authority debt

## Live View

- `v_android_missing_resolution_triage`

Current lane counts:

- `blank_package_review`: `22`
- `package_cluster_review`: `22`
- `singleton_package_review`: `13`
- `vt_tail_review`: `2`

## Triage Lanes

- `blank_package_review`
- `package_cluster_review`
- `singleton_package_review`
- `vt_tail_review`

## Recommended Actions

- `inspect_unknown_sparse`
- `inspect_repeated_package_cluster`
- `inspect_singleton_package`
- `review_vt_tail`
- `policy_hold_packer`
- `policy_hold_generic`

## Current Shape

The unresolved lane is still concentrated in:

- the `raw_hash_reservoir_20260520` backlog
- blank-package rows
- repeated package clusters such as `com.ubnt.easyunifi`, `com.frontrow.vlog`, and `net.telewebion`

The VT-tail residue remains tiny and should stay policy-held unless a new
external provenance signal appears.
