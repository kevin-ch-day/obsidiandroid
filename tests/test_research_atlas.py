"""Small retained fixtures exercise atlas joins and distinct denominators offline."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from test_permission_research_view import two_families, rewrite_csv
from obsidiandroid.reporting.research_atlas import ResearchAtlas, FORMAT
from obsidiandroid.reporting.integrated_research import open_research_packet


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path):
    pi=tmp_path/'pi'; pi.mkdir(); two_families(pi)
    rewrite_csv(pi,'COHORT_METADATA.csv',lambda rows:[dict(r,event_id=str(i+10),payload_hash=str(i)*64) for i,r in enumerate(rows,1)])
    av=tmp_path/'av'; av.mkdir()
    samples=pd.DataFrame([dict(sample_id=i,sha256=c*64,event_id=i+10,payload_hash=str(i)*64,
        recorded_family=f,malware_type='spyware',source_batch_label='',temporal_eligible=True,
        first_submission_month='2020-01',permission_covered=False) for i,c,f in [(1,'a','A'),(2,'b','B'),(3,'c','C')]])
    samples.to_csv(av/'SAMPLES.csv',index=False)
    pd.DataFrame(columns=['sample_id','sha256','token']).to_csv(av/'PERMISSIONS.csv',index=False)
    rows=pd.DataFrame([dict(sample_id=i,engine=e,category=cat,raw_label=label,family=f,known_family=known,
        parser_quality='unavailable',parser_error='') for i,e,cat,label,f,known in [
        (1,'Engine-X','malicious','Trojan.A','A',True),(1,'Second','timeout','','unknown',False),
        (2,'Engine-X','undetected','','unknown',False),(3,'Second','type_unsupported','','unknown',False)]])
    shard=av/'vendors.csv.gz';rows.to_csv(shard,index=False,compression='gzip')
    m={'format':'obsidiandroid-integrated-research-v1','files':{n:digest(av/n) for n in ['SAMPLES.csv','PERMISSIONS.csv']},
       'vendor_shards':{str(i):{'path':str(shard),'sha256':digest(shard)} for i in [1,2,3]}}
    (av/'RESEARCH_MANIFEST.json').write_text(json.dumps(m))
    config={'format':FORMAT,'av':{'path':str(av),'sha256':digest(av/'RESEARCH_MANIFEST.json')},
            'pi':{'path':str(pi),'sha256':digest(pi/'PI_VIEW_MANIFEST.json')}}
    (tmp_path/'ATLAS_MANIFEST.json').write_text(json.dumps(config))
    return tmp_path


def refresh(root):
    av=root/'av';m=json.loads((av/'RESEARCH_MANIFEST.json').read_text())
    for n in m['files']:m['files'][n]=digest(av/n)
    for entry in m['vendor_shards'].values():entry['sha256']=digest(Path(entry['path']))
    (av/'RESEARCH_MANIFEST.json').write_text(json.dumps(m))
    c=json.loads((root/'ATLAS_MANIFEST.json').read_text());c['av']['sha256']=digest(av/'RESEARCH_MANIFEST.json')
    (root/'ATLAS_MANIFEST.json').write_text(json.dumps(c))


def test_atlas_populations_engine_missingness_and_abstention(tmp_path):
    a=open_research_packet(fixture(tmp_path));r=a.describe()
    assert r['samples']==3 and r['verdicts']==4
    assert r['pi_population']['samples']==2 and r['pi_population']['projection_abstentions']==1
    assert r['complete_global_engine_universe_samples']==1
    source = next(x for x in r['av_strata'] if x['dimension']=='source_batch_label')
    assert source['stratum']=='UNAVAILABLE' and source['samples']==3
    assert source['categories']['timeout']==1 and source['detected_samples']==1
    e=a.describe('engine','engine_x')
    assert e['samples']==3 and e['retained_report_samples']==2 and e['verdicts']==2
    assert e['engine_coverage'][0]['missing_engine_samples']==1
    assert {r['category']:r['verdicts'] for r in e['category_counts']}=={'malicious':1,'undetected':1}
    assert a.describe('engine','missing')['verdicts']==0
    assert a.describe('family','C')['pi_population']['samples']==0
    assert a.describe('sample','3')['raw_source']['state']=='UNAVAILABLE'
    assert a.describe('family','missing')['samples']==0


def test_permission_zeroes_type_balancing_and_exact_overlap(tmp_path):
    a=ResearchAtlas(fixture(tmp_path));r=a.describe('permission','p')
    assert [(x['family'],x['samples']) for x in r['permission_comparison']]==[('A',1),('B',0)]
    t=a.describe('type','spyware')
    assert t['samples']==3 and t['pi_population']['samples']==2
    assert t['permission_totals'][0]['sample_denominator']==2
    assert t['permission_totals'][0]['equal_family_prevalence']==.5
    assert a.describe('overlap')['samples']==2
    assert not r['training_authorized']


@pytest.mark.parametrize('case',['sha','report','duplicate','category','membership','hash','format'])
def test_atlas_rejects_bad_bindings_and_verdicts(tmp_path,case):
    root=fixture(tmp_path);av=root/'av'
    if case in {'sha','report'}:
        s=pd.read_csv(av/'SAMPLES.csv',keep_default_na=False,dtype={'payload_hash':str})
        s.loc[0,'sha256' if case=='sha' else 'event_id']='d'*64 if case=='sha' else 99
        s.to_csv(av/'SAMPLES.csv',index=False);refresh(root)
    elif case in {'duplicate','category','membership'}:
        s=pd.read_csv(av/'vendors.csv.gz',keep_default_na=False)
        if case=='duplicate':s=pd.concat([s,s.iloc[:1]])
        if case=='category':s.loc[0,'category']='negative'
        if case=='membership':s.loc[0,'sample_id']=9
        s.to_csv(av/'vendors.csv.gz',index=False,compression='gzip');refresh(root)
    elif case=='hash':(av/'vendors.csv.gz').write_bytes(b'changed')
    else:
        p=root/'ATLAS_MANIFEST.json';c=json.loads(p.read_text());c['format']='production';p.write_text(json.dumps(c))
    with pytest.raises(ValueError):ResearchAtlas(root).describe()


def test_existing_console_engine_navigation_and_paging(tmp_path,monkeypatch):
    from obsidiandroid.cli import integrated_research as ui
    a=ResearchAtlas(fixture(tmp_path)); choices=iter([7,0]);seen=[]
    monkeypatch.setattr(ui.mu,'display_menu',lambda *a,**k:next(choices))
    monkeypatch.setattr('builtins.input',lambda *a:'Engine-X')
    monkeypatch.setattr(ui,'show_fields',lambda x:seen.append(x))
    monkeypatch.setattr(ui,'show_rows',lambda x:seen.extend(x))
    assert ui.launch_integrated_research(consumer=a)==0
    assert any(r.get('missing_engine_samples')==1 for r in seen)
    seen.clear();inputs=iter(['n','p',''])
    monkeypatch.setattr('builtins.input',lambda *a:next(inputs))
    ui.show_paged_rows([{'id':i} for i in range(5)],page_size=2)
    assert [r['id'] for r in seen]==[0,1,2,3,0,1]


def raw_fixture(root, *, mismatch=False):
    import gzip
    source=root/'source';source.mkdir()
    av=root/'av'; samples=pd.read_csv(av/'SAMPLES.csv',keep_default_na=False,dtype={'payload_hash':str})
    parsed=pd.read_csv(av/'vendors.csv.gz',keep_default_na=False)
    reports=[];members=[];hashes={}
    for s in samples.to_dict('records'):
        engines={r['engine']:dict(category=r['category'],result=r['raw_label'] or None,
                                 engine_version='1.0',engine_update='20200101')
                 for r in parsed[parsed.sample_id.eq(s['sample_id'])].to_dict('records')}
        if mismatch and s['sample_id']==1:engines['Engine-X']['result']='Different'
        payload=json.dumps({'data':{'id':s['sha256'],'attributes':{'sha256':s['sha256'],'last_analysis_results':engines}}})
        h=hashlib.sha256(payload.encode()).hexdigest();hashes[s['sample_id']]=h
        reports.append(dict(sha256=s['sha256'],event_id=s['event_id'],payload_hash=h,payload_json=payload))
        members.append(dict(sample_id=s['sample_id'],sha256=s['sha256']))
    samples['payload_hash']=samples.sample_id.map(hashes);samples.to_csv(av/'SAMPLES.csv',index=False)
    rewrite_csv(root/'pi','COHORT_METADATA.csv',lambda rows:[dict(r,payload_hash=hashes[int(r['sample_id'])]) for r in rows])
    raw=json.dumps(dict(members=members,reports=reports)).encode();(source/'chunk.gz').write_bytes(gzip.compress(raw))
    (source/'SOURCE_MANIFEST.json').write_text(json.dumps({'chunks':[dict(path='chunk.gz',sha256=digest(source/'chunk.gz'),json_bytes=len(raw))]}))
    m=json.loads((av/'RESEARCH_MANIFEST.json').read_text());m['source_manifest_sha256']=digest(source/'SOURCE_MANIFEST.json');(av/'RESEARCH_MANIFEST.json').write_text(json.dumps(m));refresh(root)
    p=root/'ATLAS_MANIFEST.json';c=json.loads(p.read_text());c['source']=dict(path=str(source),sha256=digest(source/'SOURCE_MANIFEST.json'));c['pi']['sha256']=digest(root/'pi/PI_VIEW_MANIFEST.json');p.write_text(json.dumps(c))


@pytest.mark.parametrize('mismatch',[False,True])
def test_raw_versions_and_exact_verdict_correspondence(tmp_path,mismatch):
    fixture(tmp_path);raw_fixture(tmp_path,mismatch=mismatch);a=ResearchAtlas(tmp_path)
    if mismatch:
        with pytest.raises(ValueError,match='verdict source'):a.describe('sample','1')
    else:
        r=a.describe('sample','1')
        assert r['raw_source']['state']=='EXACT_RETAINED_REPORT'
        assert r['raw_source']['engines'][0]['engine_version']=='1.0'
        assert r['pi_population']['samples']==1


def test_coverage_identity_mismatch_rejected(tmp_path):
    fixture(tmp_path);p=tmp_path/'coverage.csv'
    pd.DataFrame({'sample_id':[1],'sha256':['a'*64]}).to_csv(p,index=False)
    m=tmp_path/'ATLAS_MANIFEST.json';d=json.loads(m.read_text());d['coverage']=dict(path=str(p),sha256=digest(p),observed_utc='2020-01-01T00:00:00Z');m.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='Coverage audit identity'):ResearchAtlas(tmp_path)
