-- Read-only authority view proposal for Erebus / ObsidianDroid alignment.
--
-- Purpose:
--   - expose family/type authority explicitly for Android APK samples
--   - separate raw catalog evidence from resolved/authority family semantics
--   - classify authority gaps and raw-vs-authority status in one stable projection
--
-- This view is intentionally non-destructive.

SET NAMES utf8mb4;

DROP VIEW IF EXISTS v_android_sample_family_type_authority;
CREATE VIEW v_android_sample_family_type_authority AS
SELECT
    msc.sample_id,
    msc.sha256,
    msc.platform,
    msc.android_package_name,
    msc.vt_first_submission_at_utc,

    fam_norm.family_raw AS family_raw,
    fam_norm.family_lc AS family_lc,
    fam_res.resolved_family_lc,

    msc.classification_primary AS raw_classification_primary,
    msc.classification_subtype AS raw_classification_subtype,

    fam.family_id,
    fam.family_name,
    fam.family_slug,

    typ.type_id,
    typ.type_name,
    typ.type_slug,
    typ.parent_type_id,
    parent_typ.type_slug AS parent_type_slug,

    alias.alias_name AS matched_alias_name,
    gt.token_kind AS generic_token_kind,
    gt_vt.token_kind AS vt_tail_token_kind,
    CASE
        WHEN alias.alias_id IS NOT NULL THEN 1
        WHEN COALESCE(LOWER(TRIM(fam_norm.family_lc)), '') <> ''
             AND COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') <> ''
             AND LOWER(TRIM(fam_norm.family_lc)) <> LOWER(TRIM(fam_res.resolved_family_lc))
        THEN 1
        ELSE 0
    END AS resolved_via_alias_flag,

    CASE
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') NOT IN ('', 'unknown')
        THEN 'authority_family_typed'
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_family_unknown_type'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND gt_vt.generic_token_id IS NOT NULL
        THEN 'vt_tail_policy_hold_review'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'pua'
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'pua_or_provenance_review'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'trojan'
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = 'banker'
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'typed_malware_no_family_signal_review'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.android_package_name)), '') <> ''
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'low_signal_singleton_provenance_review'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.android_package_name)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.sample_label_kind)), '') IN ('opaque_string', 'unclassified', 'hash_like')
        THEN 'low_context_provenance_review'
        WHEN COALESCE(LOWER(TRIM(msc.android_package_name)), '') IN (
            'by.lsdsl.hdrezka',
            'com.aptoide.android.aptoidegames',
            'com.frontrow.vlog',
            'com.learn.toppr',
            'com.theporter.android.driverapp',
            'com.ubnt.easyunifi',
            'cris.org.in.prs.ima',
            'fc.admin.fcexpressadmin',
            'net.telewebion'
        )
             AND COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'known_legit_package_identity_review'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = 'unknown'
        THEN 'resolved_unknown'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'missing_resolved_family'
        WHEN gt.generic_token_id IS NOT NULL
        THEN 'generic_label_candidate'
        WHEN LOWER(TRIM(fam_res.resolved_family_lc)) IN (
            'trojan',
            'adware',
            'stalkerware',
            'ransomware',
            'infostealer',
            'banker trojan',
            'fraud financial apps',
            'spyware',
            'hiddenadware',
            'masquerading malware',
            'malware',
            'agent',
            'dropper',
            'stealer',
            'banker',
            'adfraud'
        )
        THEN 'generic_label_candidate'
        ELSE 'resolved_but_no_authority_family'
    END AS authority_bucket,

    CASE
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') NOT IN ('', 'unknown')
        THEN 'authority_family_typed'
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_family_missing_type'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND gt_vt.generic_token_id IS NOT NULL
        THEN 'vt_tail_token_policy_held_not_family'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'pua'
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'pua_without_family_signal'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'trojan'
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = 'banker'
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'coarse_trojan_banker_without_family_signal'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.android_package_name)), '') <> ''
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
        THEN 'blank_family_singleton_no_signal'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.android_package_name)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_family_token)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.vt_suggested_label)), '') = ''
             AND COALESCE(LOWER(TRIM(msc.sample_label_kind)), '') IN ('opaque_string', 'unclassified', 'hash_like')
        THEN 'low_context_blank_package_no_family_signal'
        WHEN COALESCE(LOWER(TRIM(msc.android_package_name)), '') IN (
            'by.lsdsl.hdrezka',
            'com.aptoide.android.aptoidegames',
            'com.frontrow.vlog',
            'com.learn.toppr',
            'com.theporter.android.driverapp',
            'com.ubnt.easyunifi',
            'cris.org.in.prs.ima',
            'fc.admin.fcexpressadmin',
            'net.telewebion'
        )
             AND COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'known_legit_package_identity'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = 'unknown'
        THEN 'resolved_token_unknown'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'missing_resolved_family'
        WHEN gt.generic_token_id IS NOT NULL
        THEN 'resolved_token_policy_held_not_family'
        WHEN LOWER(TRIM(fam_res.resolved_family_lc)) IN (
            'trojan',
            'adware',
            'stalkerware',
            'ransomware',
            'infostealer',
            'banker trojan',
            'fraud financial apps',
            'spyware',
            'hiddenadware',
            'masquerading malware',
            'malware',
            'agent',
            'dropper',
            'stealer',
            'banker',
            'adfraud'
        )
        THEN 'resolved_token_coarse_behavior'
        WHEN fam_res.resolved_family_lc REGEXP '[ /\\\\()]'
        THEN 'resolved_token_malformed_or_composite'
        ELSE 'resolved_token_not_in_authority_taxonomy'
    END AS authority_gap_reason,

    CASE
        WHEN fam.family_id IS NULL
             OR COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_unknown'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') IN ('', 'unknown', 'null', 'n/a', 'malware')
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('', 'unknown', 'null', 'n/a')
        THEN 'raw_missing'
        WHEN COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = LOWER(TRIM(typ.type_slug))
        THEN 'raw_subtype_matches_authority'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') = LOWER(TRIM(typ.type_slug))
        THEN 'raw_primary_matches_authority'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'trojan'
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('', 'unknown', 'null', 'n/a')
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('banker', 'dropper', 'stealer', 'sms-trojan', 'rat', 'spyware', 'adware')
        THEN 'raw_coarse_trojan_matches_parent'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') IN ('dropper', 'banker', 'stealer', 'rat', 'spyware', 'adware', 'sms-trojan')
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = LOWER(TRIM(parent_typ.type_slug))
        THEN 'raw_coarse_behavior_matches_parent'
        WHEN COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('dropper', 'banker', 'stealer', 'rat', 'spyware', 'adware', 'sms-trojan')
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = LOWER(TRIM(parent_typ.type_slug))
        THEN 'raw_coarse_behavior_matches_parent'
        ELSE 'raw_conflicts_with_authority'
    END AS raw_vs_authority_status
