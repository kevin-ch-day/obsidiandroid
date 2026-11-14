"""Versioned analytical permission relationships consuming PI identity authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import yaml

from obsidiandroid.common.repo_paths import repo_root
from .mobile_attack_reference import RELEASE, COMMIT, SHA256, load_mobile_attack_reference

MAPPING_ARTIFACT_PATH = Path('config/taxonomy/mobile_attack_permission_mapping.yaml')
MAPPING_HANDLE = 'mobile_attack_permission_mapping.rules'
SCHEMA_VERSION = 'permission-attack-relationships-v2'
DISPOSITIONS = frozenset({'CAPABILITY_RELATED', 'CONTEXT_REQUIRED', 'NO_DIRECT_MAPPING',
                          'UNRESOLVED', 'NOT_VALID_PERMISSION', 'PENDING_REVIEW'})
ROLES = frozenset({'REQUESTED', 'DEFINED', 'COMPONENT_GUARD', 'UNKNOWN', 'RUNTIME_GRANT', 'API_BEHAVIOR'})


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _artifact_path() -> Path:
    return repo_root()/MAPPING_ARTIFACT_PATH


def validate_mapping(payload: dict, reference=None) -> dict:
    """Fail closed on incorrect versions, tactics, source objects or semantics."""
    reference = reference or load_mobile_attack_reference()
    if payload.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported mapping schema; legacy bootstrap is archived, not active')
    source = payload.get('attack_source', {})
    if (source.get('release'), source.get('commit'), source.get('sha256')) != (RELEASE, COMMIT, SHA256):
        raise ValueError('ATT&CK source version/commit/hash mismatch')
    rules = payload.get('rules')
    if not isinstance(rules, list) or not rules:
        raise ValueError('Mapping rules must be a nonempty list')
    ids, edges = set(), set()
    for rule in rules:
        if 'confidence' in rule:
            raise ValueError('A single confidence field cannot represent evidence semantics')
        if not rule.get('rule_id') or rule['rule_id'] in ids:
            raise ValueError('Missing or duplicate rule ID')
        ids.add(rule['rule_id'])
        technique = reference.technique(rule.get('attack_id', ''))
        if rule.get('stix_id') != technique.stix_id or rule.get('attack_name') != technique.name:
            raise ValueError('ATT&CK source-object/name mismatch')
        if (rule.get('technique_version'), rule.get('technique_modified')) != (technique.version, technique.modified):
            raise ValueError('ATT&CK source-object version/modified mismatch')
        if sorted(rule.get('tactics', [])) != list(technique.tactics):
            raise ValueError('Incorrect or incomplete ATT&CK tactic relationships')
        if rule.get('relationship_category') not in {'CAPABILITY_RELATED','CONTEXT_REQUIRED'}:
            raise ValueError('Invalid relationship category')
        if rule.get('behavioral_assertion') is not False:
            raise ValueError('Permission rules must not assert observed adversary behavior')
        if not rule.get('observed_behavior_requires') or not rule.get('android_reference') or not rule.get('rationale'):
            raise ValueError('Evidence prerequisites and technical references required')
        perms = rule.get('required_any', [])
        if not perms or len(perms)!=len(set(perms)) or any(not isinstance(p,str) or p!=p.strip() for p in perms):
            raise ValueError('Invalid or duplicate exact permission identities')
        roles = rule.get('allowed_roles', [])
        if not roles or len(roles)!=len(set(roles)) or not set(roles)<=ROLES-{'UNKNOWN','DEFINED'}:
            raise ValueError('Invalid permission roles for capability mapping')
        if not isinstance(rule.get('required_count'),int) or not 1<=rule['required_count']<=len(perms):
            raise ValueError('Invalid required permission count')
        if not 0<=rule.get('min_prevalence',-1)<=1:
            raise ValueError('Invalid prevalence threshold')
        for token in perms:
            edge=(token,technique.attack_id,tuple(sorted(roles)))
            if edge in edges:raise ValueError('Duplicate permission-technique-role edge')
            edges.add(edge)
            constraint=rule.get('permission_constraints',{}).get(token,{})
            if not constraint.get('reference') or constraint.get('api_min') is not None and (type(constraint['api_min']) is not int or constraint['api_min']<1):
                raise ValueError('Permission API/source constraint invalid')
            boundary=constraint.get('api_review_required_from')
            if boundary is not None and (type(boundary) is not int or boundary<1 or not constraint.get('applicability_notes')):
                raise ValueError('API review boundary requires an explicit positive level and applicability notes')
    decisions={}
    related={p for r in rules for p in r['required_any']}
    for item in payload.get('identity_assessments',[]):
        token=item.get('permission');state=item.get('disposition')
        if not token or token in decisions or state not in DISPOSITIONS or not item.get('rationale') or not item.get('reference'):
            raise ValueError('Duplicate, unsupported or undocumented mapping disposition')
        if token in related and state in {'NO_DIRECT_MAPPING','NOT_VALID_PERMISSION','PENDING_REVIEW','UNRESOLVED'}:
            raise ValueError('Contradictory mapping dispositions')
        decisions[token]=state
    return payload


def load_mobile_attack_permission_mapping() -> dict[str, Any]:
    """Validate the active analytical contract against pinned official bytes."""
    payload=yaml.safe_load(_artifact_path().read_text(encoding='utf-8'))
    if not isinstance(payload,dict):raise ValueError('Mapping artifact must be a mapping')
    return validate_mapping(payload)


def mobile_attack_permission_mapping_payload() -> dict[str, Any]:
    """Return a provenance-bound contract without a behavior-confidence score."""
    payload=load_mobile_attack_permission_mapping()
    payload['artifact_path']=MAPPING_ARTIFACT_PATH.as_posix()
    payload['handle']=MAPPING_HANDLE
    payload['rule_count']=len(payload['rules'])
    payload['hash']=_stable_hash(payload)
    return payload
