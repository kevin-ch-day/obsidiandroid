"""Versioned conservative retained-evidence grouping without placeholder edges.

Exact TLSH/ssdeep matches remain conservative constraints, not proof of
independent or identical APKs. Vhash alone is only structural-similarity evidence. Known public build
certificates cannot identify authors. Package/signer edges constrain splits;
they do not establish common origin.
"""

LINEAGE_POLICY_ID = 'retained_lineage_v4_known_public_aosp_signers'
# Public certificate identity independently reproduced from AOSP's immutable file:
# https://android.googlesource.com/platform/build/+/695b28f/target/product/security/testkey.x509.pem
# DER SHA-256 a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc
# The same pinned AOSP tree publishes platform.x509.pem as a public build key.
# Its DER SHA-256 is c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8.
# Public platform/test keys cannot independently identify an APK's author.
PUBLIC_TEST_CERTIFICATES = frozenset({
    '61ed377e85d386a8dfee6b864bd85b0bfaa5af81',
    '27196e386b875e76adf700e7ea84e4c6eee33dfa',
})
_MISSING = frozenset({'', 'none', 'null', 'nan', 'n/a', 'unknown', 'tnull'})


def identifier(value):
    """Reject absent/placeholder metadata; never stringify None into an identity."""
    if not isinstance(value, str):
        return ''
    text = value.strip()
    return '' if text.lower() in _MISSING else text


def lineage_components(records):
    """Union retained relationships while excluding non-identifying evidence.

    Public test certificate metadata remains available, but cannot independently
    link APKs. Matching packages and other nonempty identifiers still link them.
    Signers outside the known-public set remain conservative constraints even
    when widely shared; exclusion-list absence does not prove private ownership.
    Vhash-only edges are retained by audit callers but never assert lineage;
    corroborating package, signer or exact fuzzy-hash matches still link samples.
    """
    ids = [r['sample_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate global sample identity')
    parent = {sid: sid for sid in ids}
    tokens = {}
    def root(sid):
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid
    for row in records:
        for key in ('package', 'signer_sha1', 'tlsh', 'ssdeep'):
            value = identifier(row.get(key))
            if key in {'package', 'signer_sha1'}:
                value = value.lower()
            if not value or (key == 'signer_sha1' and value in PUBLIC_TEST_CERTIFICATES):
                continue
            token = key, value
            if token in tokens:
                a,b = root(row['sample_id']),root(tokens[token])
                parent[max(a,b)] = min(a,b)
            else:
                tokens[token] = row['sample_id']
    return {sid:root(sid) for sid in ids}
