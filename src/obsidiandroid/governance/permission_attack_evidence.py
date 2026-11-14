"""Source-aware analytical ATT&CK relationships; never a family/model feature authority."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .mobile_attack_permission_mapping import mobile_attack_permission_mapping_payload, DISPOSITIONS, ROLES

SOURCE_KINDS = frozenset({'PROVIDER_REPORT','STATIC_MANIFEST','STATIC_CODE','RUNTIME_GRANT','RUNTIME_TRACE'})
INTERPRETATIONS = frozenset({'POTENTIAL_CAPABILITY','SUPPORTING_STATIC_INDICATOR',
                           'SUPPORTING_RUNTIME_OBSERVATION','CORROBORATED_TECHNIQUE_RELATED_BEHAVIOR',
                           'INSUFFICIENT_EVIDENCE','NO_DIRECT_ATTACK_RELATIONSHIP'})


@dataclass(frozen=True)
class PermissionIdentity:
    canonical_permission: str
    authority_class: str
    identity_status: str
    source_scope: str
    source_digest: str
    protection: str | None = None
    api_release: str | None = None


@dataclass(frozen=True)
class PermissionObservation:
    """Independent identity, provenance, role, time and evidence dimensions.

    Family/type/model labels are deliberately absent from the intake contract.
    Provider-only unresolved exports cannot supply requested/defined/grant roles.
    """
    sample_id: int
    sha256: str
    raw_token: str
    role: str
    source_kind: str
    source_version: str
    source_event_id: str | None = None
    source_payload_digest: str | None = None
    source_snapshot_digest: str | None = None
    observed_at: str | None = None
    observation_time_meaning: str = 'UNKNOWN'
    extracted_at: str | None = None
    provenance_refs: tuple[str, ...] = ()
    source_validation: str = 'UNVERIFIED'
    api_level: int | None = None
    source_asserted_role: str | None = None
    source_field_path: str | None = None
    role_interpretation_rule: str | None = None

    def validate(self) -> None:
        if type(self.sample_id) is not int or self.sample_id < 1 or not re.fullmatch('[a-f0-9]{64}',self.sha256):
            raise ValueError('Exact sample ID/SHA-256 required')
        if not isinstance(self.raw_token,str) or not self.raw_token or not self.source_version:
            raise ValueError('Raw token and source version required')
        if self.source_validation not in {'UNVERIFIED','SOURCE_BOUND'}:
            raise ValueError('Unsupported source validation status')
        if self.source_payload_digest is not None and not re.fullmatch('[a-f0-9]{64}',self.source_payload_digest):
            raise ValueError('Invalid source payload digest')
        if self.source_snapshot_digest is not None and not re.fullmatch('[a-f0-9]{64}',self.source_snapshot_digest):
            raise ValueError('Invalid source snapshot digest')
        if self.role not in ROLES or self.source_kind not in SOURCE_KINDS:
            raise ValueError('Unknown source kind or permission role')
        if self.source_asserted_role is not None:
            if (self.source_asserted_role != 'PROVIDER_REPORTED_REQUIRED_PERMISSION'
                or self.source_kind != 'PROVIDER_REPORT' or self.role != 'UNKNOWN'
                or self.source_validation != 'SOURCE_BOUND' or not self.source_payload_digest
                or not self.source_event_id or not self.provenance_refs
                or self.source_field_path != '$.data.attributes.androguard.permission_details'
                or self.role_interpretation_rule != 'pi-retained-provider-required-v1'):
                raise ValueError('Provider role assertion requires exact source field/event/payload rule; no manifest-role promotion')
        elif self.source_field_path is not None or self.role_interpretation_rule is not None:
            raise ValueError('Source role interpretation metadata requires a supported assertion')
        if self.source_kind=='PROVIDER_REPORT' and self.role!='UNKNOWN':
            raise ValueError('Unresolved provider evidence cannot assert requested/defined/granted/runtime roles')
        allowed = {'STATIC_MANIFEST':{'REQUESTED','DEFINED','COMPONENT_GUARD','UNKNOWN'},
                   'STATIC_CODE':{'API_BEHAVIOR','UNKNOWN'},'RUNTIME_GRANT':{'RUNTIME_GRANT','UNKNOWN'},
                   'RUNTIME_TRACE':{'API_BEHAVIOR','UNKNOWN'}}
        if self.source_kind in allowed and self.role not in allowed[self.source_kind]:
            raise ValueError('Permission role/source-kind mismatch')
        if self.api_level is not None and (type(self.api_level) is not int or self.api_level<1):
            raise ValueError('Invalid Android API level')
        for value in [self.observed_at,self.extracted_at]:
            if value is not None:
                parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                if parsed.tzinfo is None:raise ValueError('Timestamp timezone required; do not guess naive source time')
        if self.observed_at is not None and self.observation_time_meaning=='UNKNOWN':
            raise ValueError('Observation timestamp meaning required')


def identity_is_qualified(identity: PermissionIdentity | None, token: str) -> bool:
    return bool(identity and identity.canonical_permission==token
                and identity.identity_status=='RETAINED_SOURCE_EXACT'
                and identity.authority_class!='UNKNOWN' and identity.source_scope
                and re.fullmatch('[a-f0-9]{64}',identity.source_digest))


def assess_permission_observation(observation: PermissionObservation,
                                  identity: PermissionIdentity | None,
                                  mapping: dict | None = None) -> list[dict]:
    """Report potential relationships; this phase cannot assert an observed technique."""
    observation.validate()
    mapping=mapping or mobile_attack_permission_mapping_payload()
    base={**asdict(observation), 'canonical_permission':identity.canonical_permission if identity else None,
          'permission_authority':identity.authority_class if identity else 'UNKNOWN',
          'identity_scope':identity.source_scope if identity else None,
          'identity_status':identity.identity_status if identity else 'UNRESOLVED',
          'identity_source_digest':identity.source_digest if identity else None,
          'identity_protection_context':identity.protection if identity else None,
          'identity_api_release':identity.api_release if identity else None,
          'attack_release':mapping['attack_source']['release'],'mapping_version':mapping['version'],
          'mapping_hash':mapping.get('hash'), 'technique_observed':False,
          'source_role_complete':observation.role!='UNKNOWN',
          'source_role_assertion_available':observation.source_asserted_role is not None,
          'timestamp_available':observation.observed_at is not None,
          'evidence_availability':'RETAINED_SOURCE_BOUND' if observation.source_validation=='SOURCE_BOUND' and (observation.source_payload_digest or observation.source_snapshot_digest) and observation.provenance_refs else 'INSUFFICIENT_PROVENANCE'}
    if not identity_is_qualified(identity,observation.raw_token):
        return [{**base,'disposition':'UNRESOLVED','attack_id':None,'stix_id':None,
                 'behavioral_interpretation':'INSUFFICIENT_EVIDENCE',
                 'missing_evidence':['exact governed identity/authority; no implicit casefold alias']}]
    reviews={a['permission']:a for a in mapping.get('identity_assessments',[])}
    decision=reviews.get(observation.raw_token)
    if decision and decision['disposition'] in {'NO_DIRECT_MAPPING','NOT_VALID_PERMISSION'}:
        return [{**base,'disposition':decision['disposition'],'attack_id':None,'stix_id':None,
                 'behavioral_interpretation':'NO_DIRECT_ATTACK_RELATIONSHIP' if decision['disposition']=='NO_DIRECT_MAPPING' else 'INSUFFICIENT_EVIDENCE',
                 'assessment_rationale':decision['rationale'],'missing_evidence':[],
                 'negative_behavior_observation':False}]
    if decision and decision['disposition'] in {'PENDING_REVIEW','UNRESOLVED'}:
        return [{**base,'disposition':decision['disposition'],'attack_id':None,'stix_id':None,
                 'behavioral_interpretation':'INSUFFICIENT_EVIDENCE',
                 'assessment_rationale':decision['rationale'],
                 'missing_evidence':['reviewed hold: additional applicability or source evidence'],
                 'assessment_reference':decision['reference']}]
    rules=[r for r in mapping['rules'] if observation.raw_token in r['required_any']]
    if not rules:
        return [{**base,'disposition':'PENDING_REVIEW','attack_id':None,'stix_id':None,
                 'behavioral_interpretation':'INSUFFICIENT_EVIDENCE','missing_evidence':['mapping review']}]
    results=[]
    for rule in rules:
        missing=list(rule['observed_behavior_requires'])
        minimum=rule['permission_constraints'][observation.raw_token]['api_min']
        api_status='UNKNOWN' if observation.api_level is None or minimum is None else 'COMPATIBLE_MINIMUM_ONLY' if observation.api_level>=minimum else 'UNSUPPORTED_API'
        review_from=rule['permission_constraints'][observation.raw_token].get('api_review_required_from')
        if review_from is not None and observation.api_level is not None and observation.api_level>=review_from:
            api_status='CONTEXT_REVIEW_REQUIRED'
        role_compatible=observation.role in rule['allowed_roles']
        supporting='INSUFFICIENT_EVIDENCE'
        if role_compatible and api_status not in {'UNSUPPORTED_API','CONTEXT_REVIEW_REQUIRED'}:
            supporting='POTENTIAL_CAPABILITY'
            if (observation.source_kind=='STATIC_MANIFEST' and observation.source_validation=='SOURCE_BOUND'
                and observation.provenance_refs and observation.source_event_id):
                supporting='SUPPORTING_STATIC_INDICATOR'
        if (observation.source_kind=='RUNTIME_TRACE' and observation.role=='API_BEHAVIOR'
            and observation.source_validation=='SOURCE_BOUND' and observation.source_event_id
            and observation.observed_at and observation.provenance_refs and api_status not in {'UNSUPPORTED_API','CONTEXT_REVIEW_REQUIRED'}):
            supporting='SUPPORTING_RUNTIME_OBSERVATION'
        if not role_compatible:missing.insert(0,'permission role compatible with rule')
        if api_status=='CONTEXT_REVIEW_REQUIRED':missing.append('target SDK/storage-scope applicability review; permission presence may have no effect')
        if api_status=='UNKNOWN':missing.append('Android API applicability')
        if api_status=='UNSUPPORTED_API':missing.append('permission unavailable at supplied Android API level')
        if observation.observed_at is None:missing.append('observation timestamp and meaning')
        results.append({**base,'rule_id':rule['rule_id'],'attack_id':rule['attack_id'],'stix_id':rule['stix_id'],
                        'attack_name':rule['attack_name'],'tactics':rule['tactics'],
                        'relationship_category':rule['relationship_category'],
                        'disposition':rule['relationship_category'] if supporting!='INSUFFICIENT_EVIDENCE' else 'CONTEXT_REQUIRED',
                        'api_applicability':api_status,'behavioral_interpretation':supporting,
                        'missing_evidence':missing,'permission_role_compatible':role_compatible})
    return results


def load_retained_pi_catalog(path: Path, expected_sha256: str) -> tuple[dict, str]:
    """Load an explicitly pinned owner-produced catalog, never a live substitute.

    Callers must retain the independent digest/producer baseline receipt. This
    checks byte identity; it does not attest completeness or live currentness.
    """
    if not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise ValueError('Explicit retained PI SHA-256 required')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError('Retained PI catalog SHA-256 mismatch')
    catalog = json.loads(payload)
    for field in ('fixture_set', 'permission_identities', 'declaration_revisions', 'platform_release'):
        if field not in catalog:
            raise ValueError('Missing owner catalog contract field: ' + field)
    return catalog, digest


def project_identity_dispositions(catalog: dict, source_digest: str,
                                  mapping: dict | None = None) -> list[dict]:
    """Project every retained PI identity, preserving unknown/unreviewed cases."""
    mapping=mapping or mobile_attack_permission_mapping_payload()
    if not re.fullmatch('[a-f0-9]{64}',source_digest):raise ValueError('PI source digest required')
    declared={r['canonical_name'] for r in catalog['declaration_revisions']}
    conflicts={r['canonical_name'] for r in catalog.get('declaration_conflicts',[])}
    reviews={r['permission']:r for r in mapping.get('identity_assessments',[])}
    seen=set();result=[]
    for entry in sorted(catalog['permission_identities'],key=lambda r:r['canonical_name']):
        token=entry['canonical_name']
        if token in seen:raise ValueError('Duplicate/contradictory PI identity; do not silently deduplicate')
        seen.add(token)
        qualified=token in declared and entry['authority_class']!='UNKNOWN'
        state='DECLARATION_CONFLICT_UNRESOLVED' if token in conflicts else 'RETAINED_SOURCE_EXACT' if qualified else 'AUTHORITY_OR_DECLARATION_UNRESOLVED'
        rules=[r for r in mapping['rules'] if token in r['required_any']]
        if not qualified:disposition='UNRESOLVED';reason='Identity authority or manifest declaration not established in retained source'
        elif token in conflicts:disposition='UNRESOLVED';reason='Multiple retained declaration alternatives need applicability review'
        elif token in reviews:disposition=reviews[token]['disposition'];reason=reviews[token]['rationale']
        elif rules:disposition='CONTEXT_REQUIRED' if any(r['relationship_category']=='CONTEXT_REQUIRED' for r in rules) else 'CAPABILITY_RELATED';reason='Source-checked analytical relationship; sample role, API/grant and behavior prerequisites remain separate'
        else:disposition='PENDING_REVIEW';reason='No reviewed relationship assessment; absence is not NO_DIRECT_MAPPING'
        result.append({'permission_key':hashlib.sha256((source_digest+'\0'+token).encode()).hexdigest(),
                       'raw_token':token,'canonical_permission':token,'authority_class':entry['authority_class'],
                       'identity_status':state,'source_scope':catalog['fixture_set'],'source_digest':source_digest,
                       'source_provenance_refs':entry['source_snapshot_ids'],'api_release':catalog['platform_release']['full_api'],
                       'protection':sorted({str(r['protection']['raw_expression']) for r in catalog['declaration_revisions'] if r['canonical_name']==token}),
                       'disposition':disposition,'assessment_rationale':reason,
                       'attack_ids':[r['attack_id'] for r in rules] if disposition in {'CAPABILITY_RELATED','CONTEXT_REQUIRED'} else [],
                       'rule_ids':[r['rule_id'] for r in rules] if disposition in {'CAPABILITY_RELATED','CONTEXT_REQUIRED'} else [],
                       'mapping_version':mapping['version'],'attack_release':mapping['attack_source']['release'],
                       'live_currentness':'NOT_ATTESTED; runtime/catalog read access unavailable',
                       'behavioral_assertion':False})
    return result


def build_development_store(path: Path, rows: list[dict], mapping: dict | None = None) -> dict:
    """Create a fresh local SQLite analytical overlay; never connects to PI/MySQL."""
    mapping=mapping or mobile_attack_permission_mapping_payload()
    if path.exists():raise FileExistsError('Refusing to overwrite an existing analytical store')
    if path.suffix!='.sqlite3':raise ValueError('Development store must be an explicit local SQLite file')
    if len({r['permission_key'] for r in rows})!=len(rows):raise ValueError('Duplicate identity keys')
    if any(r['disposition'] not in DISPOSITIONS or r['behavioral_assertion'] for r in rows):raise ValueError('Invalid or behavioral mapping disposition')
    path.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(path)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
        CREATE TABLE reference_release(release TEXT PRIMARY KEY, commit_sha TEXT NOT NULL, artifact_sha256 TEXT NOT NULL);
        CREATE TABLE technique(attack_id TEXT PRIMARY KEY,stix_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,version TEXT NOT NULL,modified TEXT NOT NULL,release TEXT NOT NULL REFERENCES reference_release);
        CREATE TABLE technique_tactic(attack_id TEXT REFERENCES technique,tactic TEXT NOT NULL,PRIMARY KEY(attack_id,tactic));
        CREATE TABLE permission_identity(permission_key TEXT PRIMARY KEY,canonical_permission TEXT NOT NULL,source_scope TEXT NOT NULL,source_digest TEXT NOT NULL,facts_json TEXT NOT NULL,UNIQUE(canonical_permission,source_scope));
        CREATE TABLE mapping_rule(rule_id TEXT PRIMARY KEY,attack_id TEXT NOT NULL REFERENCES technique,rule_json TEXT NOT NULL);
        CREATE TABLE disposition(permission_key TEXT PRIMARY KEY REFERENCES permission_identity,status TEXT NOT NULL CHECK(status IN ('CAPABILITY_RELATED','CONTEXT_REQUIRED','NO_DIRECT_MAPPING','UNRESOLVED','NOT_VALID_PERMISSION','PENDING_REVIEW')),rationale TEXT NOT NULL,behavioral_assertion INTEGER NOT NULL CHECK(behavioral_assertion=0));
        CREATE TABLE permission_relationship(permission_key TEXT REFERENCES permission_identity,rule_id TEXT REFERENCES mapping_rule,PRIMARY KEY(permission_key,rule_id));
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        from .mobile_attack_reference import load_mobile_attack_reference
        reference=load_mobile_attack_reference();source=mapping['attack_source']
        connection.execute('INSERT INTO reference_release VALUES (?,?,?)',(source['release'],source['commit'],source['sha256']))
        for attack_id in sorted({r['attack_id'] for r in mapping['rules']}):
            t=reference.technique(attack_id);connection.execute('INSERT INTO technique VALUES (?,?,?,?,?,?)',(t.attack_id,t.stix_id,t.name,t.version,t.modified,source['release']))
            connection.executemany('INSERT INTO technique_tactic VALUES (?,?)',[(t.attack_id,x) for x in t.tactics])
        connection.executemany('INSERT INTO mapping_rule VALUES (?,?,?)',[(r['rule_id'],r['attack_id'],json.dumps(r,sort_keys=True)) for r in mapping['rules']])
        for row in sorted(rows,key=lambda r:r['permission_key']):
            key=row['permission_key'];connection.execute('INSERT INTO permission_identity VALUES (?,?,?,?,?)',(key,row['canonical_permission'],row['source_scope'],row['source_digest'],json.dumps(row,sort_keys=True)))
            connection.execute('INSERT INTO disposition VALUES (?,?,?,0)',(key,row['disposition'],row['assessment_rationale']))
            connection.executemany('INSERT INTO permission_relationship VALUES (?,?)',[(key,r) for r in row['rule_ids']])
        connection.executemany('INSERT INTO metadata VALUES (?,?)',[('owner','ObsidianDroid local analytical assessment; PI source authority unchanged'),('training_authorized','false'),('production_deployment','false')])
        assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        connection.commit()
    except BaseException:
        connection.rollback();raise
    finally:connection.close()
    logical=hashlib.sha256(json.dumps(sorted(rows,key=lambda r:r['permission_key']),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'identities':len(rows),'logical_projection_sha256':logical,'local_sqlite_only':True,'source_authority_changed':False,'training_authorized':False}
