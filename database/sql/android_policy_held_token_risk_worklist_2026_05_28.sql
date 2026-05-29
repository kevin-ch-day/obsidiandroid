-- Read-only worklist for policy-held Android family tokens.
--
-- These rows are intentionally excluded from true unresolved-family repair:
-- the token resolves to a generic/coarse/behavior/placeholder signal rather
-- than a governed canonical malware family. This worklist keeps that debt
-- visible without pushing unsafe family-authority promotion.

SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS tmp_android_policy_held_token_risk;

CREATE TEMPORARY TABLE tmp_android_policy_held_token_risk AS
WITH
pi AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
held AS (
    SELECT
        a.sample_id,
        a.resolved_family_lc AS policy_held_token,
        gt.token_kind,
        a.raw_classification_primary,
        a.raw_classification_subtype,
        a.android_package_name,
        COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
        COALESCE(vs.vt_malicious_count, 0) AS vt_malicious_count
    FROM v_android_sample_family_type_authority AS a
    JOIN vendor_label_generic_token_fact AS gt
      ON gt.normalized_token COLLATE utf8mb4_unicode_ci = a.resolved_family_lc COLLATE utf8mb4_unicode_ci
     AND gt.is_active = 1
    JOIN pi
      ON pi.sample_id = a.sample_id
    LEFT JOIN vt_sample_verdict_confidence_current AS vs
      ON vs.sample_id = a.sample_id
    WHERE LOWER(COALESCE(a.platform, '')) = 'android'
      AND a.authority_bucket IN ('resolved_but_no_authority_family', 'generic_label_candidate')
)
SELECT
    h.*,
    CASE
        WHEN h.token_kind IN ('behavior_class_token')
            THEN 'class_label_not_family'
        WHEN h.token_kind IN ('packer_evasion_token', 'heuristic_token')
            THEN 'technical_signal_not_family'
        WHEN h.token_kind IN ('placeholder_token')
            THEN 'placeholder_or_source_artifact'
        WHEN h.token_kind IN ('campaign_actor_token')
            THEN 'campaign_or_actor_not_family'
        ELSE 'generic_family_token_review'
    END AS policy_hold_lane,
    CASE
        WHEN h.token_kind = 'behavior_class_token'
            THEN 'Keep out of family authority. Use raw primary/subtype or type_slug surfaces for coarse behavior claims.'
        WHEN h.token_kind IN ('packer_evasion_token', 'heuristic_token')
            THEN 'Keep out of family authority. This is a technical detection/evasion signal, not a malware family.'
        WHEN h.token_kind = 'placeholder_token'
            THEN 'Keep out of family authority. Review package/source provenance before any canonical mapping.'
        WHEN h.token_kind = 'campaign_actor_token'
            THEN 'Keep out of family authority unless a governed family/campaign model is added.'
        ELSE 'Manual review. Promote only with external family evidence and stable local support.'
    END AS recommended_next_action
FROM held AS h;

SELECT
    policy_hold_lane,
    token_kind,
    COUNT(*) AS row_count,
    COUNT(DISTINCT policy_held_token) AS token_count,
    SUM(CASE WHEN confidence_bucket IN ('high', 'strong') THEN 1 ELSE 0 END) AS high_or_strong_rows
FROM tmp_android_policy_held_token_risk
GROUP BY policy_hold_lane, token_kind
ORDER BY row_count DESC, high_or_strong_rows DESC, token_kind;

SELECT
    policy_held_token,
    token_kind,
    policy_hold_lane,
    COUNT(*) AS row_count,
    SUM(CASE WHEN confidence_bucket IN ('high', 'strong') THEN 1 ELSE 0 END) AS high_or_strong_rows,
    GROUP_CONCAT(DISTINCT COALESCE(NULLIF(raw_classification_primary, ''), '<blank>') ORDER BY raw_classification_primary SEPARATOR ',') AS primary_labels,
    GROUP_CONCAT(DISTINCT COALESCE(NULLIF(raw_classification_subtype, ''), '<blank>') ORDER BY raw_classification_subtype SEPARATOR ',') AS subtype_labels,
    GROUP_CONCAT(DISTINCT android_package_name ORDER BY android_package_name SEPARATOR ',') AS package_examples,
    recommended_next_action
FROM tmp_android_policy_held_token_risk
GROUP BY
    policy_held_token,
    token_kind,
    policy_hold_lane,
    recommended_next_action
ORDER BY row_count DESC, high_or_strong_rows DESC, policy_held_token
LIMIT 100;
