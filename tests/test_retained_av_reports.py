import hashlib
import json
import pytest
from obsidiandroid.features.retained_av_reports import prepare_retained_av
from obsidiandroid.features.av_detection_contract import fit_av_detection_contract, transform_av_detection_features


def snapshot():
    members, reports = [], []
    for i in range(1, 4):
        sha = hashlib.sha256(str(i).encode()).hexdigest()
        members.append({'sample_id': i, 'sha256': sha, 'package_group': f'package.{i}',
                        'recorded_family': 'fixture', 'recorded_family_id': 1})
        attrs = {'sha256': sha, 'androguard': {'certificate': {'thumbprint': 'a'*40}},
                 'last_analysis_results': {'fixture_engine': {'category': 'malicious' if i == 1 else 'timeout'}}}
        payload = json.dumps({'data': {'id': sha, 'attributes': attrs}})
        reports.append({'sha256': sha, 'http_status': 200, 'event_id': i,
                        'payload_json': payload, 'payload_hash': hashlib.sha256(payload.encode()).hexdigest()})
    return {'format': 'obsidiandroid-retained-av-development-v1', 'members': members, 'reports': reports}


def test_real_contract_accepts_hash_bound_coherent_payload():
    rows, meta = prepare_retained_av(snapshot())
    assert meta.lineage_component.nunique() == 1  # Different packages share signer.
    contract = fit_av_detection_contract(rows, [1], scope='all_observed')
    features = transform_av_detection_features(rows, contract, [1, 2, 3]).set_index('sample_id')
    assert features.loc[1].sum() == 2 and features.loc[2].sum() == 0
    assert all(c.startswith(('avobs__', 'avdet__')) for c in features)


@pytest.mark.parametrize('mutation', ['hash', 'identity', 'duplicate', 'category'])
def test_rejects_untrusted_or_ambiguous_reports(mutation):
    data = snapshot()
    if mutation == 'hash':
        data['reports'][0]['payload_hash'] = '0'*64
    elif mutation == 'identity':
        data['reports'][0]['sha256'] = '0'*64
    elif mutation == 'duplicate':
        data['reports'][1] = data['reports'][0]
    else:
        report = data['reports'][0]
        payload = json.loads(report['payload_json'])
        payload['data']['attributes']['last_analysis_results']['fixture_engine']['category'] = 'unexpected'
        report['payload_json'] = json.dumps(payload)
        report['payload_hash'] = hashlib.sha256(report['payload_json'].encode()).hexdigest()
    with pytest.raises(ValueError):
        prepare_retained_av(data)


def test_vendor_description_preserves_unavailable_and_unparsed():
    from obsidiandroid.vendors.retained_analysis import describe_retained_vendors
    frame, coverage, consensus = describe_retained_vendors(snapshot())
    assert coverage.loc['fixture_engine', 'timeout'] == 2
    assert coverage.loc['fixture_engine', 'malicious'] == 1
    assert coverage.loc['fixture_engine', 'missing_report'] == 0
    assert frame.known_family.sum() == 0
    assert consensus.known_family_votes.sum() == 0


def test_single_record_descriptive_chunk_is_valid():
    data=snapshot();data['members']=data['members'][:1];data['reports']=data['reports'][:1]
    rows,meta=prepare_retained_av(data)
    assert len(meta)==len(rows)==1
    assert meta.iloc[0].sample_id==1


def test_missing_package_and_public_test_cert_do_not_join_records():
    data=snapshot()
    from obsidiandroid.features.av_lineage import PUBLIC_TEST_CERTIFICATES
    for member,report in zip(data['members'],data['reports']):
        member['package_group']=None
        payload=json.loads(report['payload_json'])
        payload['data']['attributes']['androguard']['certificate']['thumbprint']=next(iter(PUBLIC_TEST_CERTIFICATES))
        report['payload_json']=json.dumps(payload)
        report['payload_hash']=hashlib.sha256(report['payload_json'].encode()).hexdigest()
    _,meta=prepare_retained_av(data)
    assert meta.package.eq('').all()
    assert meta.lineage_component.nunique()==3
