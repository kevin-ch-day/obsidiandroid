import copy
import hashlib
import pytest
from obsidiandroid.governance.capability_review import review_definition

RAW = b'<manifest xmlns:android="http://schemas.android.com/apk/res/android"><permission android:name="p" android:protectionLevel="normal" /></manifest>'


def fixture():
    attrs = {'name': 'p', 'protectionLevel': 'normal'}
    sha = hashlib.sha256(RAW).hexdigest()
    entry = dict(exact_permission='p', source_sha256=sha, source_revision='commit',
                 source_release='android-15', source_url='retained-fixture', definition_attributes=attrs)
    receipt = dict(sha256=sha, commit='commit', tag='android-15', source_url='retained-fixture', definitions=[attrs])
    return entry, receipt


@pytest.mark.parametrize('release,match', [('android-15', True), ('android-17', False)])
def test_version_match_never_authorizes_activation(release, match):
    result = review_definition(*fixture(), RAW, dictionary_release=release)
    assert result['release_match'] is match
    assert not result['governed_capability_authorized'] and not result['training_authorized']


@pytest.mark.parametrize('case', ['hash', 'commit', 'token', 'protection', 'receipt'])
def test_definition_mismatch_fails(case):
    entry, receipt = copy.deepcopy(fixture())
    if case == 'hash': entry['source_sha256'] = 'x'*64
    if case == 'commit': entry['source_revision'] = 'other'
    if case == 'token': entry['exact_permission'] = 'p.similar'
    if case == 'protection': entry['definition_attributes']['protectionLevel'] = 'dangerous'; receipt['definitions'] = []
    if case == 'receipt': receipt['definitions'] = []
    with pytest.raises(ValueError): review_definition(entry, receipt, RAW, dictionary_release='android-17')
