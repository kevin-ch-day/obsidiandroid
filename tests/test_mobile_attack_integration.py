"""Pinned-source, evidence-semantics and compatibility regressions; no model fitting."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from obsidiandroid.governance.mobile_attack_reference import load_mobile_attack_reference, SHA256, RELEASE
from obsidiandroid.governance.mobile_attack_permission_mapping import mobile_attack_permission_mapping_payload, validate_mapping
from obsidiandroid.governance.permission_attack_evidence import (
    PermissionIdentity, PermissionObservation, assess_permission_observation,
    project_identity_dispositions, build_development_store,
)
from obsidiandroid.pipeline.permission_trends.attack_mapping import build_attack_mobile_hypotheses


def identity(token):
    return PermissionIdentity(token,'AOSP_PUBLIC','RETAINED_SOURCE_EXACT','synthetic-retained-catalog','a'*64)


def obs(token,role='REQUESTED',source='STATIC_MANIFEST',**kwargs):
    return PermissionObservation(1,'b'*64,token,role,source,'synthetic-v1',**kwargs)


def test_official_bytes_are_pinned_and_tampering_is_rejected(tmp_path):
    from obsidiandroid.governance.mobile_attack_reference import ARTIFACT
    from obsidiandroid.common.repo_paths import repo_root
    data=(repo_root()/ARTIFACT).read_bytes();assert hashlib.sha256(data).hexdigest()==SHA256
    path=tmp_path/'source.json';path.write_bytes(data+b' ')
    with pytest.raises(ValueError,match='SHA-256'):load_mobile_attack_reference(path)


@pytest.mark.parametrize('index',range(10))
def test_every_original_technique_corrected_against_official_source(index):
    mapping=mobile_attack_permission_mapping_payload();rule=mapping['rules'][index]
    technique=load_mobile_attack_reference().technique(rule['attack_id'])
    assert rule['stix_id']==technique.stix_id
    assert rule['tactics']==list(technique.tactics)
    assert 'confidence' not in rule and rule['behavioral_assertion'] is False
    assert rule['origin']=='bootstrap-correction'


@pytest.mark.parametrize('mutation',['tactics','missing_id','deprecated','revoked','stix','name','release','hash','commit','confidence','behavior','duplicate_rule','duplicate_edge','contradiction','object_version','object_modified','duplicate_roles'])
def test_invalid_or_obsolete_relationships_fail_closed(mutation):
    p=copy.deepcopy(mobile_attack_permission_mapping_payload());r=p['rules'][0]
    if mutation=='tactics':r['tactics']=['privilege-escalation']
    elif mutation=='missing_id':r['attack_id']='T9999.999'
    elif mutation=='deprecated':r['attack_id']='T1401'
    elif mutation=='revoked':r['attack_id']='T1540'
    elif mutation=='stix':r['stix_id']='attack-pattern--wrong'
    elif mutation=='name':r['attack_name']='wrong name'
    elif mutation in {'release','hash','commit'}:p['attack_source'][{'release':'release','hash':'sha256','commit':'commit'}[mutation]]='wrong'
    elif mutation=='object_version':r['technique_version']='wrong'
    elif mutation=='object_modified':r['technique_modified']='wrong'
    elif mutation=='duplicate_roles':r['allowed_roles']*=2
    elif mutation=='confidence':r['confidence']='direct'
    elif mutation=='behavior':r['behavioral_assertion']=True
    elif mutation=='duplicate_rule':p['rules'].append(copy.deepcopy(r))
    elif mutation=='duplicate_edge':q=copy.deepcopy(r);q['rule_id']='different';p['rules'].append(q)
    elif mutation=='contradiction':p['identity_assessments'].append({'permission':r['required_any'][0],'disposition':'NO_DIRECT_MAPPING','rationale':'contradicts','reference':'synthetic'})
    with pytest.raises(ValueError):validate_mapping(p)


@pytest.mark.parametrize('index',range(14))
def test_every_rule_has_role_aware_positive_and_negative_examples(index):
    mapping=mobile_attack_permission_mapping_payload();rule=mapping['rules'][index];token=rule['required_any'][0]
    o=obs(token,role=rule['allowed_roles'][0],api_level=37,source_event_id='synthetic-event',source_validation='SOURCE_BOUND',provenance_refs=('synthetic-source',))
    rows=assess_permission_observation(o,identity(token),mapping)
    matched=next(r for r in rows if r['rule_id']==rule['rule_id'])
    assert matched['behavioral_interpretation']=='SUPPORTING_STATIC_INDICATOR'
    assert matched['technique_observed'] is False and matched['missing_evidence']
    negative=assess_permission_observation(obs(token,role='DEFINED'),identity(token),mapping)
    assert all(r['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE' and not r['technique_observed'] for r in negative)


def test_exact_token_identity_and_missing_evidence_are_not_promoted():
    token='android.permission.READ_SMS'
    lower=assess_permission_observation(obs(token.lower()),identity(token))
    assert lower[0]['disposition']=='UNRESOLVED' and lower[0]['attack_id'] is None
    provider=assess_permission_observation(obs(token,role='UNKNOWN',source='PROVIDER_REPORT'),identity(token))
    assert provider[0]['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE'
    assert not provider[0]['timestamp_available'] and not provider[0]['technique_observed']
    with pytest.raises(ValueError,match='provider'):
        assess_permission_observation(obs(token,role='REQUESTED',source='PROVIDER_REPORT'),identity(token))


def test_runtime_grant_is_not_observed_behavior_and_static_code_is_not_execution():
    token='android.permission.RECORD_AUDIO'
    a=assess_permission_observation(obs(token,role='RUNTIME_GRANT',source='RUNTIME_GRANT'),identity(token))
    b=assess_permission_observation(obs(token,role='API_BEHAVIOR',source='STATIC_CODE'),identity(token))
    assert all(not r['technique_observed'] for r in a+b)
    assert all(r['behavioral_interpretation']!='SUPPORTING_RUNTIME_OBSERVATION' for r in a+b)


def test_api_constraints_and_binding_roles_are_preserved():
    token='android.permission.BIND_ACCESSIBILITY_SERVICE'
    rows=assess_permission_observation(obs(token,role='COMPONENT_GUARD',api_level=1),identity(token))
    assert len(rows)==2 and all(r['api_applicability']=='UNSUPPORTED_API' for r in rows)
    assert all(r['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE' for r in rows)
    with pytest.raises(ValueError,match='timezone'):obs(token,observed_at='2026-01-01T00:00:00').validate()


def test_no_direct_mapping_is_reviewed_not_a_negative_observation():
    token='android.permission.INTERNET';r=assess_permission_observation(obs(token),identity(token))[0]
    assert r['disposition']=='NO_DIRECT_MAPPING' and r['attack_id'] is None
    assert r['negative_behavior_observation'] is False
    unknown=assess_permission_observation(obs('vendor.permission.NEW'),None)[0]
    assert unknown['disposition']=='UNRESOLVED'
    pending=assess_permission_observation(obs('vendor.permission.NEW'),identity('vendor.permission.NEW'))[0]
    assert pending['disposition']=='PENDING_REVIEW'


def test_family_labels_cannot_enter_sample_intake():
    with pytest.raises(TypeError):PermissionObservation(1,'a'*64,'android.permission.READ_SMS','UNKNOWN','PROVIDER_REPORT','v1',family_label='Anubis')


def catalog():
    tokens=['android.permission.BIND_ACCESSIBILITY_SERVICE','android.permission.INTERNET','vendor.permission.NEW']
    return {'fixture_set':'synthetic-catalog','platform_release':{'full_api':'37'},
            'permission_identities':[{'canonical_name':p,'authority_class':'AOSP_PUBLIC','source_snapshot_ids':['synthetic']} for p in tokens],
            'declaration_revisions':[{'canonical_name':p,'protection':{'raw_expression':'signature'}} for p in tokens]}


def test_disposable_sqlite_projection_many_to_many_and_stable_replay(tmp_path):
    p=mobile_attack_permission_mapping_payload();a=project_identity_dispositions(catalog(),'a'*64,p)
    b=project_identity_dispositions(catalog(),'a'*64,p);assert a==b
    receipt=build_development_store(tmp_path/'a.sqlite3',a,p);other=build_development_store(tmp_path/'b.sqlite3',b,p)
    assert receipt['logical_projection_sha256']==other['logical_projection_sha256']
    conn=sqlite3.connect(tmp_path/'a.sqlite3')
    assert conn.execute('select count(*) from permission_relationship').fetchone()[0]==2
    assert conn.execute("select count(*) from technique_tactic where attack_id='T1453'").fetchone()[0]==2
    with pytest.raises(sqlite3.IntegrityError):conn.execute("update disposition set behavioral_assertion=1")
    with pytest.raises(sqlite3.IntegrityError):conn.execute("update disposition set status='VERIFIED_ATTACK'")
    conn.close()
    with pytest.raises(FileExistsError):build_development_store(tmp_path/'a.sqlite3',a,p)
    c=catalog();c['permission_identities'].append(c['permission_identities'][0])
    with pytest.raises(ValueError,match='Duplicate'):project_identity_dispositions(c,'a'*64,p)


def test_legacy_group_prevalence_remains_hints_not_individual_behavior():
    frame=pd.DataFrame([{'group':'banker','permission':'android.permission.read_sms','sample_count':10,'prevalence':.5}])
    out=build_attack_mobile_hypotheses(prevalence_df=frame,run_id='synthetic',group_field='group',group_kind='family')
    assert not out.empty and out.confidence.isna().all()
    assert not out.technique_observed.any() and not out.cooccurrence_established.any()
    assert out.attack_release.eq(RELEASE).all()
    assert not out.eligible_for_family_model_features.any()


def test_retained_catalog_hash_and_conflicted_identity_fail_closed(tmp_path):
    from obsidiandroid.governance.permission_attack_evidence import load_retained_pi_catalog
    p=tmp_path/'catalog.json';p.write_text(json.dumps(catalog()))
    with pytest.raises(ValueError,match='SHA-256'):load_retained_pi_catalog(p,'f'*64)
    c,d=load_retained_pi_catalog(p,hashlib.sha256(p.read_bytes()).hexdigest())
    assert c==catalog()
    c['declaration_conflicts']=[{'canonical_name':'android.permission.BIND_ACCESSIBILITY_SERVICE'}]
    rows=project_identity_dispositions(c,d)
    r=next(r for r in rows if r['canonical_permission']=='android.permission.BIND_ACCESSIBILITY_SERVICE')
    assert r['disposition']=='UNRESOLVED' and not r['attack_ids']
    i=PermissionIdentity(r['canonical_permission'],r['authority_class'],r['identity_status'],r['source_scope'],r['source_digest'])
    assert assess_permission_observation(obs(i.canonical_permission),i)[0]['disposition']=='UNRESOLVED'


def test_snapshot_digest_does_not_invent_payload_event_or_observation_time():
    o=obs('android.permission.READ_SMS',role='UNKNOWN',source='PROVIDER_REPORT',
          source_snapshot_digest='c'*64,source_validation='SOURCE_BOUND',provenance_refs=('retained-export',))
    r=assess_permission_observation(o,identity(o.raw_token))[0]
    assert r['source_payload_digest'] is None and r['source_event_id'] is None
    assert not r['timestamp_available'] and not r['technique_observed']
    assert r['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE'


@pytest.mark.parametrize('sample_id,sha',[(0,'a'*64),(True,'a'*64),(1,''),(1,'A'*64)])
def test_missing_or_inexact_sample_identity_rejected(sample_id,sha):
    with pytest.raises(ValueError,match='Exact sample'):
        PermissionObservation(sample_id,sha,'android.permission.READ_SMS','UNKNOWN','PROVIDER_REPORT','v1').validate()


def test_runtime_observation_does_not_establish_technique():
    token='android.permission.RECORD_AUDIO'
    r=assess_permission_observation(obs(token,role='API_BEHAVIOR',source='RUNTIME_TRACE',
        source_validation='SOURCE_BOUND',source_event_id='synthetic-trace',
        observed_at='2026-11-13T00:00:00Z',observation_time_meaning='TRACE_EVENT_TIME',
        source_payload_digest='a'*64,provenance_refs=('synthetic-trace',)),identity(token))[0]
    assert r['behavioral_interpretation']=='SUPPORTING_RUNTIME_OBSERVATION'
    assert r['technique_observed'] is False and r['missing_evidence']


def test_offline_owner_catalog_to_cli_projection_roundtrip(tmp_path):
    from scripts.diagnostics.project_permission_attack import run
    path=tmp_path/'catalog.json';path.write_text(json.dumps(catalog()))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    a=run(path,digest,tmp_path/'a');b=run(path,digest,tmp_path/'b')
    assert a['logical_projection_sha256']==b['logical_projection_sha256']
    assert a['identities']==3 and not a['training_authorized']
    with pytest.raises(FileExistsError):run(path,digest,tmp_path/'a')
