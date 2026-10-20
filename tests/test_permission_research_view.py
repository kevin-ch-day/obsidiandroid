"""Offline view integration keeps authority and missing evidence visible."""
import csv
import hashlib
import json
import pytest
from obsidiandroid.reporting.permission_research_view import PermissionResearchView, FORMAT


def packet(tmp_path):
    members=[dict(sample_id=1,sha256='a'*64,family='A',malware_type='spyware',
                  temporal_eligible='True',first_submission_utc='2020-01-01T00:00:00+00:00',
                  last_analysis_utc='2021-01-01T00:00:00+00:00',source_batch_label='',
                  authority_version='frozen',plurality_family='',first_submission_month='2020-01')]
    versions={'classifier':'frozen'}
    rows=[dict(sample_id=1,sha256='a'*64,obs_id=1,exact_token='p',family='A',
               accepted_identity=True,source_correspondence_verified=True,definition_source_present=True,
               canonical_identity='p',protection_base='normal',category='AOSP',evidence_level='CATALOG_ACCEPTED',
               source_match_state='RAW_EXACT',resolution_status='RESOLVED_CURRENT_IDENTITY',
               history={},interpretation={},source=dict(sample_id=1,sha256='a'*64,historical_relationship='LATEST_REPORT_CORRESPONDENCE_ONLY'),version_identity=versions,
               abstentions=['ORIGINAL_HISTORICAL_EVENT_UNBOUND'],capabilities=[])]
    for name,data in [('COHORT_METADATA.csv',members),('OBSERVATION_EVIDENCE.csv',rows),
                      ('LINEAGE_SIGNATURES.csv',[dict(family='A',permission='p',components=1)])]:
        with (tmp_path/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader()
            w.writerows([{k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in data])
    manifest=dict(format=FORMAT,versions=versions,samples=1,observations=1,files={
        n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['COHORT_METADATA.csv','OBSERVATION_EVIDENCE.csv','LINEAGE_SIGNATURES.csv']})
    (tmp_path/'PI_VIEW_MANIFEST.json').write_text(json.dumps(manifest))
    return manifest


def test_integrated_factory_and_family_view(tmp_path):
    from obsidiandroid.reporting.integrated_research import open_research_packet
    packet(tmp_path);v=open_research_packet(tmp_path);r=v.describe('family','A')
    assert r['samples']==r['observations']==1
    assert r['permission_profile'][0]['sample_denominator']==1
    assert r['sources']=={'Unavailable':1}
    assert r['permission_consumer_availability']['original_historical_event_bound']==0
    assert not r['training_authorized'] and not r['production_authorized']
    assert v.describe('sample','a'*64)['samples']==1
    assert v.describe('family','missing')['samples']==0


@pytest.mark.parametrize('case',['hash','symlink','version','denominator','source_identity','original_history','operation'])
def test_view_rejects_invalid_evidence(tmp_path,case):
    m=packet(tmp_path);path=tmp_path/'OBSERVATION_EVIDENCE.csv'
    if case=='hash':path.write_text(path.read_text()+'\n')
    if case=='symlink':
        path.rename(tmp_path/'other.csv');path.symlink_to(tmp_path/'other.csv')
    if case=='version':m['versions']={'classifier':'new'}
    if case=='denominator':m['observations']=2
    if case in {'source_identity','original_history'}:
        with path.open() as f:rows=list(csv.DictReader(f))
        rows[0]['source']=json.dumps(dict(sample_id=1,sha256='b'*64) if case=='source_identity' else dict(sample_id=1,sha256='a'*64,historical_relationship='BOUND_ORIGINAL_EVENT'))
        with path.open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        m['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path/'PI_VIEW_MANIFEST.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):
        v=PermissionResearchView(tmp_path)
        if case=='operation':v.describe('TRAIN')


def test_menu_displays_retained_view_without_live_reader(tmp_path,monkeypatch):
    from obsidiandroid.cli import integrated_research as menu
    packet(tmp_path);choices=iter([1,0]);shown=[]
    monkeypatch.setenv('OBSIDIANDROID_RESEARCH_PACKET',str(tmp_path))
    monkeypatch.setattr(menu.mu,'display_menu',lambda *a,**kw:next(choices))
    monkeypatch.setattr(menu,'show_fields',lambda r:shown.append(r))
    monkeypatch.setattr(menu,'show_rows',lambda r:shown.append(r))
    assert menu.launch_integrated_research()==0
    assert any(isinstance(r,dict) and r.get('mode')=='RETAINED_OFFLINE_ONLY' for r in shown)


def rewrite_csv(root, name, transform):
    path = root / name
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    rows = transform(rows)
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = root / 'PI_VIEW_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


def two_families(root):
    packet(root)
    rewrite_csv(root, 'COHORT_METADATA.csv', lambda rows: rows + [
        dict(rows[0], sample_id='2', sha256='b'*64, family='B')])
    rewrite_csv(root, 'OBSERVATION_EVIDENCE.csv', lambda rows: rows + [dict(
        rows[0], sample_id='2', sha256='b'*64, obs_id='2', family='B',
        accepted_identity='False', canonical_identity='', source_correspondence_verified='False',
        source_match_state='PROJECTION_ONLY', resolution_status='UNRESOLVED',
        source=json.dumps(dict(sample_id=2, sha256='b'*64,
                               historical_relationship='LATEST_REPORT_CORRESPONDENCE_ONLY')))])
    path = root / 'PI_VIEW_MANIFEST.json'
    manifest = json.loads(path.read_text())
    manifest.update(samples=2, observations=2)
    path.write_text(json.dumps(manifest))


def test_permission_query_preserves_zero_family_and_abstention(tmp_path):
    two_families(tmp_path)
    view = PermissionResearchView(tmp_path)
    result = view.describe('permission', 'p')
    assert result['samples'] == 2
    assert [(r['family'], r['samples'], r['sample_denominator'])
            for r in result['permission_comparison']] == [('A', 1, 1), ('B', 0, 1)]
    assert result['permission_totals'][0]['prevalence'] == 0.5
    assert not result['permission_totals'][0]['common_across_selected_families']
    assert result['permission_consumer_availability']['projection_abstentions'] == 1
    assert len(result['permission_evidence']) == 2
    assert view.describe('permission', 'missing')['permission_totals'] == []


def test_type_pooling_does_not_average_family_rates(tmp_path):
    two_families(tmp_path)
    result = PermissionResearchView(tmp_path).describe('type', 'spyware')
    assert result['permission_totals'][0]['sample_denominator'] == 2
    assert result['permission_totals'][0]['samples'] == 1
    assert result['modality_comparison'][0]['missing_av_state_samples'] == 2
    assert result['comparison_readiness']['untouched_evaluation'] == 'NOT_ESTABLISHED'


@pytest.mark.parametrize('field,value', [('sample_id', '01'), ('sample_id', '-1'),
                                        ('sha256', 'A'*64), ('sha256', 'invalid')])
def test_invalid_canonical_sample_binding(tmp_path, field, value):
    packet(tmp_path)
    rewrite_csv(tmp_path, 'COHORT_METADATA.csv', lambda rows: [dict(rows[0], **{field: value})])
    with pytest.raises(ValueError, match='Invalid sample identity'):
        PermissionResearchView(tmp_path)


@pytest.mark.parametrize('source_change', [{'match_state': 'PROJECTION_ONLY'},
                                         {'raw_candidates': ['a different exact token']}])
def test_contradictory_retained_source_correspondence(tmp_path, source_change):
    packet(tmp_path)
    def change(rows):
        source = json.loads(rows[0]['source'])
        source.update(source_change)
        return [dict(rows[0], source=json.dumps(source))]
    rewrite_csv(tmp_path, 'OBSERVATION_EVIDENCE.csv', change)
    with pytest.raises(ValueError):
        PermissionResearchView(tmp_path)



def test_console_pagination_forward_backward_and_exit(monkeypatch):
    from obsidiandroid.cli import integrated_research as menu
    pages = []
    replies = iter(['n', 'p', ''])
    monkeypatch.setattr('builtins.input', lambda _: next(replies))
    monkeypatch.setattr(menu, 'show_rows', lambda rows: pages.append(rows))
    menu.show_paged_rows([{'id': i} for i in range(25)])
    assert [len(p) for p in pages] == [20, 5, 20]
    assert pages[1][0]['id'] == 20


@pytest.mark.parametrize('choice,value', [(5, 'p'), (6, '')])
def test_new_research_menu_routes(tmp_path, monkeypatch, choice, value):
    from obsidiandroid.cli import integrated_research as menu
    packet(tmp_path)
    choices = iter([choice, 0])
    monkeypatch.setenv('OBSIDIANDROID_RESEARCH_PACKET', str(tmp_path))
    monkeypatch.delenv('OBSIDIANDROID_RESEARCH_AV_PACKET', raising=False)
    monkeypatch.setattr(menu.mu, 'display_menu', lambda *a, **kw: next(choices))
    monkeypatch.setattr('builtins.input', lambda _: value)
    shown = []
    monkeypatch.setattr(menu, 'show_fields', lambda row: shown.append(row))
    monkeypatch.setattr(menu, 'show_rows', lambda rows: shown.extend(rows))
    assert menu.launch_integrated_research() == 0
    assert any(row.get('training_authorized') is False for row in shown)


@pytest.mark.parametrize('mismatch', [None, 'sha256', 'event_id', 'payload_hash'])
def test_companion_requires_exact_av_report_binding(tmp_path, mismatch):
    from types import SimpleNamespace
    import pandas as pd
    packet(tmp_path)
    rewrite_csv(tmp_path, 'COHORT_METADATA.csv', lambda rows: [dict(
        rows[0], event_id='7', payload_hash='c'*64)])
    record = dict(sample_id=1, sha256='a'*64, event_id='7', payload_hash='c'*64)
    if mismatch:
        record[mismatch] = 'different'
    companion = SimpleNamespace(samples=pd.DataFrame([record]), root=tmp_path,
                                vendor_claims=lambda _: [{'vendor': 'retained fixture'}])
    view = PermissionResearchView(tmp_path)
    if mismatch:
        with pytest.raises(ValueError, match='binding mismatch'):
            view.bind_av_packet(companion)
    else:
        result = view.bind_av_packet(companion).describe('sample', '1')
        assert result['vendor_claims'] == [{'vendor': 'retained fixture'}]
        assert result['records'][0]['family'] == 'A'


def test_family_disagreement_is_missing_without_vendor_count_evidence(tmp_path):
    packet(tmp_path)
    result = PermissionResearchView(tmp_path).describe('family', 'A')
    assert result['vendor_conflicting_samples'] is None
    assert result['vendor_disagreement_unavailable_samples'] == 1
    rewrite_csv(tmp_path, 'COHORT_METADATA.csv', lambda rows: [dict(rows[0], distinct_known_families='2')])
    result = PermissionResearchView(tmp_path).describe('family', 'A')
    assert result['vendor_conflicting_samples'] == result['vendor_disagreement_evidence_samples'] == 1


@pytest.mark.parametrize('key,value', [('protection_base', 'dangerous'), ('category', 'UNKNOWN')])
def test_retained_interpretation_cannot_contradict_projection(tmp_path, key, value):
    packet(tmp_path)
    rewrite_csv(tmp_path, 'OBSERVATION_EVIDENCE.csv', lambda rows: [
        dict(rows[0], interpretation=json.dumps({key: value}))])
    with pytest.raises(ValueError, match='Contradictory retained classification'):
        PermissionResearchView(tmp_path)
