-- Additive triage surface over the suppression-aware effective FP review view.
-- Purpose:
--   * separate real malware-family low-consensus rows from placeholder noise
--   * separate likely installer/software ambiguity from artifact/hash residue
--   * give analysts a more explicit next-action lane without mutating base data

CREATE OR REPLACE VIEW v_vt_false_positive_review_candidates_triage AS
SELECT
  v.*,
  CASE
    WHEN v.vt_malicious_count = 1
      AND EXISTS (
        SELECT 1
        FROM vt_false_positive_suppression_rule s
        WHERE s.active_flag = 1
          AND s.scope_type = 'global'
          AND s.scope_value = 'vt_malicious_count=1'
      )
      THEN 'single_vendor_low_context_review'
    WHEN v.vt_malicious_count <= 2
      AND v.vt_harmless_count >= 20
      AND EXISTS (
        SELECT 1
        FROM vt_false_positive_suppression_rule s
        WHERE s.active_flag = 1
          AND s.scope_type = 'global'
          AND s.scope_value = 'vt_malicious_count<=2 AND vt_harmless_count>=20'
      )
      THEN 'low_consensus_high_harmless_review'
    ELSE 'no_global_policy_match'
  END AS global_policy_bucket,
  CASE
    WHEN v.vt_malicious_count = 1
      AND EXISTS (
        SELECT 1
        FROM vt_false_positive_suppression_rule s
        WHERE s.active_flag = 1
          AND s.scope_type = 'global'
          AND s.scope_value = 'vt_malicious_count=1'
      )
      THEN 0.2500
    WHEN v.vt_malicious_count <= 2
      AND v.vt_harmless_count >= 20
      AND EXISTS (
        SELECT 1
        FROM vt_false_positive_suppression_rule s
        WHERE s.active_flag = 1
          AND s.scope_type = 'global'
          AND s.scope_value = 'vt_malicious_count<=2 AND vt_harmless_count>=20'
      )
      THEN 0.4000
    ELSE 1.0000
  END AS global_policy_weight,
  CASE
    WHEN v.sample_label IN ('UNCLASSIFIED', 'Phishing')
      THEN 'generic_placeholder_review'
    WHEN v.sample_label IN ('Gigabud', 'Banker Trojan')
      THEN 'real_malware_family_or_class_review'
    WHEN v.sample_label IN (
      'WEXTRACT.EXE            .MUI',
      'PandaObfuscator.exe',
      'libWBP122.dll',
      'Uninstall.exe',
      'setup.exe'
    )
      THEN 'legit_software_or_installer_review'
    WHEN v.sample_label REGEXP '^[a-f0-9]{8,}(\\.|$)'
      THEN 'hash_artifact_review'
    WHEN v.sample_label REGEXP '\\.(apk|exe|dll|jar|zip|rar|doc|png|so|virus|file)$'
      THEN 'file_artifact_review'
    ELSE 'other_review'
  END AS review_lane,
  CASE
    WHEN v.sample_label IN ('UNCLASSIFIED', 'Phishing')
      THEN 'reclassify_or_hold_placeholder'
    WHEN v.sample_label IN ('Gigabud', 'Banker Trojan')
      THEN 'retain_for_malware_review'
    WHEN v.sample_label IN (
      'WEXTRACT.EXE            .MUI',
      'PandaObfuscator.exe',
      'libWBP122.dll',
      'Uninstall.exe',
      'setup.exe'
    )
      THEN 'require_file_provenance_before_suppression'
    WHEN v.sample_label REGEXP '^[a-f0-9]{8,}(\\.|$)'
      THEN 'artifact_name_noise_review'
    WHEN v.sample_label REGEXP '\\.(apk|exe|dll|jar|zip|rar|doc|png|so|virus|file)$'
      THEN 'artifact_name_noise_review'
    ELSE 'manual_review'
  END AS recommended_triage_action
FROM v_vt_false_positive_review_candidates_effective v;
