"""Retained positive labels and hostile boundary cases for vendor explanations."""
import json
import pytest
from obsidiandroid.vendors.parsing.kaspersky_parser import parse_kaspersky_classification
from obsidiandroid.vendors.interpretation_quality import interpret, source_identity


@pytest.mark.parametrize('label,family',[
 ('HEUR:Trojan-Banker.AndroidOS.GodFather.m','godfather'),
 ('HEUR:Trojan-Spy.AndroidOS.Gigabud.c','gigabud'),
 ('HEUR:Trojan-Banker.AndroidOS.GodFather.b','godfather')])
def test_retained_supported_exact_family_slot(label,family):
    parsed=parse_kaspersky_classification(label).to_dict()
    assert parsed['family']==family
    r=interpret('Kaspersky',label,'unknown',False)
    assert r['corrected'] and r['family']==family and r['state']=='E_CORRECTED_IMPLEMENTATION'


@pytest.mark.parametrize('label',[
 'HEUR:Trojan-Spy.AndroidOS.Arsink.a',
 'HEUR:Backdoor.AndroidOS.KungFu.a',
 'HEUR:Trojan-Banker.AndroidOS.Agent.pp',
 'HEUR:Trojan.AndroidOS.Unknown.GodFather',
 'HEUR:Trojan.AndroidOS.NotGodFather.m',
 'HEUR:Trojan.Win32.GodFather.m',
 'HEUR:Trojan.NotAndroid.GodFather.m',
 'HEUR:Trojan.AndroidEvil.GodFather.m',
 'HEUR:Trojan.AndroidOS.GodFather_Evil.m',
 'HEUR:Trojan.AndroidOS.GodFatherEvil.m',
 'Detected','Trojan.Generic.1',''])
def test_no_alias_suffix_substring_or_platform_promotion(label):
    r=interpret('Kaspersky',label,'unknown',False)
    assert not r['recognized'] and not r['corrected']


def test_generic_and_ambiguous_keep_abstention():
    assert interpret('Google','Detected','unknown',False)['state']=='A_GENERIC_DETECTION'
    assert interpret('Cynet','Malicious (score: 99)','unknown',False)['family'] is None
    assert interpret('Other','Android.Godfather.Joker','unknown',False)['state']=='D_AMBIGUOUS'
    assert interpret('Ikarus','Trojan.AndroidOS.DroidKungFu','droidkungfu',False,{'droidkungfu'})['state']=='F_TAXONOMY_REVIEW'
    assert interpret('DrWeb','Android.BankBot.1042.origin','bankbot',True)['family']=='bankbot'
    assert interpret('Unknown','Android.TotallyNovel.X','unknown',False)['state']=='C_SPECIFIC_LOOKING_UNRESOLVED'


def test_pinned_atlas_explains_without_changing_frozen_claims(tmp_path):
    from test_research_atlas import fixture
    from obsidiandroid.reporting.research_atlas import ResearchAtlas
    fixture(tmp_path)
    p=tmp_path/'ATLAS_MANIFEST.json';m=json.loads(p.read_text());m['vendor_interpretation']=source_identity();p.write_text(json.dumps(m))
    a=ResearchAtlas(tmp_path);before=a._load_vendors().copy(deep=True)
    r=a.describe('engine','Engine-X')
    assert r['vendor_intelligence_summary']['recognized_verdicts_before']==1
    assert r['vendor_intelligence_summary']['recognized_verdicts_after']==1
    assert r['vendor_label_review'][0]['example_payload_hash']
    assert a._load_vendors().equals(before)
    m['vendor_interpretation']['policy']='changed';p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='interpretation source'):ResearchAtlas(tmp_path)
