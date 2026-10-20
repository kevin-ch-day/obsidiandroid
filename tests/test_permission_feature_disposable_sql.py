"""Actual maintained legacy feature SQL against retained-report disposable rows."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.database import db_engine, permission_contracts
from obsidiandroid.database.permission_current_interpretation import interpretation_joins
from obsidiandroid.orchestration import permission_features

OVERLAP_TOKENS = (
    'com.android.browser.permission.READ_HISTORY_BOOKMARKS',
    'com.android.browser.permission.WRITE_HISTORY_BOOKMARKS',
    'com.android.email.permission.ACCESS_PROVIDER',
    'com.android.launcher.permission.READ_SETTINGS',
    'com.android.launcher.permission.WRITE_SETTINGS',
    'com.android.launcher2.permission.READ_SETTINGS',
    'com.android.launcher2.permission.WRITE_SETTINGS',
    'com.android.launcher3.permission.READ_SETTINGS',
    'com.android.launcher3.permission.WRITE_SETTINGS',
)


@pytest.mark.integration
@pytest.mark.live_database
def test_retained_feature_query_cardinality_and_dictionary_overlap(monkeypatch):
    path = os.environ.get('EREBUS_CANARY_MARIADB_REPLAY_CONFIG')
    if not path:
        pytest.skip('explicit disposable replay configuration required')
    from erebus.canary.fixture_replay import config_from_file
    import mysql.connector

    cfg = config_from_file(Path(path))
    assert cfg.schema == cfg.user and cfg.schema.startswith('erebus_replay_')
    conn = mysql.connector.connect(host=cfg.host, port=cfg.port, user=cfg.user,
                                   password=cfg.password, database=cfg.schema, connection_timeout=5)

    def execute(sql, params=()):
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            cursor.close()

    try:
        source = execute('SELECT COUNT(*) n, COUNT(DISTINCT obs_id) distinct_n FROM android_permission_obs_sample WHERE sample_id IN (123332,123341)')[0]
        assert source == {'n': 59, 'distinct_n': 59}
        cur = conn.cursor()
        try:
            cur.execute('ALTER TABLE android_permission_dict_oem ADD COLUMN protection_level VARCHAR(255) NULL')
            cur.execute('ALTER TABLE android_permission_v1_current_permission ADD COLUMN identity_status VARCHAR(32) NOT NULL DEFAULT \'ACCEPTED\'')
            cur.execute('ALTER TABLE android_permission_token_anomaly_fact ADD COLUMN token_value_norm VARCHAR(255) GENERATED ALWAYS AS (LOWER(TRIM(token_value))) STORED')
            cur.execute('CREATE TABLE android_permission_v1_obsidiandroid_permission (canonical_permission VARCHAR(512) NOT NULL, catalog_release_id VARCHAR(96) NOT NULL, catalog_digest CHAR(64) NOT NULL, compatibility_protection_expression TEXT NULL)')
            cur.execute('CREATE TABLE android_permission_token_alias (alias_id BIGINT PRIMARY KEY AUTO_INCREMENT, raw_token VARCHAR(512) NOT NULL, canonical_token VARCHAR(512) NOT NULL)')
            # The authority lookup fixture inherits the replay catalog default;
            # current PI dictionary tables use utf8mb4_unicode_ci with observations.
            for table in ('android_permission_v1_current_permission',
                          'android_permission_v1_obsidiandroid_permission',
                          'android_permission_token_alias', 'android_permission_authority_fact',
                          'android_permission_dict_aosp', 'android_permission_dict_oem',
                          'android_permission_non_permission_fact',
                          'android_permission_token_anomaly_fact'):
                cur.execute(f'ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            cur.execute("INSERT INTO android_permission_meta_oem_vendor VALUES (7,'test-oem','Test OEM')")
            cur.execute("INSERT INTO malware_sample_catalog(sample_id,sha256,sample_label,platform) VALUES(900999,%s,'overlap-fixture','android')", ('9'*64,))
            for permission_id, token in enumerate(OVERLAP_TOKENS, 1000):
                cur.execute('INSERT INTO android_permission_dict_aosp(constant_value,source_family_key,lifecycle_status) VALUES (%s,%s,%s)', (token,'overlap-fixture','current'))
                cur.execute('INSERT INTO android_permission_dict_oem(permission_string,vendor_id) VALUES (%s,7)', (token,))
                cur.execute("INSERT INTO android_permission_v1_current_permission(permission_id,canonical_permission,authority_class,lifecycle,feature_dependency,catalog_release_id,catalog_digest) VALUES(%s,%s,'AOSP_PUBLIC','current',NULL,'fixture-v1',%s)", (permission_id,token,'d'*64))
                cur.execute("INSERT INTO android_permission_v1_obsidiandroid_permission(canonical_permission,catalog_release_id,catalog_digest,compatibility_protection_expression) VALUES(%s,'fixture-v1',%s,'normal')", (token,'d'*64))
                cur.execute("INSERT INTO android_permission_obs_sample(sample_id,sha256,permission_string,classification,source) VALUES(900999,%s,%s,'AOSP','other')", ('9'*64,token))
            conn.commit()
        finally:
            cur.close()

        def frame_query(sql, params=(), fetch=False, as_dataframe=False):
            rows = execute(sql, params)
            return pd.DataFrame(rows) if as_dataframe else rows

        monkeypatch.setattr(permission_features, 'assert_legacy_observation_read_allowed', lambda: None)
        monkeypatch.setattr(db_engine, 'execute_permission_query', frame_query)
        monkeypatch.setattr(db_engine, 'get_table_columns', lambda table: [row['Field'] for row in execute(f'SHOW COLUMNS FROM `{table}`')])
        permission_contracts.reset_permission_obs_norm_cache()
        ids = [123332, 123341, 900999]
        where = 'WHERE ops.sample_id IN (123332,123341,900999)'
        canonical = ' LEFT JOIN android_permission_v1_current_permission pi ON pi.canonical_permission=ops.permission_string AND BINARY pi.canonical_permission=BINARY ops.permission_string'
        aosp = ' LEFT JOIN android_permission_dict_aosp a ON a.constant_value=ops.permission_string AND BINARY a.constant_value=BINARY ops.permission_string'
        oem = ' LEFT JOIN android_permission_dict_oem o ON o.permission_string=ops.permission_string AND BINARY o.permission_string=BINARY ops.permission_string AND o.vendor_id IS NOT NULL'
        full = interpretation_joins(key_expr='ops.permission_string_norm', raw_expr='ops.permission_string') + oem
        stage_joins = {'source': '', 'canonical': canonical,
                       'aosp': canonical+aosp, 'oem': canonical+aosp+oem,
                       'authority_protection': full}
        stages = {}
        for stage, joins in stage_joins.items():
            stages[stage] = execute('SELECT COUNT(*) n, COUNT(DISTINCT ops.obs_id) distinct_n FROM android_permission_obs_sample ops '
                                    + joins + ' ' + where)[0]
            assert stages[stage] == {'n': 68, 'distinct_n': 68}
        joined = permission_features._fetch_permission_rows(ids)
        assert len(joined) == 68
        assert len(joined[['sample_id','permission_string_raw']].drop_duplicates()) == 68
        overlap_joined = joined.loc[joined.sample_id.eq(900999)]
        assert set(overlap_joined.permission_source) == {'AOSP'}
        assert set(overlap_joined.current_evidence_state) == {'ACCEPTED_CANONICAL'}
        sample_frame = pd.DataFrame({'sample_id': ids})
        matrix = permission_features.build_permission_feature_frame(sample_frame, min_permission_support=1)
        assert list(matrix.sample_id) == ids and len(matrix) == 3
        assert matrix.sample_id.is_unique
        assert matrix.loc[matrix.sample_id.eq(123341), 'perm__total_count'].iloc[0] == 56
        assert matrix.loc[matrix.sample_id.eq(123332), 'perm__total_count'].iloc[0] == 3
        assert matrix.loc[matrix.sample_id.eq(900999), 'perm__total_count'].iloc[0] == 9
        overlap = execute('SELECT ops.permission_string, COUNT(*) n FROM android_permission_obs_sample ops LEFT JOIN android_permission_dict_aosp a ON a.constant_value=ops.permission_string AND BINARY a.constant_value=BINARY ops.permission_string LEFT JOIN android_permission_dict_oem o ON o.permission_string=ops.permission_string AND BINARY o.permission_string=BINARY ops.permission_string AND o.vendor_id IS NOT NULL WHERE ops.sample_id=900999 AND a.constant_value IS NOT NULL AND o.permission_string IS NOT NULL GROUP BY ops.permission_string')
        assert {r['permission_string'] for r in overlap} == set(OVERLAP_TOKENS)
        assert all(r['n'] == 1 for r in overlap)
        print(f'FEATURE_QUERY stages={stages} retained_base=59 overlap_fixture=9 joined=68 overlap=9 sample_rows=3 permission_counts=3,56,9')
    finally:
        permission_contracts.reset_permission_obs_norm_cache()
        conn.rollback()
        conn.close()
