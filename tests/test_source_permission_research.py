import hashlib
import json
import pandas as pd
import pytest
from obsidiandroid.reporting.integrated_research import open_research_packet
from obsidiandroid.reporting.source_permission_research import FORMAT
from obsidiandroid.vendors.alias_sensitivity import alias_sensitivity


def fixture_packet(root, mutate=None):
    version = dict(catalog_release_id='fixture-v1', catalog_digest='d'*64)
    frames = {
        'samples': pd.DataFrame([dict(sample_id=i, sha256=str(i)*64, family_label='F', classification_primary='T', source_batch_label='B') for i in [1, 2, 3]]),
        'tokens': pd.DataFrame([dict(sample_id=1, sha256='1'*64, event_id=10, payload_hash='a'*64, exact_provider_token=t, current_accepted_exact_identity=t=='android.permission.INTERNET') for t in ['android.permission.INTERNET', 'android.permission.internet', ' com.é.Mixed ']]),
        'bindings': pd.DataFrame([dict(sample_id=1, sha256_retained='1'*64, event_id=10, payload_hash_retained='a'*64)]),
        'dictionary': pd.DataFrame([dict(**version, identity_status='ACCEPTED', canonical_permission='android.permission.INTERNET')]),
        'stored': pd.DataFrame([dict(sample_id=1, permission_string='android.permission.internet')]),
        'authority': pd.DataFrame([dict(permission_string='android.permission.INTERNET', is_current_best=1, protection_level='normal')]),
    }
    if mutate:
        mutate(frames)
    manifest = dict(format=FORMAT, dictionary=version, inputs={})
    for key, frame in frames.items():
        path = root / (key+'.csv')
        frame.to_csv(path, index=False)
        raw = path.read_bytes()
        manifest['inputs'][key] = dict(path=path.name, bytes=len(raw), decoded_bytes=len(raw), rows=len(frame), sha256=hashlib.sha256(raw).hexdigest())
    (root/'SOURCE_PERMISSION_MANIFEST.json').write_text(json.dumps(manifest))
    return open_research_packet(root)


def test_real_consumer_keeps_exact_source_history_and_missingness(tmp_path):
    view = fixture_packet(tmp_path)
    profile = view.describe('sample', '1')
    assert profile['accepted_count'] == 1
    rows = {r['exact_provider_token']: r for r in profile['records']}
    upper = rows['android.permission.INTERNET']
    assert upper['correspondence'] == 'CASEFOLD_ONLY'
    assert upper['historical_relationship'] == 'LATEST_REPORT_CORRESPONDENCE_ONLY'
    assert upper['original_observation_event_id'] is None
    assert rows['android.permission.internet']['canonical_identity'] is None
    assert rows[' com.é.Mixed ']['canonical_identity'] is None
    assert view.describe('sample', '2')['accepted_count'] is None
    frequency = view.describe('permission', 'android.permission.INTERNET')['permission_totals'][0]
    assert (frequency['positive'], frequency['sample_denominator'], frequency['unavailable_samples']) == (1, 1, 2)
    matrix = view.feature_matrix(['android.permission.INTERNET'])
    assert matrix.loc[1].iloc[0]
    assert pd.isna(matrix.loc[2].iloc[0])
    assert view.similarity(1, 2) is None
    assert view.stored[1] == {'android.permission.internet'}
    unknown = view.prevalence(permission='android.permission.internet')[0]
    assert unknown['positive'] is None and unknown['exact_source_positive'] == 1
    with pytest.raises(ValueError, match='accepted canonical'):
        view.feature_matrix(['android.permission.internet'])
    assert view.cooccurrence('android.permission.INTERNET', 'android.permission.INTERNET')[0]['both'] == 1


@pytest.mark.parametrize('field,value', [('sha256', 'f'*64), ('event_id', 11), ('payload_hash', 'b'*64), ('current_accepted_exact_identity', False)])
def test_contradictory_source_binding_fails(tmp_path, field, value):
    with pytest.raises(ValueError):
        fixture_packet(tmp_path, lambda frames: frames['tokens'].loc.__setitem__((0, field), value))


def test_duplicate_source_membership_requires_selection(tmp_path):
    def mutate(frames):
        frames['tokens'] = pd.concat([frames['tokens'], frames['tokens'].iloc[:1]])
    with pytest.raises(ValueError, match='explicit report selection'):
        fixture_packet(tmp_path, mutate)


def test_changed_input_and_dictionary_versions_fail(tmp_path):
    fixture_packet(tmp_path)
    path = tmp_path/'stored.csv'
    path.write_text(path.read_text().replace('internet', 'INTERNET'))
    with pytest.raises(ValueError, match='digest'):
        open_research_packet(tmp_path)
    fixture_packet(tmp_path)
    path = tmp_path/'SOURCE_PERMISSION_MANIFEST.json'
    doc = json.loads(path.read_text()); doc['dictionary']['catalog_digest'] = 'e'*64
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='Dictionary'):
        open_research_packet(tmp_path)


def test_alias_sensitivity_preserves_ties_raw_labels_and_unavailable():
    rows = [dict(sample_id=1, engine='A', raw_label='Trojan.Hqwar.x', active_family='trickmo', active_recognized=True),
            dict(sample_id=1, engine='B', raw_label='TrickMo', active_family='trickmo', active_recognized=True),
            dict(sample_id=2, engine='A', raw_label='SpyMax', active_family='spynote', active_recognized=True),
            dict(sample_id=3, engine='A', raw_label='', active_family='', active_recognized=False)]
    evidence, result = alias_sensitivity(pd.DataFrame(rows), [1, 2, 3, 4])
    assert evidence.raw_label.tolist() == [r['raw_label'] for r in rows]
    assert evidence.iloc[0].alias_rule == 'hqwar -> trickmo'
    selected = result.set_index(['scenario', 'sample_id'])
    assert selected.loc[('current', 1), 'families'] == 1
    assert selected.loc[('disputed_distinct', 1), 'tie']
    assert selected.loc[('disputed_distinct', 1), 'dominant_unique'] == ''
    assert selected.loc[('both_unresolved', 2), 'votes'] == 0
    assert selected.loc[('current', 4), 'votes'] == 0


def test_numeric_sha_lookup(tmp_path):
    assert fixture_packet(tmp_path).describe('sample', '1'*64)['sample_id'] == 1


def test_unresolved_cooccurrence_abstains(tmp_path):
    view = fixture_packet(tmp_path)
    with pytest.raises(ValueError, match='accepted canonical'):
        view.cooccurrence('android.permission.internet', 'android.permission.INTERNET')


def test_matrix_accepts_generator_and_rejects_duplicates(tmp_path):
    view = fixture_packet(tmp_path)
    permission = 'android.permission.INTERNET'
    assert list(view.feature_matrix(iter([permission])).columns) == [permission]
    with pytest.raises(ValueError, match='Duplicate'):
        view.feature_matrix([permission, permission])


def test_scoped_availability(tmp_path):
    def mutate(frames):
        frames['samples'].loc[0, 'family_label'] = 'Covered'
    view = fixture_packet(tmp_path, mutate)
    for kind, value in [('family', 'Covered'), ('sample', '1')]:
        counts = view.describe(kind, value)['permission_consumer_availability']
        assert counts['selected_samples'] == 1
        assert counts['source_covered_samples'] == 1
        assert counts['unavailable_samples'] == 0
    missing = view.describe('family', 'F')['permission_consumer_availability']
    assert missing['selected_samples'] == missing['unavailable_samples'] == 2