FROM malware_sample_catalog AS msc
LEFT JOIN v_android_apk_family_norm AS fam_norm
    ON fam_norm.sample_id = msc.sample_id
LEFT JOIN v_android_apk_family_resolved AS fam_res
    ON fam_res.sample_id = msc.sample_id
LEFT JOIN android_malware_family AS fam
    ON LOWER(TRIM(fam.family_slug)) = LOWER(TRIM(fam_res.resolved_family_lc))
   AND fam.is_active = 1
LEFT JOIN android_malware_type AS typ
    ON typ.type_id = fam.primary_type_id
LEFT JOIN android_malware_type AS parent_typ
    ON parent_typ.type_id = typ.parent_type_id
LEFT JOIN android_malware_family_alias AS alias
    ON alias.family_id = fam.family_id
   AND LOWER(TRIM(alias.alias_name)) = LOWER(TRIM(fam_norm.family_lc))
   AND alias.is_active = 1
LEFT JOIN vendor_label_generic_token_fact AS gt
    ON gt.normalized_token COLLATE utf8mb4_unicode_ci = fam_res.resolved_family_lc COLLATE utf8mb4_unicode_ci
   AND gt.is_active = 1
LEFT JOIN vendor_label_generic_token_fact AS gt_vt
    ON gt_vt.normalized_token COLLATE utf8mb4_unicode_ci = LOWER(TRIM(COALESCE(msc.vt_family_token, ''))) COLLATE utf8mb4_unicode_ci
   AND gt_vt.is_active = 1
WHERE msc.platform = 'android'
  AND msc.file_extension = 'apk';
