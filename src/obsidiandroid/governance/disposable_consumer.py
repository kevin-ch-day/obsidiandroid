"""Process-isolated SQLite consumer rehearsal, with no production transport.

The owner provisions a new private /tmp fixture. A pipe client cannot supply SQL,
source paths, approval records, signing keys or resource policy. Same-UID filesystem
access is trusted in this harness; production needs separate OS/service identities.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager, closing
import hmac
import json
import multiprocessing
import os
from pathlib import Path
import secrets
import sqlite3
import time

from obsidiandroid.governance.permission_consumer_conformance import CATEGORIES, LEVELS, STATUSES, PROTECTION

def fingerprint(value):
    """Hash the disposable provider's deterministic JSON fixture."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


MODE = 'DISPOSABLE_INTEGRATION_ONLY'
QUERY = 'SELECT obs_id, payload FROM observations WHERE obs_id > ? ORDER BY obs_id LIMIT ?'
MAX_BYTES = 128 * 1024**2


class ConsumerDenied(ValueError):
    """No valid research publication exists for the failed operation."""


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _mac(key, value):
    return hmac.new(key, encode(value), hashlib.sha256).hexdigest()


def _root(directory):
    root = Path(directory)
    if (root.resolve() != root or not root.is_relative_to(Path('/tmp')) or
            root == Path('/tmp') or root.is_symlink()):
        raise ConsumerDenied('DISPOSABLE_ROOT_REQUIRED')
    return root


def validate_row(row, versions, identities):
    """Validate retained interpretation semantics as well as immutable row hashes."""
    sid, oid, sha = row['sample_id'], row['obs_id'], row['sha256']
    if type(sid) is not int or type(oid) is not int or sid <= 0 or oid <= 0:
        raise ConsumerDenied('MALFORMED_IDENTITY')
    if identities.get(str(sid)) != sha:
        raise ConsumerDenied('UNKNOWN_IDENTITY')
    if row['version_identity'] != versions or not isinstance(row['history'], dict):
        raise ConsumerDenied('VERSION_OR_HISTORY_MISMATCH')
    if row['category'] not in CATEGORIES or row['evidence_level'] not in LEVELS or row['resolution_status'] not in STATUSES:
        raise ConsumerDenied('UNSUPPORTED_INTERPRETATION')
    if row['protection_base'] is not None and row['protection_base'] not in PROTECTION:
        raise ConsumerDenied('UNSUPPORTED_PROTECTION')
    for name in ['accepted_identity', 'source_correspondence_verified']:
        if type(row[name]) is not bool:
            raise ConsumerDenied('NONBOOLEAN_EVIDENCE')
    source = row['source']
    if (source['sample_id'], source['sha256']) != (sid, sha):
        raise ConsumerDenied('SOURCE_IDENTITY_MISMATCH')
    if source.get('match_state') != row['source_match_state']:
        raise ConsumerDenied('SOURCE_MATCH_CONFLICT')
    if row['source_correspondence_verified'] != (row['source_match_state'] == 'RAW_EXACT'):
        raise ConsumerDenied('SOURCE_AUTHORITY_CONFLICT')
    if row['source_correspondence_verified'] and row['exact_token'] not in source['raw_candidates']:
        raise ConsumerDenied('EXACT_TOKEN_MISMATCH')
    relationship = source['historical_relationship']
    if relationship == 'BOUND_ORIGINAL_EVENT':
        if (source.get('event_id'), source.get('payload_sha256')) != (
                row['history'].get('original_event_id'), row['history'].get('original_payload_sha256')) or not source.get('payload_sha256'):
            raise ConsumerDenied('HISTORICAL_BINDING_MISMATCH')
    elif relationship != 'LATEST_REPORT_CORRESPONDENCE_ONLY':
        raise ConsumerDenied('HISTORICAL_AUTHORITY_UNKNOWN')
    if not source.get('event_id') or not source.get('payload_sha256'):
        raise ConsumerDenied('SOURCE_REPORT_MISSING')
    if row['accepted_identity'] and not row['canonical_identity']:
        raise ConsumerDenied('CANONICAL_IDENTITY_MISSING')
    for field in ['category', 'evidence_level', 'protection_base']:
        if row['interpretation'].get(field) != row[field]:
            raise ConsumerDenied('CLASSIFICATION_CONFLICT')
    if not row['source_correspondence_verified'] and not row['abstentions']:
        raise ConsumerDenied('ABSTENTION_MISSING')


