-- ObsidianDroid research database — secondary indexes (DDL draft, v2.2.0)

USE obsidiandroid_research;

-- runs
CREATE INDEX idx_runs_profile_id ON runs (profile_id);
CREATE INDEX idx_runs_dataset_hash ON runs (dataset_hash);
CREATE INDEX idx_runs_split_hash ON runs (split_hash);
CREATE INDEX idx_runs_pipeline_status ON runs (pipeline_status);
CREATE INDEX idx_runs_source_git_tag ON runs (source_git_tag);

-- samples (lazy registry lookups)
CREATE INDEX idx_samples_last_seen_run_id ON samples (last_seen_run_id);

-- sample_label_facts
CREATE INDEX idx_sample_label_facts_profile_id ON sample_label_facts (profile_id);
CREATE INDEX idx_sample_label_facts_supervised_label ON sample_label_facts (supervised_label);
CREATE INDEX idx_sample_label_facts_family_id ON sample_label_facts (family_id);

-- profile_membership
CREATE INDEX idx_profile_membership_profile_id ON profile_membership (profile_id);
CREATE INDEX idx_profile_membership_curation_state ON profile_membership (curation_state);
CREATE INDEX idx_profile_membership_membership_stage ON profile_membership (membership_stage);

-- permission_vocabulary
CREATE INDEX idx_permission_vocabulary_canonical ON permission_vocabulary (canonical_permission);

-- sample_permission_facts
CREATE INDEX idx_sample_permission_facts_permission_name ON sample_permission_facts (permission_name);
CREATE INDEX idx_sample_permission_facts_present ON sample_permission_facts (permission_present);

-- permission_pattern_facts
CREATE INDEX idx_permission_pattern_facts_focus_key ON permission_pattern_facts (focus_key);
CREATE INDEX idx_permission_pattern_facts_pattern_level ON permission_pattern_facts (pattern_level);

-- model_metrics
CREATE INDEX idx_model_metrics_primary_metric ON model_metrics (primary_metric_name, primary_metric_value);

-- prediction_facts
CREATE INDEX idx_prediction_facts_prediction_error ON prediction_facts (prediction_error);

-- quality_flags
CREATE INDEX idx_quality_flags_run_scope ON quality_flags (run_id, flag_scope);
CREATE INDEX idx_quality_flags_flag_code ON quality_flags (flag_code);
CREATE INDEX idx_quality_flags_sample_id ON quality_flags (sample_id);

-- split_assignments
CREATE INDEX idx_split_assignments_split_role ON split_assignments (split_role);
CREATE INDEX idx_split_assignments_split_hash ON split_assignments (split_hash);

-- release_manifests
CREATE INDEX idx_release_manifests_run_id ON release_manifests (run_id);
CREATE INDEX idx_release_manifests_git_tag ON release_manifests (git_tag);
