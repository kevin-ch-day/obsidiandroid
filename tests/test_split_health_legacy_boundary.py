"""Health must recognize enforced legacy denial without granting V2 authority."""
from unittest.mock import MagicMock
import pytest
from mysql.connector import Error
from obsidiandroid.database import db_engine


@pytest.mark.parametrize('gate,denials,visible,expected', [
    ([("BLOCK",)], [1142, 1143], False, 'LEGACY_ACCESS_PROTECTED'),
    ([("BLOCK",)], [None], True, 'UNSAFE_LEGACY_ACCESS'),
    ([("BLOCK",)], [1142, None], False, 'UNSAFE_LEGACY_ACCESS'),
    ([("BLOCK",)], [1146], False, 'UNVERIFIED'),
    ([("BLOCK",)], [2006], False, 'UNVERIFIED'),
    ([], [], False, 'UNVERIFIED'),
    ([("UNKNOWN",)], [], False, 'UNVERIFIED'),
    ([("BLOCK",), ("BLOCK",)], [], False, 'UNVERIFIED'),
    ([("ALLOW",)], [], True, 'LEGACY_READABLE'),
    ([("ALLOW",)], [], False, 'UNVERIFIED'),
])
def test_effective_access_boundary(gate, denials, visible, expected):
    conn = MagicMock(); cur = conn.cursor.return_value
    responses = iter(denials)
    def execute(sql):
        assert sql.startswith('SELECT ')
        if 'LIMIT 0' in sql:
            errno = next(responses)
            if errno: raise Error('fixture', errno=errno)
    cur.execute.side_effect = execute
    cur.fetchall.return_value = gate
    assert db_engine._permission_access_health(conn, legacy_visible=visible) == expected
    cur.close.assert_called_once()


@pytest.mark.parametrize('errno,visible,expected', [
    (1146, True, 'LEGACY_READABLE'), (1146, False, 'UNVERIFIED'),
    (1142, True, 'UNVERIFIED'), (2006, True, 'UNVERIFIED'),
])
def test_missing_gate_is_not_proof_of_protected_access(errno, visible, expected):
    conn = MagicMock();conn.cursor.return_value.execute.side_effect = Error('fixture', errno=errno)
    assert db_engine._permission_access_health(conn, legacy_visible=visible) == expected


@pytest.mark.parametrize('status,exit_code', [('LEGACY_ACCESS_PROTECTED',0), ('LEGACY_READABLE',0), ('UNSAFE_LEGACY_ACCESS',1), ('UNVERIFIED',1)])
def test_cli_classifies_access_separately_from_visibility(monkeypatch,status,exit_code):
    monkeypatch.setattr(db_engine, 'check_split_database_health', lambda: {
        'primary_ok': True, 'permission_intel_ok': True,
        'permission_obs_sample_in_pi': False, 'permission_access_status': status,
        'permission_v2_consumer_status': 'NOT_CHECKED'})
    assert db_engine.split_database_health_cli() == exit_code
