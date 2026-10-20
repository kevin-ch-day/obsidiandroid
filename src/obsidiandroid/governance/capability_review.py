"""Source-definition review only; no mapping activation or Android behavior inference."""
import hashlib
import xml.etree.ElementTree as ET


def review_definition(entry, receipt, manifest_bytes, *, dictionary_release):
    """Verify exact pinned XML attributes and distinguish source and dictionary releases.

    Matching a source does not supply an owner approval, target-SDK applicability,
    API semantics or observed behavior. This function never authorizes a capability.
    """
    if len(manifest_bytes) > 16*1024**2 or b'<!DOCTYPE' in manifest_bytes or b'<!ENTITY' in manifest_bytes:
        raise ValueError('Unsupported or oversized definition source')
    actual = hashlib.sha256(manifest_bytes).hexdigest()
    if actual != entry['source_sha256'] or actual != receipt['sha256']:
        raise ValueError('Definition source hash mismatch')
    if (entry['source_revision'], entry['source_release'], entry['source_url']) != (
            receipt['commit'], receipt['tag'], receipt['source_url']):
        raise ValueError('Definition source identity mismatch')
    android = '{http://schemas.android.com/apk/res/android}'
    matches = [node for node in ET.fromstring(manifest_bytes).iter('permission')
               if node.get(android+'name') == entry['exact_permission']]
    if len(matches) != 1:
        raise ValueError('Exact definition missing or ambiguous')
    attributes = {key.removeprefix(android): value for key, value in matches[0].attrib.items()}
    if attributes != entry['definition_attributes']:
        raise ValueError('Definition attributes mismatch')
    if attributes not in receipt['definitions']:
        raise ValueError('Definition receipt mismatch')
    matches_release = entry['source_release'] == dictionary_release
    return dict(permission=entry['exact_permission'], definition_verified=True,
                source_release=entry['source_release'], dictionary_release=dictionary_release,
                release_match=matches_release,
                disposition='REVIEW_ONLY' if matches_release else 'ABSTAIN_VERSION_MISMATCH',
                governed_capability_authorized=False, training_authorized=False,
                target_applicability='UNVERIFIED', runtime_behavior='NOT_ESTABLISHED')
