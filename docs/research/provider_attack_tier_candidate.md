# Provider-reported ATT&CK tier candidate

The active v3 YAML remains unchanged. The separate
`config/taxonomy/mobile_attack_permission_mapping.v4-candidate.yaml` proposes a
lower evidence tier for the nine CAPABILITY_RELATED rules. The twelve
CONTEXT_REQUIRED rules are byte-equivalent as parsed mappings. Official Mobile
ATT&CK v20.1 source pins, rule identities and behavioral prerequisites stay fixed.

`PROVIDER_REPORTED` describes a source assertion, not an observed manifest element
or grant role. It requires the exact provider field path, event, payload digest,
source binding and interpretation rule. Its results explicitly retain
`source_role_complete=false`, `permission_role_observable=false`, API uncertainty,
missing behavioral evidence and `technique_observed=false`.

The candidate emits `PROVIDER_REPORTED_CAPABILITY_HYPOTHESIS` with
`evidence_tier=PROVIDER_REPORTED_LOWER`. This is an audit-only proposal for an owner
decision. It is not a training feature, a verified requested permission, measured
adversary behavior or a production policy change. A source-bound provider assertion
cannot substitute for governed exact identity or override reviewed holds.

`scripts/research/audit_provider_attack_tier.py` compares observation-level v3 and
candidate assessments on explicitly SHA-256-pinned Parquet/PI inputs. It never
queries a database, uses target SDK as device API, normalizes tokens or trains a
model. Each rule's sample statuses sum to its denominator; type/year strata use
the same frozen DETECTED_V2 population. Invalid tokens abstain; the output also
identifies assessed profiles containing other invalid tokens for an exclusion
sensitivity. Group labels are reporting dimensions only.

Run from an environment providing PyYAML and pyarrow, with this branch's `src`
on PYTHONPATH, supplying `--parquet`, `--parquet-sha256`, `--fixture`,
`--fixture-sha256` and a new `--output` directory. Private source data and
sample-level outputs stay outside Git. The numerical audit packet and draft PR
are evidence for review; neither authorizes adoption or merging.
