"""Exact source reconciliation and bounded mapping review regressions, offline."""
import copy
import hashlib
import json

import pytest

from obsidiandroid.governance.permission_attack_reconciliation import (
    EXPORT_SCHEMA, load_owner_reference_export, reconcile_catalog_populations,
)
from obsidiandroid.governance.permission_attack_evidence import (
    PermissionIdentity, PermissionObservation, assess_permission_observation,
)
from obsidiandroid.governance.mobile_attack_permission_mapping import mobile_attack_permission_mapping_payload, validate_mapping


def retained(token='android.permission.READ_SMS'):
    return {'canonical_permission':token,'authority_class':'AOSP_PUBLIC','source_scope':'synthetic',
            'source_digest':'a'*64,'source_provenance_refs':['synthetic'],'disposition':'CAPABILITY_RELATED','attack_ids':['T1636.004']}


def export(token='android.permission.READ_SMS'):
    return {'schema_version':EXPORT_SCHEMA,'scope':{'database':'android_permission_intel','snapshot_id':'synthetic',
            'generated_at':'2026-11-13T00:00:00Z','schema_version':'synthetic','migration_versions':[],
            'source_owner':'synthetic-owner','coverage_statement':'non-exhaustive synthetic','authorization_ref':'synthetic-reference-only',
            'purpose':'REFERENCE_CATALOG_RECONCILIATION'},'record_count':1,'identities':[
                {'raw_token':token,'raw_token_utf8_hex':token.encode().hex(),'authority_class':'AOSP_PUBLIC','lifecycle_state':None,
                 'canonical_interpretations':[token],'aliases':[],'api_context':None,'protection_context':None,'evidence_refs':['synthetic'],
                 'available_observation_roles':None,'observation_time_fields':None}]}


def load(tmp_path, payload):
    p=tmp_path/'owner.json';p.write_text(json.dumps(payload));return load_owner_reference_export(p,hashlib.sha256(p.read_bytes()).hexdigest())


def test_no_current_export_is_unknown_not_empty_or_retained_only():
    r=reconcile_catalog_populations([retained()])[0]
    assert r['current_present'] is None and r['reconciliation_status']=='CURRENT_EVIDENCE_UNAVAILABLE'
    assert r['authority_comparison']==r['lifecycle_comparison']=='UNKNOWN'
    assert r['current_role_evidence_status']==r['current_timestamp_evidence_status']=='UNKNOWN'
    assert not r['source_absence_means_deleted'] and not r['technique_observed']


def test_union_exact_case_and_authority_canonical_conflicts(tmp_path):
    c=export('android.permission.read_sms');x=c['identities'][0]
    x['authority_class']='UNKNOWN';x['canonical_interpretations']=['vendor.permission.WRONG']
    current=load(tmp_path,c)
    r=reconcile_catalog_populations([retained()],current)
    assert len(r)==2 and {x['reconciliation_status'] for x in r}=={'RETAINED_ONLY_IN_SUPPLIED_SCOPES','CURRENT_ONLY_IN_SUPPLIED_SCOPES'}
    c=export();x=c['identities'][0];x['authority_class']='OEM';x['canonical_interpretations']=['vendor.permission.OTHER']
    r=reconcile_catalog_populations([retained()],load(tmp_path,c))[0]
    assert r['authority_comparison']=='CHANGED' and r['canonical_comparison']=='CONFLICT_REQUIRES_OWNER_REVIEW'
    assert r['lifecycle_comparison']=='UNKNOWN'


@pytest.mark.parametrize('mutation',['bytes','duplicate','count','database','time','authorization','missing_provenance'])
def test_invalid_owner_export_fails_closed(tmp_path,mutation):
    c=export()
    if mutation=='bytes':c['identities'][0]['raw_token_utf8_hex']='00'
    elif mutation=='duplicate':c['identities']*=2;c['record_count']=2
    elif mutation=='count':c['record_count']=2
    elif mutation=='database':c['scope']['database']='wrong'
    elif mutation=='time':c['scope']['generated_at']='2026-11-13T00:00:00'
    elif mutation=='authorization':c['scope']['purpose']='EXPAND_OCCURRENCE_APPROVAL'
    elif mutation=='missing_provenance':del c['identities'][0]['evidence_refs']
    with pytest.raises(ValueError):load(tmp_path,c)


def test_owner_export_hash_json_duplicates_and_missing_unknowns(tmp_path):
    p=tmp_path/'source.json';p.write_text('{}')
    with pytest.raises(ValueError,match='SHA-256'):load_owner_reference_export(p,'a'*64)
    p.write_text('{"scope":{},"scope":{}}')
    with pytest.raises(ValueError,match='Duplicate'):load_owner_reference_export(p,hashlib.sha256(p.read_bytes()).hexdigest())
    c=export();c['identities'][0]['evidence_refs']=[];c['identities'][0]['available_observation_roles']=[]
    r=reconcile_catalog_populations([retained()],load(tmp_path,c))[0]
    assert r['current_provenance']=='MISSING' and r['current_role_evidence_status']=='NONE_IN_EXPORT'


