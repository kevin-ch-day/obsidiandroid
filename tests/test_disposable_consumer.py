"""Real SQLite transactions and independent provider processes; no network DB."""
import copy
import json
import sqlite3
import shutil
import time
from types import SimpleNamespace

import pytest

from obsidiandroid.governance.disposable_consumer import (
    ConsumerDenied, DisposableClient, change_authority, provision, recover, _Store,
)


def fixture_view():
    versions = dict(dictionary_release='fixture-release', dictionary_sha256='a'*64,
                    classifier_policy='fixture-v1', classifier_source_sha256='b'*64)
    rows = []
    for i in range(1, 4):
        rows.append(dict(sample_id=i, sha256=f'{i:064x}', obs_id=i,
            exact_token='permission.example', accepted_identity=i != 3,
            canonical_identity='permission.example' if i != 3 else '',
            category='AOSP', evidence_level='CATALOG_ACCEPTED',
            resolution_status='RESOLVED_CURRENT_IDENTITY', protection_base='normal',
            source_correspondence_verified=i != 3,
            source_match_state='RAW_EXACT' if i != 3 else 'PROJECTION_ONLY',
            source=dict(sample_id=i, sha256=f'{i:064x}', event_id=100+i, payload_sha256='c'*64,
                        raw_candidates=['permission.example'],
                        match_state='RAW_EXACT' if i != 3 else 'PROJECTION_ONLY',
                        historical_relationship='LATEST_REPORT_CORRESPONDENCE_ONLY'),
            history={'classification': 'UNKNOWN', 'classifier_version': 'historic-v1'},
            interpretation=dict(category='AOSP', evidence_level='CATALOG_ACCEPTED', protection_base='normal'),
            abstentions=[] if i != 3 else ['SOURCE_UNVERIFIED'], version_identity=versions))
    return SimpleNamespace(observations=rows, manifest={'versions': versions},
                           samples=[dict(sample_id=r['sample_id'], sha256=r['sha256']) for r in rows])


@pytest.fixture
def setup(tmp_path):
    clients = []
    roots = []
    def create(**kwargs):
        view = fixture_view()
        root = provision(tmp_path/f'provider-{len(clients)}', view, **kwargs)
        client = DisposableClient(root)
        clients.append(client)
        roots.append(root)
        return root, view, client
    yield create
    for client in clients:
        client.close()
    for root in roots:
        shutil.rmtree(root)


def scope(view):
    return dict(identities={str(m['sample_id']): m['sha256'] for m in view.samples},
                fields=sorted(view.observations[0]))


def test_positive_transaction_pages_publication_and_rollback(setup):
    root, view, client = setup(page_size=1)
    rows, receipt = client.read(**scope(view))
    assert rows == view.observations
    assert rows[-1]['abstentions'] == ['SOURCE_UNVERIFIED']
    assert client.process.pid != __import__('os').getpid()
    assert client.request(action='validate', publication=receipt['publication'])['valid']
    client.request(action='rollback')
    with pytest.raises(ConsumerDenied):
        client.request(action='validate', publication=receipt['publication'])
    with sqlite3.connect(root/'control.sqlite') as db:
        assert db.execute("SELECT count(*) FROM audit WHERE body LIKE '%PUBLISH%'").fetchone()[0] == 1
        assert db.execute('SELECT status FROM jobs').fetchone()[0] == 'INVALIDATED'


@pytest.mark.parametrize('case', ['unknown', 'malformed', 'fields', 'sql', 'mode'])
def test_server_admission_rejects_client_overrides(setup, case):
    _, view, client = setup()
    request = dict(action='open', **scope(view))
    if case == 'unknown': request['identities']['999'] = 'd'*64
    if case == 'malformed': request['identities']['1'] = 'not-a-sha'
    if case == 'fields': request['fields'].append('private_owner_field')
    if case == 'sql': request['query'] = 'DELETE FROM observations'
    if case == 'mode': request['mode'] = 'PRODUCTION'
    with pytest.raises(ConsumerDenied):
        client.request(**request)


