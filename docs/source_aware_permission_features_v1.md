# Source-aware permission features v1

Contract ID: `obsidiandroid-permission-evidence-features-v1`. This is an explicit opt-in research contract. Existing profiles and the completed 2026-10-07 runs retain their legacy `perm__*` interpretation and artifacts.

The unpublished legacy ML loader, permission-trends loaders, cohort permission
aggregates, and banking-permission report now check the proposed PI-v2 research
gate before reading `android_permission_obs_sample`. Only one explicit `ALLOW` row
permits a legacy observation feature fetch; `BLOCK`, a missing table, an
unreadable table, or ambiguous rows raises instead of silently producing an
empty feature frame. The corresponding disposable Erebus migration defaults
the gate to `BLOCK`. This code is not deployed in the current ObsidianDroid
runtime, and it does not make the existing source-aware v1 path an exact-v2
consumer. Gate deployment, SELECT privilege, and research profile cutover must
precede any production collision recovery.

The v1 builder emits separate `perm_provider__<SHA-256-of-exact-canonical-token>` and `perm_manifest__<SHA-256-of-exact-canonical-token>` columns. It also emits `perm_status__has_provider_report`, `perm_status__has_manifest_parse`, provider/manifest missing masks, unresolved count, governance-conflict count, and a separate `perm_status__alias_review_count`. A zero in a presence column is **not** a verified absence. An accepted canonical identity reached through a PI alias remains `UNRESOLVED_ALIAS` until an independently reviewed alias release is supplied; it increments alias-review and unresolved counts, not the explicit conflict count. Missing or unknown canonical identity remains `UNRESOLVED_IDENTITY`. Neither yields a positive permission feature. A checksum-verified complete static projection with zero manifest declarations carries an explicit `VERIFIED_EMPTY` evidence marker, so `manifest_missing=0` without creating a positive permission feature. Provider zero-token receipt coverage remains unresolved until a separate receipt-level coverage contract exists. Vocabulary is fit only from caller-supplied training sample IDs; callers must freeze that split before constructing v1 features. The resulting vocabulary and column-schema digests are recorded in a future run manifest.

Provider-positive evidence requires matching PI `source='virustotal'`, exact `sample_id`/catalog SHA, projected token bytes, VT event system/engine/analysis time, recovery plan-core/batch identity, and a verified completed production sample receipt bound to the plan action. The read-only adapter in `orchestration/recovery_receipt_evidence.py` checks plan/action/receipt digests, exact receipt filename, private owner/mode, production execution scope, and zero provider/primary-catalog side effects; it reconstructs raw provider tokens from action token evidence. Multiple historical VT event rows for one PI sample/token are reconciled as one observation: a receipt-bound event takes precedence over older nonmatching event rows, which do not create extra unresolved counts. The PI row's permission authority is interpreted separately; only an accepted exact identity yields a positive feature. A governed alias needs both a versioned alias-release digest and an externally reviewed exact `(projected token, canonical token) -> release digest` map; the current PI adapter grants none automatically. Missing receipts, wrong event identity, case conflicts, and disputed authority yield unresolved status. Independently parsed manifest declarations use `orchestration/static_projection_evidence.py`, which verifies the separately reviewed projection digest, exact APK baseline file hash, and direct-manifest occurrence digests. PI `source='apk_manifest'` alone is not proof.

The pipeline accepts v1 only when `feature_flags.permission_feature_contract_version` names this contract and `permission_training_sample_ids` is supplied. A caller-supplied `source_aware_permission_evidence` DataFrame is rejected, regardless of its `source_verified` flags. Provider evidence must go through the retained plan and private sample-receipt loader using `permission_recovery_plan_path`, `permission_recovery_receipt_directory`, and `permission_recovery_plan_digest`; exact pilots additionally require the manifest and selection digests. Manifest evidence must go through `permission_static_projection_paths`, `permission_static_baseline_paths_by_sha`, and separately reviewed `permission_static_projection_digests_by_sha`. The modalities can be combined without merging their columns. No existing YAML profile enables v1. The current general pipeline computes its split after feature construction, so a future controlled v1 experiment must provide a frozen training membership before this stage or move vocabulary fitting after the split. Full model retraining is outside this implementation.

The local continuation closes the direct-frame and cached-frame bypasses at
their public pipeline entry points. The adapter records a source-file snapshot
and process-bound feature seal covering contract, training membership, sample
SHA membership, policy, content, and source identity. Fusion rechecks the seal,
source bytes, receipt-directory membership, and current PI research gate for
both source-aware and cached legacy permission frames. A serialized or modified cached frame cannot be
reused across processes or after a source/policy/gate change. This is an
in-process integrity guard, **not** a signed export or independent authority
for arbitrary operator-supplied plan digests. A reviewed source/export registry,
V2 exact-snapshot reader, approved policy identity, and coordinated gate
deployment remain release prerequisites. Do not enable a research profile yet.

Do not treat AV and provider permission signals as independent corroboration merely because they occupy different columns. Family/type labels are not read by the v1 feature builder. Use source/campaign-disjoint sensitivity analysis and record any shared VT upstream dependence in a later experiment's evaluation contract.

Status counts use distinct `(sample_id, observation_origin, projected_token)` identities: multiple raw spellings of one projected PI fact count once, while provider and manifest facts remain separate. Byte-distinct case variants remain distinct. If one projected fact has both accepted and conflicting evidence, the conflict suppresses its positive feature until reviewed. Rows without a projected token remain distinct unresolved occurrences. Raw spellings stay in the evidence input and receipts.
