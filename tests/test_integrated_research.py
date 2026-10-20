import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pandas as pd
import pytest
from obsidiandroid.reporting.integrated_research import (
    attribution_relationship, submission_proxy, attach_permission_coverage,
    permission_profile, ResearchPacket, FORMAT,
)


def test_research_cli_cold_import_is_acyclic():
    """The real module entry point must import before pytest warms package imports."""
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    result = subprocess.run(
        [sys.executable, "-c", "from obsidiandroid.reporting.integrated_research import open_research_packet"],
        cwd=root, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_permission_identity_mismatch_rejected():
    a = pd.DataFrame({'sample_id': [1], 'sha256': ['a' * 64]})
    b = pd.DataFrame({'sample_id': [1], 'sha256': ['b' * 64]})
    with pytest.raises(ValueError, match='disagreement'):
        attach_permission_coverage(a, b)
    b = pd.DataFrame({'sample_id': [2], 'sha256': ['a' * 64]})
    with pytest.raises(ValueError, match='disagreement'):
        attach_permission_coverage(a, b)


def test_permission_missingness_and_covered_denominator():
    a = pd.DataFrame({'sample_id': [1, 2], 'sha256': ['a' * 64, 'b' * 64]})
    result = attach_permission_coverage(a, a.iloc[:1])
    assert result.permission_state.tolist() == ['PROVIDER_REPORTED_UNRESOLVED', 'UNAVAILABLE']
    occurrences = pd.DataFrame({'sample_id': [1, 1], 'token': ['x', 'x']})
    profile = permission_profile(result, occurrences)
    assert profile[0]['covered_denominator'] == 1
    assert profile[0]['samples'] == 1
    assert profile[0]['category'] == profile[0]['capability'] == 'UNAVAILABLE'
    assert permission_profile(result.iloc[1:], occurrences) == []


def test_timestamp_missingness_and_ordering_never_substitutes_scan():
    assert submission_proxy(None, 1600000000)['first_submission_utc'] == ''
    assert not submission_proxy(True, 1600000000)['temporal_eligible']
    anomaly = submission_proxy(1700000000, 1600000000)
    assert anomaly['first_after_analysis'] and not anomaly['temporal_eligible']
    valid = submission_proxy(1600000000, 1700000000)
    assert valid['first_submission_month'] == '2020-09' and valid['temporal_eligible']
    for missing in [float('nan'), float('inf'), -1, '1600000000']:
        assert not submission_proxy(missing, 1700000000)['temporal_eligible']


def test_attribution_does_not_rewrite_or_resolve_unknowns():
    assert attribution_relationship(' Joker ', 'Joker') == 'exact'
    assert attribution_relationship('joker', 'Joker') == 'case_or_whitespace'
    assert attribution_relationship('Joker', 'Godfather') == 'conflict_requires_review'
    assert attribution_relationship('unknown', 'Joker') == 'unresolved'
    assert attribution_relationship('darkHerring', 'Dark Herring') == 'separator_formatting'


def test_packet_tampering_rejected(tmp_path):
    raw = b'sample_id,sha256\n1,abc\n'
    (tmp_path / 'SAMPLES.csv').write_bytes(raw + b'2,def\n')
    (tmp_path / 'RESEARCH_MANIFEST.json').write_text(json.dumps(
        {'format': FORMAT, 'files': {'SAMPLES.csv': hashlib.sha256(raw).hexdigest()}}))
    with pytest.raises(ValueError, match='hash mismatch'):
        ResearchPacket(tmp_path)


def test_research_menu_does_not_open_live_session(monkeypatch):
    from obsidiandroid.cli import data_explorer, integrated_research
    choices = iter([6, 0]);called=[]
    monkeypatch.setattr(data_explorer.mu, 'display_menu', lambda *a, **k: next(choices))
    monkeypatch.setattr(integrated_research, 'launch_integrated_research', lambda: called.append(True))
    monkeypatch.setattr(data_explorer, 'explorer_session', lambda: pytest.fail('Unexpected DB connection'))
    assert data_explorer.launch_data_explorer() == 0
    assert called == [True]


def test_family_and_type_views_keep_population_and_coverage_separate(tmp_path):
    samples = pd.DataFrame({
        'sample_id': [1, 2], 'sha256': ['a' * 64, 'b' * 64],
        'recorded_family': ['FamilyA', 'FamilyB'], 'malware_type': ['banker', 'banker'],
        'source_batch_label': ['source_a', ''], 'authority_basis': ['review', ''],
        'permission_covered': [True, False], 'reviewed_label': [False, True],
        'temporal_eligible': [True, False], 'first_submission_utc': ['2020-01-01T00:00:00+00:00', ''],
        'first_submission_month': ['2020-01', ''], 'first_after_analysis': [False, False],
        'distinct_known_families': [2, 0], 'known_family_votes': [4, 0],
    })
    permissions = pd.DataFrame({'sample_id': [1], 'sha256': ['a' * 64], 'token': ['x']})
    samples.to_csv(tmp_path / 'SAMPLES.csv', index=False)
    permissions.to_csv(tmp_path / 'PERMISSIONS.csv', index=False)
    manifest = {'format': FORMAT, 'files': {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                                           for name in ['SAMPLES.csv', 'PERMISSIONS.csv']}}
    (tmp_path / 'RESEARCH_MANIFEST.json').write_text(json.dumps(manifest))
    packet = ResearchPacket(tmp_path)
    family = packet.describe('family', 'familyb')
    assert family['samples'] == 1 and family['permission_unavailable_samples'] == 1
    assert family['permission_profile'] == []
    combined = packet.describe('type', 'banker')
    assert combined['samples'] == 2 and combined['permission_covered_samples'] == 1
    assert combined['permission_profile'][0]['covered_prevalence'] == 1
    assert combined['temporal_eligible_samples'] == 1 and combined['missing_first_submission'] == 1
    assert combined['training_authorized'] is False
    assert combined['vendor_conflicting_samples'] == 1