@pytest.mark.parametrize('case', ['source', 'versions', 'history', 'interpretation', 'classification', 'hash', 'abstention'])
def test_source_corruption_never_publishes(setup, case):
    root, view, client = setup()
    with sqlite3.connect(root/'source.sqlite') as db:
        row = copy.deepcopy(view.observations[2])
        if case == 'source': row['source']['sha256'] = 'f'*64
        if case == 'versions': row['version_identity'] = {}
        if case == 'history': row['history'] = None
        if case == 'interpretation': row['category'] = 'IMAGINED'
        if case == 'classification': row['interpretation']['protection_base'] = 'dangerous'
        if case == 'hash': row['history']['classification'] = 'AOSP'
        if case == 'abstention': row['abstentions'] = []
        db.execute('UPDATE observations SET payload=? WHERE obs_id=3', (json.dumps(row),))
    with pytest.raises(ConsumerDenied):
        client.read(**scope(view))
    with sqlite3.connect(root/'control.sqlite') as db:
        assert not db.execute("SELECT 1 FROM jobs WHERE status='PUBLISHED'").fetchone()


def test_consistent_read_snapshot_and_next_reader_detects_change(setup):
    root, view, client = setup(page_size=1)
    cursor = client.request(action='open', **scope(view))['cursor']
    with sqlite3.connect(root/'source.sqlite') as db:
        db.execute("UPDATE observations SET payload='{}' WHERE obs_id=2")
    rows = []
    while True:
        page = client.request(action='page', cursor=cursor)
        rows.extend(page['rows']); cursor = page['cursor']
        if page['done']: break
    assert rows == view.observations
    client.request(action='publish')
    other = DisposableClient(root)
    try:
        with pytest.raises(ConsumerDenied): other.read(**scope(view))
    finally:
        other.close()


@pytest.mark.parametrize('revoke', [True, False])
def test_revocation_or_new_authority_generation_invalidates_exports(setup, revoke):
    root, view, client = setup()
    _, receipt = client.read(**scope(view))
    change_authority(root, revoke=revoke)
    with pytest.raises(ConsumerDenied):
        client.request(action='validate', publication=receipt['publication'])


def test_expiry_denies_start(setup):
    _, view, client = setup(expires=time.time()-1)
    with pytest.raises(ConsumerDenied, match='EXPIRED'): client.read(**scope(view))


def test_revocation_between_pages_denies_remaining_output(setup):
    root, view, client = setup(page_size=1)
    cursor = client.request(action='open', **scope(view))['cursor']
    page = client.request(action='page', cursor=cursor)
    change_authority(root)
    with pytest.raises(ConsumerDenied): client.request(action='page', cursor=page['cursor'])


def test_replayed_cursor_denied(setup):
    _, view, client = setup(page_size=1)
    cursor = client.request(action='open', **scope(view))['cursor']
    client.request(action='page', cursor=cursor)
    with pytest.raises(ConsumerDenied, match='CONTINUATION'): client.request(action='page', cursor=cursor)


def test_sqlite_progress_timeout_is_real_engine_interruption(setup):
    _, view, client = setup(query_seconds=1e-12)
    with pytest.raises(ConsumerDenied, match='OperationalError'): client.read(**scope(view))


def test_nonindexed_projection_plan_denied(setup):
    root, view, client = setup()
    with sqlite3.connect(root/'source.sqlite') as db:
        db.executescript('ALTER TABLE observations RENAME TO old; CREATE TABLE observations(obs_id INTEGER,payload TEXT); INSERT INTO observations SELECT * FROM old;')
    with pytest.raises(ConsumerDenied, match='QUERY_PLAN'): client.read(**scope(view))


