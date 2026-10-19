"""Local cohort export/selection preserves source evidence without approval services."""
import json
import hashlib
import pytest
from obsidiandroid.reporting.permission_research_view import PermissionResearchView
from obsidiandroid.reporting.research_atlas import ResearchAtlas
from test_research_atlas import fixture


def test_subset_roundtrip_abstention_and_exact_allowlist(tmp_path):
    root=fixture(tmp_path); view=PermissionResearchView(root/'pi')
    member=view.samples[1]
    subset=view.export_subset(root/'subset',[member])
    assert subset.samples==[member]
    assert subset.observations==[r for r in view.observations if r['sample_id']==2]
    assert subset.describe()['permission_consumer_availability']['projection_abstentions']==1
    for bad in [[dict(member,sha256='c'*64)],[dict(member,event_id='900')],[dict(member,payload_hash='f'*64)],[dict(member,sample_id='999')],[member,member]]:
        with pytest.raises(ValueError):view.export_subset(root/'bad',bad)
        assert not (root/'bad').exists()
    with pytest.raises(ValueError):view.export_subset(root/'subset',[member])


def test_atlas_cohort_select_and_combine(tmp_path):
    root=fixture(tmp_path); view=PermissionResearchView(root/'pi')
    original=view.export_subset(root/'original',[view.samples[0]])
    addition=view.export_subset(root/'addition',[view.samples[1]])
    allow=root/'identities.csv'
    allow.write_bytes((root/'addition/COHORT_METADATA.csv').read_bytes())
    def pin(p):return dict(path=str(p),sha256=hashlib.sha256((p/'PI_VIEW_MANIFEST.json').read_bytes()).hexdigest())
    config=json.loads((root/'ATLAS_MANIFEST.json').read_text());config['pi']=pin(root/'original')
    config['pi_cohorts']={'pilot_b':dict(pin(root/'addition'),identities=dict(path=str(allow),sha256=hashlib.sha256(allow.read_bytes()).hexdigest()))}
    (root/'ATLAS_MANIFEST.json').write_text(json.dumps(config))
    atlas=ResearchAtlas(root)
    assert len(atlas.pi.samples)==1
    assert atlas.select_pi_cohort('pilot_b').describe('comparison')['samples']==1
    r=atlas.select_pi_cohort('combined').describe('comparison')
    assert r['samples']==2 and r['pi_population']['projection_abstentions']==1
    assert r['research_readiness']['selected_cohort']=='combined'
    assert len(atlas.select_pi_cohort('original').pi.samples)==1
    with pytest.raises(ValueError):atlas.select_pi_cohort('not-retained')
    with pytest.raises(ValueError):PermissionResearchView.combine([original,original])
    addition.manifest['versions']={'classifier':'different'}
    with pytest.raises(ValueError):PermissionResearchView.combine([original,addition])


def test_export_failure_leaves_no_destination(tmp_path,monkeypatch):
    root=fixture(tmp_path); view=PermissionResearchView(root/'pi')
    view.observations[0]['source']['sha256']='bad'
    with pytest.raises(ValueError):view.export_subset(root/'bad',[view.samples[0]])
    assert not (root/'bad').exists()


def test_cli_subset_and_console_cohort_selection(tmp_path, monkeypatch):
    from obsidiandroid.reporting import integrated_research as cli
    from obsidiandroid.cli import integrated_research as ui
    root=fixture(tmp_path)
    identities=root/'identities.csv'
    identities.write_bytes((root/'pi/COHORT_METADATA.csv').read_bytes())
    monkeypatch.setattr('sys.argv',['research','--packet',str(root),'--identities',str(identities),
                                 '--write-subset',str(root/'export'),'overview'])
    cli.main()
    assert len(PermissionResearchView(root/'export').samples)==2
    atlas=ResearchAtlas(root)
    view=atlas.pi
    atlas.pi_cohorts['subset']=view.export_subset(root/'subset',[view.samples[1]])
    choices=iter([11,11,1,0])  # no vendor interpretation pin: selector follows structure
    inputs=iter(['unknown','subset'])
    monkeypatch.setattr(ui.mu,'display_menu',lambda *a,**k:next(choices))
    monkeypatch.setattr('builtins.input',lambda prompt:next(inputs) if 'PI cohort (' in prompt else '')
    seen=[]
    monkeypatch.setattr(ui,'show_fields',lambda x:seen.append(x))
    monkeypatch.setattr(ui,'show_rows',lambda x:None)
    assert ui.launch_integrated_research(consumer=atlas)==0
    assert any(r.get('selected_cohort')=='subset' for r in seen)


def test_combined_population_limit_matches_requested_expansion(tmp_path):
    import copy
    root=fixture(tmp_path); template=PermissionResearchView(root/'pi')
    def make(start,count):
        view=copy.copy(template);view.samples=[];view.observations=[]
        for sid in range(start,start+count):
            member=dict(template.samples[0],sample_id=str(sid),sha256=f'{sid:064x}')
            row=dict(template.observations[0],sample_id=sid,obs_id=sid,sha256=member['sha256'])
            view.samples.append(member);view.observations.append(row)
        return view
    first,second=make(1,1212),make(1213,100)
    assert len(PermissionResearchView.combine([first,second]).samples)==1312
    with pytest.raises(ValueError,match='cohort bounds'):
        PermissionResearchView.combine([first,make(1213,101)])
