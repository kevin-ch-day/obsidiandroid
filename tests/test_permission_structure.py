"""Structural profile estimands, missing evidence and normalization checks."""
import math
import pytest
from obsidiandroid.reporting.permission_structure import describe_structure, profile_distance
from obsidiandroid.reporting.research_atlas import ResearchAtlas
from test_research_atlas import fixture


def data():
    members=[]; observations=[]
    for sid,family,component,token,batch,year in [(1,'A','a','p','one','2020'),(2,'A','a','p','one','2020'),
            (3,'A','b','q','two','2021'),(4,'B','c','q','','2020'),(5,'C','','p','only','2021')]:
        members.append(dict(sample_id=str(sid),family=family,lineage_component=component,
                            source_batch_label=batch,first_submission_month=year+'-01',temporal_eligible=True))
        observations.append(dict(sample_id=sid,canonical_identity=token,accepted_identity=True,
                                 source_correspondence_verified=True,resolution_status='RESOLVED'))
    return members,observations


def test_distance_definitions_and_invalid_profiles():
    assert profile_distance([1,0],[0,1])==1
    assert profile_distance([1,2],[2,4])==0
    assert profile_distance([0,0],[1,0]) is None
    for a,b in [([-1,1],[1,0]),([math.nan,1],[1,0]),([1],[1,0])]:
        with pytest.raises(ValueError):profile_distance(a,b)


def test_weighting_contributors_omissions_and_years():
    m,o=data();r=describe_structure(m,o)
    pairs=[x for x in r['structure_pairs'] if x['left']=='A' and x['right']=='B']
    assert pairs[0]['distance']!=pairs[1]['distance']
    omission=next(x for x in r['structure_component_sensitivity'] if x['left']=='A' and x['right']=='B' and x['omitted_family']=='A')
    assert omission['minimum_distance']==0 and omission['maximum_distance']==1
    assert omission['estimable_omissions']==2
    terms=[x['js_divergence_contribution'] for x in r['structure_contributions'] if x['left']=='A' and x['right']=='B']
    assert sum(terms)==pytest.approx(pairs[0]['distance']**2)
    assert any(x['distance'] is None for x in r['structure_source_sensitivity'] if x['omitted_family']=='C')
    assert all(x['omitted_family']!='B' for x in r['structure_source_sensitivity'])
    assert r['structure_temporal'][0]['distance']==1
    assert not r['structure_temporal'][0]['min5_samples_each']
    assert all(x['distance'] is None for x in r['structure_pairs'] if x['right']=='C' and x['weighting']=='equal_component')


def test_abstention_duplicate_positive_missing_year_and_bounds():
    m,o=data();o.append(dict(o[0]));o.append(dict(o[0],canonical_identity='projection',source_correspondence_verified=False))
    m[0]['temporal_eligible']=False
    r=describe_structure(m,o)
    assert r['accepted_permission_identities']==2 and r['projection_abstentions']==1
    p=next(x for x in r['structure_profiles'] if x['family']=='A' and x['permission']=='p' and x['weighting']=='sample')
    assert p['positive_samples']==2 and p['observed_frequency']==pytest.approx(2/3)
    assert r['structure_coverage'][0]['missing_period_samples']==1
    with pytest.raises(ValueError):describe_structure(m+[m[0]],o)
    with pytest.raises(ValueError):describe_structure(m,o+[dict(o[0],sample_id=999)])
    with pytest.raises(ValueError):describe_structure(m,[])


def test_existing_atlas_and_console_without_vendor_policy(tmp_path,monkeypatch):
    from obsidiandroid.cli import integrated_research as ui
    a=ResearchAtlas(fixture(tmp_path));r=a.describe('structure')
    assert r['samples']==2 and r['projection_abstentions']==1
    assert r['structure_pairs'][0]['distance'] is None
    assert not r['training_authorized'] and not r['production_authorized']
    choices=iter([10,0]);seen=[]
    monkeypatch.setattr(ui.mu,'display_menu',lambda *args,**kwargs:next(choices))
    monkeypatch.setattr('builtins.input',lambda *args:'')
    monkeypatch.setattr(ui,'show_fields',lambda x:seen.append(x))
    monkeypatch.setattr(ui,'show_rows',lambda x:seen.extend(x))
    assert ui.launch_integrated_research(consumer=a)==0
    assert any('structure_method' in x for x in seen)


def test_temporal_gaps_shared_components_report_time():
    m,o=data();m[2]['first_submission_month']='2023-01';m[2]['lineage_component']='a'
    m[0]['fetched_at_utc']='2026-01-01 00:00:00'
    r=describe_structure(m,o)['structure_temporal'][0]
    assert r['year_gap']==3 and r['shared_inferred_components']==1
    assert r['earlier_support']['retained_report_timing']['fetched_at_utc']['missing_samples']==1
    assert r['earlier_support']['supported_acquisition_origins'] is None
