-- Read-only statements executed by generate_snapshot.py (mariadb -u claude_ro android_permission_intel)

-- lut_rows
SELECT attack_technique_id, attack_name, tactic, platform, source_url, notes, record_created_at_utc, record_updated_at_utc FROM android_attack_technique_lut ORDER BY attack_technique_id;

-- mapping_rows
SELECT m.mapping_id, m.permission_string_norm, HEX(m.permission_string_norm) AS permission_hex, LENGTH(m.permission_string_norm) AS byte_length, CHAR_LENGTH(m.permission_string_norm) AS char_length, COLLATION(m.permission_string_norm) AS collation_name, m.attack_technique_id, m.mapping_strength, m.mapping_source, m.active_flag, m.evidence_note, m.record_created_at_utc, m.record_updated_at_utc, a.lifecycle_status AS dict_aosp_lifecycle_status, a.protection_level AS dict_aosp_protection_level, i.canonical_permission AS api_identity_canonical, i.authority_class AS api_identity_authority_class, i.identity_status AS api_identity_status FROM android_permission_attack_mapping m LEFT JOIN android_permission_dict_aosp a ON a.constant_value_norm = m.permission_string_norm LEFT JOIN api_permission_identity i ON LOWER(i.canonical_permission) = m.permission_string_norm ORDER BY m.mapping_id;

-- schema_migration_0058
SELECT id, version, note, applied_at_utc FROM schema_migrations WHERE version='0058';

-- view_summary_rows
SELECT attack_technique_id, attack_name, tactic, sample_count, mapped_permission_observations FROM v_android_permission_attack_surface_summary ORDER BY attack_technique_id;

SHOW CREATE VIEW v_android_permission_attack_surface_current\G

SHOW CREATE VIEW v_android_permission_attack_surface_summary\G
