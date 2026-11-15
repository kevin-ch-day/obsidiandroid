"""Offline, byte-pinned MITRE ATT&CK Mobile v20.1 reference validation."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from obsidiandroid.common.repo_paths import repo_root

RELEASE = 'v20.1'
COMMIT = 'f59b03ecf828579d5f9e93683ce25b7e2e5fd9d7'
SHA256 = '632e2ec40848394f9873a7a3485fc32f92b861a4e7271f7e88e0cb02f11bb6af'
ARTIFACT = Path('config/taxonomy/mitre/mobile-attack-v20.1.json')
SOURCE_URL = 'https://github.com/mitre-attack/attack-stix-data/releases/download/v20.1/mobile-attack.json'


@dataclass(frozen=True)
class Technique:
    attack_id: str
    stix_id: str
    name: str
    tactics: tuple[str, ...]
    platforms: tuple[str, ...]
    version: str
    modified: str
    revoked: bool
    deprecated: bool
    subtechnique: bool


class MobileAttackReference:
    """Immutable reference index; no dynamic version or network fallback."""

    def __init__(self, payload: bytes):
        if hashlib.sha256(payload).hexdigest() != SHA256:
            raise ValueError('Pinned ATT&CK artifact SHA-256 mismatch')
        bundle = json.loads(payload)
        if bundle.get('type') != 'bundle':
            raise ValueError('ATT&CK source is not a STIX bundle')
        techniques = {}
        for obj in bundle['objects']:
            if obj.get('spec_version') != '2.1':
                raise ValueError('ATT&CK source requires STIX2.1 objects')
            if obj['type'] != 'attack-pattern':
                continue
            for ref in obj.get('external_references', []):
                if ref.get('source_name') != 'mitre-attack' or not ref.get('external_id'):
                    continue
                attack_id = ref['external_id']
                if attack_id in techniques:
                    raise ValueError('Ambiguous ATT&CK technique ID')
                techniques[attack_id] = Technique(
                    attack_id, obj['id'], obj['name'],
                    tuple(sorted(p['phase_name'] for p in obj.get('kill_chain_phases', [])
                                 if p['kill_chain_name'] == 'mitre-mobile-attack')),
                    tuple(obj.get('x_mitre_platforms', [])), obj.get('x_mitre_version', ''),
                    obj['modified'], bool(obj.get('revoked', False)),
                    bool(obj.get('x_mitre_deprecated', False)),
                    bool(obj.get('x_mitre_is_subtechnique', False)),
                )
        self.techniques = MappingProxyType(techniques)
        self.bundle_id = bundle['id']

    def technique(self, attack_id: str, *, active: bool = True) -> Technique:
        """Resolve an ID and reject obsolete/non-Android mappings by default."""
        if attack_id not in self.techniques:
            raise ValueError(f'Missing ATT&CK Mobile technique: {attack_id}')
        result = self.techniques[attack_id]
        if active and (result.revoked or result.deprecated):
            raise ValueError(f'Obsolete ATT&CK technique: {attack_id}')
        if active and 'Android' not in result.platforms:
            raise ValueError(f'Technique does not support Android: {attack_id}')
        return result


@lru_cache(maxsize=2)
def _verified_index(payload: bytes) -> MobileAttackReference:
    return MobileAttackReference(payload)


def load_mobile_attack_reference(path: Path | None = None) -> MobileAttackReference:
    """Recheck actual bytes on every call, even when parsing is cached."""
    payload = (path or repo_root()/ARTIFACT).read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError('Pinned ATT&CK artifact SHA-256 mismatch')
    return _verified_index(payload)
