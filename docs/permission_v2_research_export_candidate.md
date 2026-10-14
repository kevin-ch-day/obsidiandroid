# PI V2 exact export and research-run policy candidate

This is an unpublished local contract. No production export approval, research
profile, or model run is enabled by these files. The existing paper artifacts
and previous results are not reclassified.

`obsidiandroid-permission-exact-v2-unresolved-v1` accepts a complete exact
sample/SHA export only when its **actual bytes** match an administrator-owned
approval at `/etc/obsidiandroid/pi-v2-export-approval.json`. The anchor must be
root-owned in root-owned directories and not group/world writable. Research
callers may name the export file, but may not provide the approval path, an
unchecked expected digest, a `source_verified` flag, or an alternate policy.
The independently reviewed anchor binds the export SHA-256, frozen cohort
manifest, published Erebus source commit, source-authority digest, projection
policy, interpretation release, feature contract and completeness status.
This contract additionally requires the exact frozen 1,813-SHA manifest digest
`7eea4260d985107f5c9e8a0f692adadda79922cebd6f59761943939e469a7238`
and exactly 1,813 export records. An anchor for a partial or different cohort
cannot mark it complete under this contract; a future cohort needs its own
reviewed version.
There is no installed anchor today. Test fixtures replace the private anchor
reader only on disposable inputs; those fixtures are not approvals.

The loader hashes and parses the same in-memory byte buffer, rejects duplicate
JSON keys, incompatible versions, missing provenance, duplicate members and
sample/SHA mismatches. It preserves exact raw and projected token strings;
many-to-one raw members count as one projected occurrence feature. It emits
`perm_provider_unresolved__<sha256(exact projected token)>` and status counts,
never canonical permission, protection-level or malware-class positives.
Vocabulary is fitted only from the frozen training IDs. The feature frame is
process-sealed and rechecks both export and approval bytes at fusion and direct
ablation. A serialized or modified cached frame cannot supply authority. The
legacy observation-table gate is not used to grant this V2 contract; a V2
export failure cannot fall back to legacy reads.

The PI-required policy accepts complete, approved V2 unresolved occurrence
features **only as that exact reviewed research choice**. A required PI input
that is unavailable, incomplete, contradictory, blocked or unsupported stops
before training. `development_compatibility` can continue but records
`DEVELOPMENT_ONLY_NOT_ACCEPTED_RESEARCH`; intentionally disabled PI records a
different `PI_DISABLED_DECLARED` state. A successful observation-table query
with no rows is `NO_OBSERVATIONS`, not an independently verified empty
manifest. Only an explicit verified-empty static projection can claim
`VERIFIED_EMPTY`. The chosen policy and evidence state enter run manifest
context and the model-fitting boundary checks them again.

Before production cutover, reviewers must approve the exact export producer,
the byte-bound approval anchor, the research profile and feature semantics,
the approved sample/source snapshots, and the split-before-vocabulary rule.
Legacy research accounts with direct `SELECT` on PI observation tables must
lose that read path or use an independently reviewed compatibility mechanism.
Application checks alone cannot stop direct SQL under an existing schema-wide
grant. This candidate does not change any account or grant.
