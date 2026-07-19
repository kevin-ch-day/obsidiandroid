-- RETIRED HISTORICAL DRAFT. DO NOT APPLY.
-- ObsidianDroid research database — convenience views (DDL draft, v2.2.0)

USE obsidiandroid_research;

-- Latest run per profile (by finished timestamp, then run_id)
CREATE OR REPLACE VIEW v_latest_run_by_profile AS
SELECT r.*
FROM runs r
INNER JOIN (
  SELECT profile_id, MAX(COALESCE(run_finished_at_utc, run_started_at_utc)) AS max_finished
  FROM runs
  GROUP BY profile_id
) latest
  ON latest.profile_id = r.profile_id
 AND latest.max_finished = COALESCE(r.run_finished_at_utc, r.run_started_at_utc);

-- Run-level headline metrics (primary metric when declared)
CREATE OR REPLACE VIEW v_run_headline_metrics AS
SELECT
  r.run_id,
  r.profile_id,
  r.pipeline_status,
  r.claim_status,
  r.dataset_hash,
  r.split_hash,
  m.model_name,
  m.label_target,
  m.primary_metric_name,
  m.primary_metric_value,
  m.macro_f1,
  m.weighted_f1,
  m.accuracy
FROM runs r
LEFT JOIN model_metrics m
  ON m.run_id = r.run_id;

-- Curation state counts per run
CREATE OR REPLACE VIEW v_run_curation_summary AS
SELECT
  pm.run_id,
  pm.profile_id,
  pm.curation_state,
  COUNT(*) AS sample_count
FROM profile_membership pm
GROUP BY pm.run_id, pm.profile_id, pm.curation_state;

-- Release tag to run linkage (official packaging)
CREATE OR REPLACE VIEW v_release_run_map AS
SELECT
  rm.release_tag,
  rm.profile_id,
  rm.run_id,
  rm.git_commit,
  rm.git_tag,
  rm.code_version,
  r.source_git_commit,
  r.source_git_tag,
  r.pipeline_status,
  r.claim_status
FROM release_manifests rm
INNER JOIN runs r ON r.run_id = rm.run_id;

-- Sparse permission fact roll-up (present permissions only)
CREATE OR REPLACE VIEW v_sample_permissions_present AS
SELECT
  spf.run_id,
  spf.sample_id,
  spf.permission_name,
  spf.canonical_permission,
  spf.permission_authority_bucket,
  spf.permission_risk_tier,
  spf.permission_source
FROM sample_permission_facts spf
WHERE spf.permission_present = 1;
