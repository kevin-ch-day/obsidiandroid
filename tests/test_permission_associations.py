"""Composition, missingness and evidence boundaries of descriptive contrasts."""
import json
import pandas as pd
import pytest
from obsidiandroid.reporting.permission_associations import compare_permission
from obsidiandroid.reporting.research_atlas import ResearchAtlas
from obsidiandroid.vendors.interpretation_quality import source_identity
from test_research_atlas import fixture


def data():
    members=[]; rows=[]; vendors=[]
    # Simpson reversal: pooled conflict 8/11 vs nonconflict 3/11;
    # within each family conflict is lower (8/10 vs 1/1; 0/1 vs 2/10).
    for family, state, n, positives in [('A',True,10,8),('A',False,1,1),('B',True,1,0),('B',False,10,2)]:
        for i in range(n):
            sid=len(members)+1
            members.append(dict(sample_id=str(sid),sha256=str(sid),family=family,event_id=sid,
                                payload_hash='hash',source_batch_label='',temporal_eligible=False))
            if i < positives:
                rows.append(dict(sample_id=sid,canonical_identity='p',accepted_identity=True,
                                 source_correspondence_verified=True,resolution_status='RESOLVED'))
            for claim in (['a','b'] if state else ['a']):
                vendors.append(dict(sample_id=sid,active_recognized=True,active_family=claim,category='malicious'))
    return members, rows, pd.DataFrame(vendors)


def test_composition_reversal_and_missing_common_support():
    r=compare_permission(*data(),'p')
    contrasts=[c for c in r['association_contrasts'] if c['left']=='conflicting' and c['right']=='recognized_nonconflicting']
    assert contrasts[0]['difference']==pytest.approx(5/11)
    assert contrasts[1]['difference']==pytest.approx(-.2)
    assert contrasts[1]['left_included']==11
    assert contrasts[1]['minimum_cell_samples']==1
    assert contrasts[1]['min5_difference'] is None
    assert contrasts[2]['difference'] is None and contrasts[2]['left_excluded']==11
    assert contrasts[3]['shared_strata']==0
    assert any(x['sample_denominator']==0 and x['frequency'] is None for x in r['association_strata'])


def test_abstention_unknown_identity_and_missing_av():
    m,o,v=data();o.append(dict(sample_id=1,canonical_identity='q',accepted_identity=True,
                             source_correspondence_verified=False,resolution_status='UNRESOLVED'))
    with pytest.raises(ValueError): compare_permission(m,o,v,'q')
    r=compare_permission(m,o,v,'p');assert r['projection_abstentions']==1
    assert r['association_samples'][0]['unresolved_evidence']
    with pytest.raises(ValueError): compare_permission(m,o,v[v.sample_id.ne(1)],'p')
    with pytest.raises(ValueError): compare_permission(m+[m[0]],o,v,'p')


def test_atlas_console_and_version_gate(tmp_path,monkeypatch):
    from obsidiandroid.cli import integrated_research as ui
    root=fixture(tmp_path)
    with pytest.raises(ValueError): ResearchAtlas(root).describe('association','p')
    p=root/'ATLAS_MANIFEST.json';m=json.loads(p.read_text());m['vendor_interpretation']=source_identity();p.write_text(json.dumps(m))
    atlas=ResearchAtlas(root);r=atlas.describe('association','p')
    assert r['samples']==2 and r['projection_abstentions']==1
    assert not r['production_authorized'] and not r['training_authorized']
    choices=iter([10,0]);seen=[]
    monkeypatch.setattr(ui.mu,'display_menu',lambda *a,**k:next(choices))
    monkeypatch.setattr('builtins.input',lambda prompt:'p' if 'exact value' in prompt else '')
    monkeypatch.setattr(ui,'show_fields',lambda x:seen.append(x))
    monkeypatch.setattr(ui,'show_rows',lambda x:seen.extend(x))
    assert ui.launch_integrated_research(consumer=atlas)==0
    assert any(x.get('permission_query')=='p' for x in seen)


def test_shared_source_period_and_duplicate_observation_denominators():
    m,o,v=data()
    for row in m:
        row.update(source_batch_label='batch', first_submission_month='2020-01',
                   temporal_eligible='True', lineage_component='related')
    o.append(dict(o[0]))
    r=compare_permission(m,o,v,'p')
    pooled=next(x for x in r['association_strata'] if x['dimension']=='pooled' and x['vendor_stratum']=='conflicting')
    assert pooled['positive_samples']==8 and pooled['positive_inferred_components']==1
    cs=[x for x in r['association_contrasts'] if x['left']=='conflicting' and x['right']=='recognized_nonconflicting']
    assert cs[2]['difference']==pytest.approx(-.2)
    assert cs[3]['difference']==pytest.approx(-.2)
    assert cs[0]['min5_difference']==pytest.approx(5/11)
    assert cs[2]['min5_shared_strata']==0


def test_exact_common_population_weighting_and_screen():
    r=compare_permission(*data(),'p')
    c=next(c for c in r['association_contrasts'] if c['dimension']=='family' and c['left']=='conflicting' and c['right']=='recognized_nonconflicting')
    assert c['common_population_pooled_difference']==pytest.approx(5/11)
    assert c['difference']==pytest.approx(-.2)
    assert len(c['common_population']['left']['sample_ids'])==11
    assert c['min5_population']['left']['sample_ids']==[]
    assert c['min5_population_pooled_difference'] is None
