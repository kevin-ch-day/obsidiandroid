"""Offline contracts for classification navigation and pre-execution evidence."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from obsidiandroid.cli import classification_overview as ui
from obsidiandroid.cli.ui import console as console_ui


@pytest.fixture(autouse=True)
def _plain_console(monkeypatch):
    """These assertions read plain text; colour codes depend on the terminal."""
    monkeypatch.setattr(console_ui, "USE_COLORS", False)


@pytest.fixture
def profile(monkeypatch):
    from obsidiandroid.database import classification_population
    monkeypatch.setattr(classification_population, 'major_family_population',
                        Mock(side_effect=RuntimeError('offline fixture')))
    return {
        'profile_id':'android_malware_major_families', 'name':'Fixture family experiment',
        'description':'Selected major-family fixture; not the broad catalog',
        'training_label_field':'family_id', 'model_list':['random_forest'],
        'dataset_filters':{'mode':'malicious_only'},
        'cohort_gates':{'min_samples_per_family':7, 'support_floor_mode':'benchmark_eligibility',
                        'time_window_start_utc':'2020-01-01T00:00:00Z',
                        'time_window_end_utc':'2026-01-01T00:00:00Z'},
        'feature_flags':{'enable_permission_features':False,'permission_input_policy':'intentionally_disabled'},
    }


def test_population_is_visible_without_claiming_training_ready(profile, monkeypatch, capsys):
    from obsidiandroid.database import classification_population
    monkeypatch.setattr(classification_population, 'major_family_population', lambda _: {
        'checked_utc': '2026-10-18T12:00:00+00:00', 'samples': 100, 'av_source_rows': 80,
        'families': [{'samples': 98}, {'samples': 2}]})
    ui.show_population(profile)
    output = ' '.join(capsys.readouterr().out.split())
    assert '100' in output and '80' in output
    assert 'Training-eligible population remains unverified' in output


def test_unavailable_population_is_not_zero(profile, capsys):
    ui.show_population(profile)
    output = capsys.readouterr().out
    assert 'Population unavailable' in output
    assert 'Metadata-selected samples' not in output


def test_summary_is_configuration_not_catalog_census(profile, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ui.app_config, 'DEFAULT_OUTPUT_DIR', str(tmp_path/'preview-output'))
    monkeypatch.setattr(ui.app_config, 'RUNTIME_OUTPUT_ROOT_BASE', None, raising=False)
    before = deepcopy(profile)
    ui.show_experiment(profile)
    out = capsys.readouterr().out
    assert 'Fixture family experiment' in out and 'family_id' in out and 'random_forest' in out
    assert 'benchmark_eligibility' in out and '7' in out
    assert 'Selected major-family fixture' in out and '35,369' not in out
    assert 'intentionally_disabled' in out and 'not frozen-model inference' in ' '.join(out.split())
    assert 'majorfam_benchmark' in out and 'archive' in out and 'Core' in out
    assert not (tmp_path/'preview-output').exists()
    assert profile == before


def test_readiness_viability_ready_is_not_scientific_ready(profile, monkeypatch):
    viable = Mock(return_value=(True,''))
    monkeypatch.setattr(ui, 'validate_profile_runnable', viable)
    checks = ui.check_readiness(profile)
    assert ui.can_start(checks)
    assert next(c for c in checks if c.name == 'Profile cohort viability').status == ui.READY
    for name in ('Selected cohort and labels','Feature availability','Eligible classes','Scientific acceptance','Experiment/split integrity'):
        assert next(c for c in checks if c.name == name).status == ui.NOT_EVALUATED
    viable.assert_called_once_with(profile['profile_id'])


@pytest.mark.parametrize('policy', ['required','development_compatibility'])
def test_legacy_gate_blocks_before_cohort_reads(profile, monkeypatch, policy):
    profile['feature_flags'] = {'enable_permission_features':True, 'permission_input_policy':policy}
    monkeypatch.setattr(ui, 'assert_legacy_observation_read_allowed', Mock(side_effect=RuntimeError('PI gate blocks legacy permission features')))
    viability = Mock()
    monkeypatch.setattr(ui, 'validate_profile_runnable', viability)
    checks = ui.check_readiness(profile)
    assert not ui.can_start(checks)
    assert checks[0].status == ui.BLOCKED
    viability.assert_not_called()


def test_v2_approved_export_does_not_authorize_model_training(profile, monkeypatch):
    profile['feature_flags'] = dict(enable_permission_features=True, permission_input_policy='required',
                                   permission_feature_contract_version=ui.v2.CONTRACT_VERSION,
                                   permission_v2_export_path='/fixture/export.json')
    monkeypatch.setattr(ui.v2, '_checked_export', Mock(return_value=(b'',b'',{})))
    checks = ui.check_readiness(profile)
    assert checks[0].status == ui.READY
    assert checks[1].status == ui.BLOCKED
    assert 'feature acceptance' in checks[1].detail
    assert not ui.can_start(checks)


def test_v2_missing_approval_is_blocked(profile, monkeypatch):
    profile['feature_flags'] = dict(enable_permission_features=True, permission_input_policy='required',
                                   permission_feature_contract_version=ui.v2.CONTRACT_VERSION)
    monkeypatch.setattr(ui.v2, '_checked_export', Mock(side_effect=ValueError('not approved')))
    assert ui.check_readiness(profile)[0].status == ui.BLOCKED


@pytest.mark.parametrize('result', [(False,'restricted source'), (False,'empty selected cohort')])
def test_failed_preflight_cannot_start(profile, monkeypatch, result):
    monkeypatch.setattr(ui, 'validate_profile_runnable', lambda _:result)
    assert not ui.can_start(ui.check_readiness(profile))


def test_unavailable_check_not_assumed_success(profile, monkeypatch):
    monkeypatch.setattr(ui, 'validate_profile_runnable', Mock(side_effect=PermissionError('private detail')))
    checks = ui.check_readiness(profile)
    assert checks[1].status == ui.NOT_EVALUATED
    assert 'private detail' not in checks[1].detail
    assert not ui.can_start(checks)
    assert not ui.can_start([])


@pytest.mark.parametrize('choices', [[0], [2,0], [1,0]])
def test_readonly_actions_never_launch_or_archive(profile, monkeypatch, choices):
    from obsidiandroid.common import run_slots
    from obsidiandroid import pipeline
    monkeypatch.setattr(pipeline, 'run_pipeline', Mock(side_effect=AssertionError('training')))
    monkeypatch.setattr(run_slots, 'prepare_run_root', Mock(side_effect=AssertionError('archive')))
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _:deepcopy(profile))
    monkeypatch.setattr(ui, 'validate_profile_runnable', lambda _:(True,''))
    answers = iter(choices)
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a,**k:next(answers))
    start = Mock()
    ui.launch_experiment(profile['profile_id'], start_analysis=start)
    start.assert_not_called()


def test_start_refreshes_preflight_and_reuses_final_confirmation(profile, monkeypatch):
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _:deepcopy(profile))
    viable = Mock(side_effect=[(True,''),(False,'source no longer available')])
    monkeypatch.setattr(ui, 'validate_profile_runnable', viable)
    answers = iter([1,3,0])
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a,**k:next(answers))
    start = Mock()
    ui.launch_experiment(profile['profile_id'], start_analysis=start)
    assert viable.call_count == 2
    start.assert_not_called()


def test_explicit_start_warns_before_confirmation(profile, monkeypatch, capsys):
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _:deepcopy(profile))
    monkeypatch.setattr(ui, 'validate_profile_runnable', lambda _:(True,''))
    answers = iter([3,0])
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a,**k:next(answers))
    calls = []
    def confirmation(profile_id):
        text = capsys.readouterr().out
        assert 'archive' in text and 'Core' in text
        assert 'Required evidence status' in text and 'NOT EVALUATED' in text
        calls.append(profile_id)
        return 0  # existing final confirmation cancelled
    ui.launch_experiment(profile['profile_id'], start_analysis=confirmation)
    assert calls == [profile['profile_id']]


def test_configuration_view_redacts_private_keys(profile, capsys):
    profile['feature_flags']['password'] = 'sensitive'
    ui.show_configuration(profile)
    out = capsys.readouterr().out
    assert 'sensitive' not in out and '[redacted]' in out


def test_advanced_route_preserved(monkeypatch):
    from obsidiandroid.cli import startup_menu
    answers = iter([4,0])
    monkeypatch.setattr(startup_menu.mu, 'display_menu', lambda *a,**k:next(answers))
    advanced = Mock()
    monkeypatch.setattr(startup_menu, '_launch_pipeline_actions_menu', advanced)
    startup_menu._launch_classification_menu()
    advanced.assert_called_once()


def test_unsupported_contract_cannot_claim_readiness(profile):
    profile['feature_flags'] = dict(enable_permission_features=True,
                                   permission_feature_contract_version='unreviewed')
    checks = ui.check_readiness(profile)
    assert checks[0].status == ui.NOT_EVALUATED
    assert not ui.can_start(checks)


def test_permission_gate_blocks_explicit_start(profile, monkeypatch):
    profile['feature_flags'] = dict(enable_permission_features=True,permission_input_policy='required')
    monkeypatch.setattr(ui.profile_manager,'load_profile',lambda _:deepcopy(profile))
    monkeypatch.setattr(ui,'assert_legacy_observation_read_allowed',Mock(side_effect=RuntimeError('BLOCKED')))
    answers = iter([3,0])
    monkeypatch.setattr(ui.mu,'display_menu',lambda *a,**k:next(answers))
    start = Mock()
    ui.launch_experiment(profile['profile_id'],start_analysis=start)
    start.assert_not_called()


def test_blocked_start_explains_without_repeating_queries_or_overview(profile, monkeypatch, capsys):
    profile['feature_flags'] = dict(enable_permission_features=True, permission_input_policy='required')
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _: deepcopy(profile))
    gate = Mock(side_effect=RuntimeError('PI V2 research gate blocks legacy permission features'))
    monkeypatch.setattr(ui, 'assert_legacy_observation_read_allowed', gate)
    viability = Mock()
    monkeypatch.setattr(ui, 'validate_profile_runnable', viability)
    answers = iter([3, 3, 0])
    menus = []
    def menu(options, **kwargs):
        menus.append(options)
        return next(answers)
    monkeypatch.setattr(ui.mu, 'display_menu', menu)
    start = Mock()
    ui.launch_experiment(profile['profile_id'], start_analysis=start)
    output = capsys.readouterr().out
    assert output.count('EXPERIMENT OVERVIEW') == 1
    assert 'Scientific acceptance' not in output
    assert menus[1][2] == 'Why analysis is unavailable'
    assert menus[1][0] == 'Recheck data and training readiness'
    assert 'Choose 1 to recheck' in output
    gate.assert_called_once()
    viability.assert_not_called()
    start.assert_not_called()


def test_explicit_recheck_clears_block_but_start_checks_again(profile, monkeypatch):
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _: deepcopy(profile))
    viable = Mock(side_effect=[(False, 'source unavailable'), (True, ''), (True, '')])
    monkeypatch.setattr(ui, 'validate_profile_runnable', viable)
    answers = iter([3, 1, 3, 0])
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a, **k: next(answers))
    start = Mock(return_value=0)
    ui.launch_experiment(profile['profile_id'], start_analysis=start)
    assert viable.call_count == 3
    start.assert_called_once_with(profile['profile_id'])


def test_kept_run_path_matches_existing_planner(profile, monkeypatch, tmp_path):
    monkeypatch.setattr(ui.app_config,'DEFAULT_OUTPUT_DIR',str(tmp_path))
    monkeypatch.setattr(ui.app_config,'RUNTIME_OUTPUT_ROOT_BASE',None,raising=False)
    profile['keep_run_output'] = True
    assert ui.output_destination(profile) == str(tmp_path/'runs/_archived/kept/<run_id>')
    assert not (tmp_path/'runs').exists()


@pytest.mark.parametrize('choice, expected', [
    (1, 'android_malware_major_families'),
    (2, 'android_malware_type_taxonomy'),
    (3, 'dev_ablation_fast'),
])
def test_comparison_profiles_open_overview_only(monkeypatch, choice, expected):
    from obsidiandroid.cli import startup_menu
    answers = iter([choice, 0])
    monkeypatch.setattr(startup_menu.mu, 'display_menu', lambda *a, **k: next(answers))
    overview = Mock()
    monkeypatch.setattr(ui, 'launch_experiment', overview)
    confirm = Mock(side_effect=AssertionError('Opening a comparison must not train'))
    monkeypatch.setattr(startup_menu, '_run_full_pipeline_with_persistence_choice', confirm)
    startup_menu._launch_comparison_menu()
    overview.assert_called_once_with(expected, start_analysis=confirm)
    confirm.assert_not_called()


def test_classification_comparison_navigation(monkeypatch):
    from obsidiandroid.cli import startup_menu
    answers = iter([3, 0])
    monkeypatch.setattr(startup_menu.mu, 'display_menu', lambda *a, **k: next(answers))
    compare = Mock()
    monkeypatch.setattr(startup_menu, '_launch_comparison_menu', compare)
    startup_menu._launch_classification_menu()
    compare.assert_called_once()


@pytest.mark.parametrize('ready, confirmation', [(False, True), (True, False), (True, True)])
def test_advanced_preview_requires_readiness_and_confirmation(profile, monkeypatch, ready, confirmation):
    from obsidiandroid.cli import startup_menu
    monkeypatch.setattr(ui.profile_manager, 'load_profile', lambda _: profile)
    monkeypatch.setattr(ui, 'check_readiness', lambda _: [ui.Check('source', ui.READY if ready else ui.BLOCKED, 'fixture', True)])
    confirm = Mock(return_value=confirmation)
    monkeypatch.setattr(startup_menu.mu, 'confirm_prompt', confirm)
    assert startup_menu._preview_classification(profile['profile_id']) == (ready and confirmation)
    assert confirm.call_count == int(ready)