def test_cross_process_single_job_and_cumulative_budget(setup):
    root, view, client = setup(global_rows=3)
    cursor = client.request(action='open', **scope(view))['cursor']
    other = DisposableClient(root)
    try:
        with pytest.raises(ConsumerDenied, match='CROSS_PROCESS_BUSY'): other.read(**scope(view))
    finally: other.close()
    client.request(action='page', cursor=cursor)
    client.request(action='publish')
    third = DisposableClient(root)
    try:
        with pytest.raises(ConsumerDenied, match='RESOURCE_EXHAUSTED'): third.read(**scope(view))
    finally: third.close()


@pytest.mark.parametrize('fault', ['missing', 'forged', 'truncated'])
def test_durable_audit_failure_rejects_access(setup, fault):
    root, view, client = setup()
    _, receipt = client.read(**scope(view))
    with sqlite3.connect(root/'control.sqlite') as db:
        if fault == 'missing': db.execute('DROP TABLE audit')
        if fault == 'forged': db.execute("UPDATE audit SET body='forged' WHERE seq=1")
        if fault == 'truncated': db.execute('DELETE FROM audit WHERE seq=(SELECT max(seq) FROM audit)')
    with pytest.raises(ConsumerDenied): client.request(action='validate', publication=receipt['publication'])


def test_killed_transaction_requires_conservative_lease_recovery(setup):
    root, view, client = setup(max_seconds=0.3)
    client.request(action='open', **scope(view))
    client.process.terminate(); client.process.join()
    time.sleep(0.35)
    assert recover(root) == 1
    fresh = DisposableClient(root)
    try:
        assert len(fresh.read(**scope(view))[0]) == 3
    finally: fresh.close()


def test_byte_exhaustion_is_not_zero_evidence(setup):
    _, view, client = setup(global_bytes=1)
    with pytest.raises(ConsumerDenied, match='RESOURCE_EXHAUSTED'): client.read(**scope(view))


def test_interrupted_transport_has_explicit_unavailable_disposition(setup):
    _, view, client = setup()
    client.request(action='open', **scope(view))
    client.process.terminate(); client.process.join()
    with pytest.raises(ConsumerDenied, match='TRANSPORT_UNAVAILABLE'):
        client.request(action='publish')


def test_publication_survives_clean_disconnect_but_not_authority_change(setup):
    root, view, client = setup()
    _, receipt = client.read(**scope(view))
    client.close()
    later = DisposableClient(root)
    try:
        assert later.request(action='validate', publication=receipt['publication'])['valid']
        change_authority(root, revoke=False)
        with pytest.raises(ConsumerDenied): later.request(action='validate', publication=receipt['publication'])
    finally: later.close()


def test_no_unbounded_terminal_page_polling(setup):
    _, view, client = setup()
    cursor = client.request(action='open', **scope(view))['cursor']
    cursor = client.request(action='page', cursor=cursor)['cursor']
    page = client.request(action='page', cursor=cursor)
    assert page['done']
    with pytest.raises(ConsumerDenied, match='CONTINUATION_FINISHED'):
        client.request(action='page', cursor=page['cursor'])


def test_audit_work_has_a_hard_bound(setup):
    root, view, client = setup()
    with sqlite3.connect(root/'control.sqlite') as db:
        db.executemany('INSERT INTO audit VALUES (?,?,?,?)', [(i, '{}', '', '') for i in range(1,10001)])
    with pytest.raises(ConsumerDenied, match='AUDIT_RESOURCE_BOUND'):
        client.read(**scope(view))


def test_owner_query_pin_must_match_installed_template(setup):
    from obsidiandroid.governance.disposable_consumer import _mac
    root, view, client = setup()
    store = _Store(root)
    changed = dict(store.contract, query_sha256='f'*64)
    (root/'contract.json').write_text(json.dumps(dict(contract=changed, mac=_mac(store.key, changed))))
    # A new provider must reject an otherwise authenticated contract for different SQL.
    other = DisposableClient(root)
    try:
        with pytest.raises(ConsumerDenied, match='QUERY_IDENTITY_MISMATCH'):
            other.read(**scope(view))
    finally: other.close()