def provision(directory, view, *, expires=None, global_rows=27920, global_bytes=2*MAX_BYTES,
              page_size=100, max_seconds=60, query_seconds=2):
    """Owner-only fixture creation; never provision an existing or production DB."""
    root = _root(directory)
    if root.exists():
        raise ConsumerDenied('NEW_FIXTURE_REQUIRED')
    rows, versions = view.observations, view.manifest['versions']
    required = {'dictionary_release', 'dictionary_sha256', 'classifier_policy', 'classifier_source_sha256'}
    if not required <= set(versions) or any(not versions[k] for k in required):
        raise ConsumerDenied('VERSION_REQUIREMENTS_MISSING')
    ids = {str(int(m['sample_id'])): m['sha256'] for m in view.samples}
    if (not 0 < len(ids) <= 1212 or len(ids) != len(view.samples) or
            len(set(ids.values())) != len(ids) or not 0 < len(rows) <= 13960):
        raise ConsumerDenied('POPULATION_BOUND')
    if any(len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha) for sha in ids.values()):
        raise ConsumerDenied('MALFORMED_SHA')
    if type(page_size) is not int or not 1 <= page_size <= 100 or not 0 < query_seconds <= 30 or not 0 < max_seconds <= 600:
        raise ConsumerDenied('RESOURCE_POLICY')
    if len(encode(rows)) > MAX_BYTES:
        raise ConsumerDenied('INPUT_BYTE_BOUND')
    fields = sorted(rows[0])
    if len(fields) > 64 or any(sorted(row) != fields for row in rows):
        raise ConsumerDenied('FIELD_SCOPE')
    for row in rows:
        validate_row(row, versions, ids)
    if len({row['obs_id'] for row in rows}) != len(rows):
        raise ConsumerDenied('DUPLICATE_OBSERVATION')
    contract = dict(mode=MODE, versions=versions, identities=ids, fields=fields,
                    hashes={str(row['obs_id']): fingerprint(row) for row in rows},
                    snapshot=fingerprint(sorted(rows, key=lambda r: r['obs_id'])),
                    page_size=page_size, max_rows=len(rows), max_bytes=MAX_BYTES,
                    max_seconds=max_seconds, query_seconds=query_seconds,
                    query_sha256=hashlib.sha256(QUERY.encode()).hexdigest())
    root.mkdir(mode=0o700)
    key = secrets.token_bytes(32)
    (root/'key').write_bytes(key)
    (root/'contract.json').write_bytes(encode(dict(contract=contract, mac=_mac(key, contract))))
    with closing(sqlite3.connect(root/'source.sqlite')) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE observations(obs_id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        db.executemany('INSERT INTO observations VALUES (?,?)', [(r['obs_id'], encode(r).decode()) for r in rows])
        db.commit()
    with closing(sqlite3.connect(root/'control.sqlite')) as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE authority(epoch INTEGER, revoked INTEGER, expires REAL, rows_left INTEGER, bytes_left INTEGER, head TEXT);
        CREATE TABLE jobs(id TEXT PRIMARY KEY, epoch INTEGER, status TEXT, deadline REAL, cursor INTEGER, rows INTEGER, bytes INTEGER, output_hash TEXT);
        CREATE TABLE audit(seq INTEGER PRIMARY KEY, body TEXT, previous TEXT, mac TEXT);
        ''')
        db.execute('INSERT INTO authority VALUES (1,0,?,?,?,?)',
                   (expires if expires is not None else time.time()+3600, global_rows, global_bytes, ''))
        db.commit()
    for path in root.iterdir():
        path.chmod(0o600)
    return root


class _Store:
    def __init__(self, root):
        self.root = _root(root)
        for name in ['key', 'contract.json', 'source.sqlite', 'control.sqlite']:
            path = self.root/name
            if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
                raise ConsumerDenied('UNTRUSTED_FIXTURE_FILE')
        self.key = (self.root/'key').read_bytes()
        envelope = json.loads((self.root/'contract.json').read_bytes())
        self.contract = envelope['contract']
        if not hmac.compare_digest(envelope['mac'], _mac(self.key, self.contract)) or self.contract['mode'] != MODE:
            raise ConsumerDenied('CONTRACT_AUTHENTICATION')
        if self.contract['query_sha256'] != hashlib.sha256(QUERY.encode()).hexdigest():
            raise ConsumerDenied('QUERY_IDENTITY_MISMATCH')

    @contextmanager
    def control(self):
        db = sqlite3.connect((self.root/'control.sqlite').as_uri()+'?mode=rw', uri=True, timeout=0.2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, event):
        if db.execute('SELECT count(*) FROM audit').fetchone()[0] >= 10000:
            raise ConsumerDenied('AUDIT_RESOURCE_BOUND')
        previous = ''
        seq = 0
        for seq, body, parent, signature in db.execute('SELECT seq,body,previous,mac FROM audit ORDER BY seq'):
            if parent != previous or not hmac.compare_digest(signature, _mac(self.key, [seq, parent, body])):
                raise ConsumerDenied('AUDIT_AUTHENTICATION')
            previous = signature
        if db.execute('SELECT head FROM authority').fetchone()[0] != previous:
            raise ConsumerDenied('AUDIT_TRUNCATION')
        body = encode(dict(event, utc=time.time(), mode=MODE)).decode()
        signature = _mac(self.key, [seq+1, previous, body])
        db.execute('INSERT INTO audit VALUES (?,?,?,?)', (seq+1, body, previous, signature))
        db.execute('UPDATE authority SET head=?', (signature,))

    def check(self, db, job=None):
        epoch, revoked, expiry, _, _, _ = db.execute('SELECT * FROM authority').fetchone()
        if revoked or time.time() >= expiry:
            raise ConsumerDenied('AUTHORITY_REVOKED_OR_EXPIRED')
        if job:
            row = db.execute('SELECT epoch,status,deadline FROM jobs WHERE id=?', (job,)).fetchone()
            if not row or row[0] != epoch or row[1] not in {'ACTIVE', 'PUBLISHED'} or time.time() >= row[2]:
                raise ConsumerDenied('JOB_INVALIDATED_OR_EXPIRED')
        return epoch


def change_authority(directory, *, revoke=True):
    """Owner-only disposable revocation/version-generation change, never a source grant."""
    store = _Store(directory)
    with store.control() as db:
        db.execute('UPDATE authority SET epoch=epoch+1, revoked=?', (int(revoke),))
        db.execute("UPDATE jobs SET status='INVALIDATED' WHERE status IN ('ACTIVE','PUBLISHED')")
        store.audit(db, dict(event='AUTHORITY_CHANGED', revoked=bool(revoke)))


def recover(directory):
    """Expire orphan leases without refunding uncertain resource use."""
    store = _Store(directory)
    with store.control() as db:
        count = db.execute("UPDATE jobs SET status='ABORTED' WHERE status='ACTIVE' AND deadline<=?", (time.time(),)).rowcount
        store.audit(db, dict(event='RECOVER', expired_jobs=count, refunds=False))
    return count


def _serve(pipe, directory):
    source = None
    store = None
    job = None
    deadline = 0
    last = 0
    sequence = 0
    terminal = False
    collected = []
    try:
        store = _Store(directory)
        c = store.contract
        while True:
            if not pipe.poll(max(0.01, deadline-time.time()) if job else 10):
                raise ConsumerDenied('IDLE_DEADLINE')
            request = json.loads(pipe.recv_bytes(1024*1024))
            action = request.get('action')
            if action == 'open':
                if job or set(request) != {'action', 'identities', 'fields'}:
                    raise ConsumerDenied('REQUEST_SHAPE')
                if request['identities'] != c['identities'] or request['fields'] != c['fields']:
                    raise ConsumerDenied('POPULATION_OR_FIELDS_DENIED')
                with store.control() as db:
                    epoch = store.check(db)
                    if db.execute("SELECT 1 FROM jobs WHERE status='ACTIVE'").fetchone():
                        raise ConsumerDenied('CROSS_PROCESS_BUSY')
                    job = secrets.token_hex(16)
                    deadline = time.time()+c['max_seconds']
                    db.execute('INSERT INTO jobs VALUES (?,?,?,?,0,0,0,NULL)', (job, epoch, 'ACTIVE', deadline))
                    store.audit(db, dict(event='OPEN', job=job, snapshot=c['snapshot'], versions=fingerprint(c['versions'])))
                source = sqlite3.connect((store.root/'source.sqlite').as_uri()+'?mode=ro', uri=True, timeout=c['query_seconds'])
                source.execute('PRAGMA query_only=ON')
                source.execute('BEGIN')
                plan = source.execute('EXPLAIN QUERY PLAN '+QUERY, (0, c['page_size'])).fetchall()
                if not all('SEARCH observations USING INTEGER PRIMARY KEY' in r[3] for r in plan):
                    raise ConsumerDenied('QUERY_PLAN_DENIED')
                # Establish the read snapshot now, not at the first client continuation.
                source.execute('SELECT obs_id FROM observations WHERE obs_id>0 ORDER BY obs_id LIMIT 1').fetchall()
                token = dict(job=job, after=0, sequence=0, snapshot=c['snapshot'])
                response = dict(cursor=dict(value=token, mac=_mac(store.key, token)), mode=MODE)
            elif action == 'page':
                if terminal:
                    raise ConsumerDenied('CONTINUATION_FINISHED')
                if not job or set(request) != {'action', 'cursor'}:
                    raise ConsumerDenied('REQUEST_SHAPE')
                token = request['cursor']
                expected = dict(job=job, after=last, sequence=sequence, snapshot=c['snapshot'])
                if token['value'] != expected or not hmac.compare_digest(token['mac'], _mac(store.key, expected)):
                    raise ConsumerDenied('CONTINUATION_DENIED')
                with store.control() as db:
                    store.check(db, job)
                    if db.execute('SELECT status FROM jobs WHERE id=?', (job,)).fetchone()[0] != 'ACTIVE':
                        raise ConsumerDenied('JOB_NOT_ACTIVE')
                until = min(time.monotonic()+c['query_seconds'], time.monotonic()+max(0, deadline-time.time()))
                source.set_progress_handler(lambda: int(time.monotonic() >= until), 1)
                batch = source.execute(QUERY, (last, c['page_size'])).fetchall()
                source.set_progress_handler(None, 0)
                rows = []
                for oid, payload in batch:
                    row = json.loads(payload)
                    validate_row(row, c['versions'], c['identities'])
                    if row['obs_id'] != oid or fingerprint(row) != c['hashes'].get(str(oid)):
                        raise ConsumerDenied('SOURCE_ROW_BINDING')
                    rows.append(row)
                used = len(encode(rows))
                with store.control() as db:
                    store.check(db, job)
                    if db.execute('SELECT status FROM jobs WHERE id=?', (job,)).fetchone()[0] != 'ACTIVE':
                        raise ConsumerDenied('JOB_NOT_ACTIVE')
                    current = db.execute('SELECT cursor,rows,bytes FROM jobs WHERE id=?', (job,)).fetchone()
                    limits = db.execute('SELECT rows_left,bytes_left FROM authority').fetchone()
                    if (current[0] != last or current[1]+len(rows) > c['max_rows'] or
                            current[2]+used > c['max_bytes'] or limits[0] < len(rows) or limits[1] < used):
                        raise ConsumerDenied('RESOURCE_EXHAUSTED')
                    if batch:
                        last = batch[-1][0]
                    db.execute('UPDATE jobs SET cursor=?,rows=rows+?,bytes=bytes+? WHERE id=?', (last, len(rows), used, job))
                    db.execute('UPDATE authority SET rows_left=rows_left-?,bytes_left=bytes_left-?', (len(rows), used))
                    store.audit(db, dict(event='PAGE', job=job, rows=len(rows), bytes=used, after=last))
                terminal = not batch
                collected.extend(rows)
                sequence += 1
                token = dict(job=job, after=last, sequence=sequence, snapshot=c['snapshot'])
                response = dict(rows=rows, cursor=dict(value=token, mac=_mac(store.key, token)), staged=True, done=not batch)
            elif action == 'publish':
                if set(request) != {'action'} or not job or fingerprint(collected) != c['snapshot']:
                    raise ConsumerDenied('INCOMPLETE_PUBLICATION')
                with store.control() as db:
                    store.check(db, job)
                    if db.execute('SELECT status FROM jobs WHERE id=?', (job,)).fetchone()[0] != 'ACTIVE':
                        raise ConsumerDenied('JOB_NOT_ACTIVE')
                    db.execute("UPDATE jobs SET status='PUBLISHED',output_hash=? WHERE id=?", (c['snapshot'], job))
                    store.audit(db, dict(event='PUBLISH', job=job, output_hash=c['snapshot']))
                source.rollback()
                response = dict(publication=job, output_hash=c['snapshot'], mode=MODE)
            elif action == 'validate':
                if set(request) != {'action', 'publication'}:
                    raise ConsumerDenied('REQUEST_SHAPE')
                with store.control() as db:
                    store.check(db, request['publication'])
                    publication = db.execute('SELECT status,output_hash FROM jobs WHERE id=?', (request['publication'],)).fetchone()
                    if publication != ('PUBLISHED', c['snapshot']):
                        raise ConsumerDenied('PUBLICATION_INVALID')
                    store.audit(db, dict(event='ACCESS', publication=request['publication']))
                response = dict(valid=True, mode=MODE)
            elif action == 'rollback':
                with store.control() as db:
                    db.execute("UPDATE jobs SET status='INVALIDATED' WHERE id=?", (job,))
                    store.audit(db, dict(event='ROLLBACK', job=job))
                if source:
                    source.rollback()
                response = dict(valid=False)
            else:
                raise ConsumerDenied('OPERATION_DENIED')
            pipe.send_bytes(encode(dict(ok=True, result=response)))
    except (Exception, KeyboardInterrupt) as exc:
        try:
            if store:
                with store.control() as db:
                    db.execute("UPDATE jobs SET status='ABORTED' WHERE id=? AND status='ACTIVE'", (job,))
                    store.audit(db, dict(event='ABORT' if job else 'DENIED', job=job, reason=type(exc).__name__))
        except Exception:
            pass
        try:
            pipe.send_bytes(encode(dict(ok=False, error=str(exc) if isinstance(exc, ConsumerDenied) else type(exc).__name__)))
        except (OSError, BrokenPipeError):
            pass
    finally:
        if source:
            source.close()
        pipe.close()


class DisposableClient:
    """JSON pipe transport to a separate provider process; no production endpoint."""
    def __init__(self, directory):
        root = _root(directory)
        context = multiprocessing.get_context('spawn')
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_serve, args=(child, str(root)))
        self.process.start()
        child.close()

    def request(self, **request):
        try:
            self.pipe.send_bytes(encode(request))
            if not self.pipe.poll(35):
                self.close()
                raise ConsumerDenied('TRANSPORT_TIMEOUT')
            response = json.loads(self.pipe.recv_bytes(MAX_BYTES))
        except (EOFError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConsumerDenied('TRANSPORT_UNAVAILABLE') from exc
        if not response['ok']:
            raise ConsumerDenied(response['error'])
        return response['result']

    def read(self, identities, fields):
        cursor = self.request(action='open', identities=identities, fields=fields)['cursor']
        rows = []
        while True:
            page = self.request(action='page', cursor=cursor)
            rows.extend(page['rows'])
            cursor = page['cursor']
            if page['done']:
                break
        receipt = self.request(action='publish')
        if fingerprint(rows) != receipt['output_hash']:
            raise ConsumerDenied('TRANSPORT_CONTENT_MISMATCH')
        self.request(action='validate', publication=receipt['publication'])
        return rows, receipt

    def close(self):
        self.pipe.close()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