def observation(token,**kwargs):
    return PermissionObservation(1,'a'*64,token,'REQUESTED','STATIC_MANIFEST','synthetic',**kwargs)


def identity(token):
    return PermissionIdentity(token,'AOSP_PUBLIC','RETAINED_SOURCE_EXACT','synthetic','b'*64)


@pytest.mark.parametrize('index',range(14,21))
def test_each_new_rule_positive_negative_and_no_observed_behavior(index):
    rule=mobile_attack_permission_mapping_payload()['rules'][index]
    for token in rule['required_any']:
        api=32 if token.endswith('READ_EXTERNAL_STORAGE') else 37
        r=assess_permission_observation(observation(token,api_level=api),identity(token))[0]
        assert r['attack_id']==rule['attack_id'] and not r['technique_observed']
        assert r['behavioral_interpretation']=='POTENTIAL_CAPABILITY'
        o=PermissionObservation(1,'a'*64,token,'DEFINED','STATIC_MANIFEST','synthetic',api_level=api)
        assert all(x['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE' for x in assess_permission_observation(o,identity(token)))


def test_storage_newer_api_requires_target_sdk_review_not_assumed_access():
    token='android.permission.READ_EXTERNAL_STORAGE'
    r=assess_permission_observation(observation(token,api_level=33),identity(token))[0]
    assert r['api_applicability']=='CONTEXT_REVIEW_REQUIRED'
    assert r['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE' and not r['technique_observed']
    p=copy.deepcopy(mobile_attack_permission_mapping_payload())
    rule=next(x for x in p['rules'] if x['attack_id']=='T1533')
    rule['permission_constraints'][token]['api_review_required_from']=True
    with pytest.raises(ValueError):validate_mapping(p)


def test_reviewed_hold_and_no_direct_decisions_are_preserved():
    for short,state in [('VIBRATE','NO_DIRECT_MAPPING'),('READ_PHONE_STATE','PENDING_REVIEW'),('DISABLE_KEYGUARD','NO_DIRECT_MAPPING')]:
        token='android.permission.'+short;r=assess_permission_observation(observation(token),identity(token))[0]
        assert r['disposition']==state and r['assessment_rationale'] and not r['technique_observed']


def test_precise_provider_source_assertion_stays_independent_of_manifest_role():
    token='android.permission.READ_SMS'
    kwargs=dict(source_asserted_role='PROVIDER_REPORTED_REQUIRED_PERMISSION',source_field_path='$.data.attributes.androguard.permission_details',
                role_interpretation_rule='pi-retained-provider-required-v1',source_validation='SOURCE_BOUND',
                source_event_id='synthetic-event',source_payload_digest='b'*64,provenance_refs=('synthetic',))
    o=PermissionObservation(1,'a'*64,token,'UNKNOWN','PROVIDER_REPORT','synthetic',**kwargs)
    r=assess_permission_observation(o,identity(token))[0]
    assert r['source_role_assertion_available'] and not r['source_role_complete']
    assert r['behavioral_interpretation']=='INSUFFICIENT_EVIDENCE' and not r['technique_observed']
    for key in ['source_event_id','source_payload_digest','source_field_path','role_interpretation_rule']:
        bad={**kwargs,key:None}
        with pytest.raises(ValueError):PermissionObservation(1,'a'*64,token,'UNKNOWN','PROVIDER_REPORT','synthetic',**bad).validate()


def test_empty_canonical_interpretation_is_unknown_not_a_conflict(tmp_path):
    c=export();c['identities'][0]['canonical_interpretations']=[]
    r=reconcile_catalog_populations([retained()],load(tmp_path,c))[0]
    assert r['canonical_comparison']=='UNKNOWN'
    c['identities'][0]['evidence_refs']=['']
    with pytest.raises(ValueError):load(tmp_path,c)


def test_unknown_current_identity_is_unresolved_and_does_not_activate_mapping(tmp_path):
    c=export('vendor.permission.NEW');c['identities'][0]['authority_class']='UNKNOWN'
    r=reconcile_catalog_populations([],load(tmp_path,c))[0]
    assert r['mapping_disposition']=='UNRESOLVED' and not r['attack_ids']
    assert r['mapping_assessment_scope']=='UNREVIEWED_CURRENT_IDENTITY'
    p=copy.deepcopy(mobile_attack_permission_mapping_payload())
    p['identity_assessments'].append({'permission':'android.permission.READ_SMS','disposition':'PENDING_REVIEW',
                                    'rationale':'contradict active relationship','reference':'synthetic'})
    with pytest.raises(ValueError):validate_mapping(p)
