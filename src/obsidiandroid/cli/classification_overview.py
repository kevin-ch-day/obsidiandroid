"""Read-only classification overview and explicit execution navigation.

Cohort viability is not a census, fitted-feature audit or scientific acceptance.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from config import app_config
from obsidiandroid.cli import profile_manager
from obsidiandroid.cli.menu.profile_preflight import validate_profile_runnable
from obsidiandroid.cli.profile_selection import quick_profile_label
from obsidiandroid.cli.ui import display as du, menu as mu
from obsidiandroid.common.run_slots import resolve_run_slot_plan
from obsidiandroid.common.time_display import format_timestamp
from obsidiandroid.orchestration.permission_v2_research_gate import assert_legacy_observation_read_allowed
from obsidiandroid.orchestration import permission_v2_export as v2

READY = 'READY'
BLOCKED = 'BLOCKED'
NOT_EVALUATED = 'NOT EVALUATED'


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    required_before_start: bool = False


def permission_configuration(profile):
    flags = profile.get('feature_flags', {})
    enabled = flags.get('enable_permission_features', getattr(app_config, 'ENABLE_PERMISSION_FEATURES', True))
    policy = flags.get('permission_input_policy', 'development_compatibility' if enabled else 'intentionally_disabled')
    contract = flags.get('permission_feature_contract_version', 'legacy')
    return enabled, policy, contract


def output_destination(profile):
    """Plan paths only; never prepare, archive or create a run slot."""
    plan = resolve_run_slot_plan(
        profile_id=profile['profile_id'], paper_locked=bool(profile.get('paper_locked', False)),
        evidence_mode=bool(profile.get('evidence_mode', False)),
        keep_run_output=bool(profile.get('keep_run_output', False) or getattr(app_config, 'RUNTIME_KEEP_RUN_OUTPUT', False)),
    )
    root = Path(str(getattr(app_config, 'RUNTIME_OUTPUT_ROOT_BASE', None)
                    or app_config.DEFAULT_OUTPUT_DIR)).resolve()
    return str(root / ('runs/_archived/kept/<run_id>' if plan.archive_run else f'runs/{plan.run_slot}'))


def show_experiment(profile):
    du.print_subheader('Experiment overview')
    du.print_stat('Name', profile.get('name') or quick_profile_label(profile['profile_id']))
    du.print_stat('Profile ID', profile['profile_id'])
    du.print_stat('Target', profile.get('training_label_field', 'family_id'))
    du.print_stat('Purpose', 'Train and evaluate configured models; not frozen-model inference for a new APK.')
    du.print_stat('Population', profile.get('description', 'Defined by the profile filters and cohort gates below.'))
    from obsidiandroid.database import db_config
    du.print_stat('Catalog source', db_config.DB_NAME or 'Not configured')
    du.print_stat('PI source', db_config.PERMISSION_INTEL_DB_NAME or 'Not configured')
    du.print_stat('Dataset filter', profile.get('dataset_filters', {}).get('mode', 'none'))
    du.print_stat('Type filter', profile.get('type_slug_filter') or 'No single-type filter')
    gates = profile.get('cohort_gates', {})
    from obsidiandroid.pipeline.sample_exports import resolve_dataset_time_contract
    window = resolve_dataset_time_contract(gates, 'menu_preview')
    du.print_stat('From (inclusive)', window.get('start_utc') or 'No time-window lower bound')
    du.print_stat('Before (exclusive)', window.get('end_utc') or 'No time-window upper bound')
    du.print_stat('Models', ', '.join(profile.get('model_list', [])) or 'Inherited runtime configuration')
    if profile.get('runtime_overrides', {}).get('ENABLE_ABLATION_EXPERIMENTS') is True:
        du.print_stat('Feature comparison', 'Existing ablation suite: vendor, permission and combined feature sets; permission requirements apply to the run.')
        du.print_stat('Ablation models', ', '.join(profile.get('ablation_model_list', profile.get('model_list', []))))
    flags = profile.get('feature_flags', {})
    enabled, policy, contract = permission_configuration(profile)
    metadata = flags.get('enable_sample_metadata_features', getattr(app_config, 'ENABLE_SAMPLE_METADATA_FEATURES', True))
    du.print_stat('Feature modalities', f"Stored AV/vendor features; metadata {'enabled' if metadata else 'disabled'}; permissions {'enabled' if enabled else 'disabled'}")
    du.print_stat('AV feature engine scope', profile.get('av_binary_feature_engine_scope', 'all_observed'))
    du.print_stat('Permission policy', policy)
    du.print_stat('Permission contract', contract)
    du.print_stat('Family authority', gates.get('include_families_from_authority') or 'Profile mapping/label gates')
    du.print_stat('Mapped family required', 'Yes' if gates.get('require_mapped_family', True) else 'No')
    du.print_stat('Unknown type excluded', 'Yes' if gates.get('exclude_unknown_type_slug', bool(profile.get('evidence_mode', False))) else 'No')
    du.print_stat('Family support threshold', gates.get('min_samples_per_family', 'Inherited runtime support policy'))
    du.print_stat('Support policy', gates.get('support_floor_mode', 'Inherited runtime support policy'))
    du.print_info('Full label, confidence and feature settings: View experiment configuration.')
    du.print_stat('Output destination', output_destination(profile))
    du.print_stat('Core artifact directory', str(Path(str(getattr(app_config, 'RUNTIME_OUTPUT_ROOT_BASE', None) or app_config.DEFAULT_OUTPUT_DIR)).resolve() / 'analytical_runs/<run_id>') + ' (only if Core persistence is selected)')
    du.print_stat('Output effects', 'Writes reports/models; may archive or replace a run slot and prune retained archives under existing policy.')
    du.print_stat('Persistence', 'Chosen at final confirmation: local files, or local files plus Core results.')
    du.print_info('Configuration preview only; selected population counts require profile-scoped checks.')


def _permission_checks(profile):
    enabled, policy, contract = permission_configuration(profile)
    if (not isinstance(enabled, bool) or policy not in {'required','development_compatibility','intentionally_disabled'}
        or (policy == 'intentionally_disabled') != (not enabled)):
        return [Check('Permission configuration', BLOCKED, 'Policy and feature enablement are inconsistent.', True)]
    if not enabled and contract != v2.CONTRACT_VERSION:
        return [Check('Permission source', READY, 'Intentionally disabled by configuration; no coverage claim.', True)]
    if contract == 'legacy':
        try:
            assert_legacy_observation_read_allowed()
        except RuntimeError as exc:
            return [Check('Permission source', BLOCKED, str(exc) + '; source was not substituted.', True)]
        return [Check('Permission source', READY, 'Legacy research gate allows reads. Cohort coverage and usable features remain unmeasured.', True)]
    if contract == v2.CONTRACT_VERSION:
        try:
            path = Path(profile.get('feature_flags', {}).get('permission_v2_export_path', ''))
            v2._checked_export(path)
            approval = Check('PI V2 export approval', READY, 'Root-anchored exact export validated; cohort identity intersection not checked.', True)
        except (ValueError, TypeError, KeyError, OSError):
            approval = Check('PI V2 export approval', BLOCKED, 'Approved export is missing, inaccessible or invalid.', True)
        return [approval, Check('PI V2 training authority', BLOCKED,
                'Implemented experiment_split.assert_training_authorized rejects approval v1: feature acceptance does not authorize target-specific training.', True)]
    return [Check('Permission source', NOT_EVALUATED,
                  'This source contract needs its source-specific loader; overview cannot establish training authority.', True)]


def check_readiness(profile):
    """Use existing SELECT-only gates and viability; do not construct a split or fit."""
    checks = _permission_checks(profile)
    if any(c.required_before_start and c.status != READY for c in checks):
        checks.append(Check('Profile cohort viability', NOT_EVALUATED, 'Not queried while permission prerequisites are blocked/unverified.', True))
    else:
        try:
            ok, reason = validate_profile_runnable(profile['profile_id'])
            checks.append(Check('Profile cohort viability', READY if ok else BLOCKED,
                                'Existing profile preflight passed; not an exact population census.' if ok else reason, True))
        except Exception as exc:
            checks.append(Check('Profile cohort viability', NOT_EVALUATED,
                                f'Source check unavailable ({type(exc).__name__}); no readiness assumed.', True))
    checks.extend([
        Check('Selected cohort and labels', NOT_EVALUATED, 'Exact selected sample count and known/unknown family/type counts have not been measured for this profile.'),
        Check('Eligible classes', NOT_EVALUATED, 'Configured support/label rules are shown above; post-filter class counts are not computed by the viability probe.'),
        Check('Feature availability', NOT_EVALUATED, 'Selected-cohort AV, metadata and permission coverage require runtime feature checks; no features fitted here.'),
        Check('Experiment/split integrity', NOT_EVALUATED,
              'Target-specific PI V2 binding is implemented in experiment_split and the runner/trainer. No experiment plan or fit partition has been built or accepted here.'),
        Check('Scientific acceptance', NOT_EVALUATED, 'Cohort viability does not resolve nested CV, preprocessing, label provenance or evaluation limitations.'),
    ])
    return checks


def can_start(checks):
    required = [c for c in checks if c.required_before_start]
    return bool(required) and all(c.status == READY for c in required)


def show_readiness(checks):
    du.print_subheader('Data and training readiness')
    du.print_stat('Checked', format_timestamp(datetime.now(timezone.utc)))
    for check in checks:
        du.print_stat(check.name, f'{check.status} — {check.detail}')
    if can_start(checks):
        du.print_stat('Execution prerequisites', 'READY — checked source prerequisites passed; runtime checks still apply.')
    else:
        status = BLOCKED if any(c.status == BLOCKED for c in checks) else NOT_EVALUATED
        du.print_stat('Execution prerequisites', f'{status} — Start analysis is unavailable until required checks pass.')
    du.print_stat('Training capability', 'NOT EVALUATED — no model fitting was attempted.')


def show_configuration(profile):
    du.print_subheader('Experiment configuration')
    keys = ('profile_id','description','training_label_field','type_slug_filter','dataset_filters',
            'cohort_gates','model_list','feature_flags','parser_overrides','threshold_overrides',
            'paper_locked','paper_lock','evidence_mode','keep_run_output','av_binary_feature_engine_scope',
            'ablation_model_list','runtime_overrides')
    def redact(value):
        if isinstance(value, dict):
            return {k: ('[redacted]' if any(word in str(k).lower() for word in ('password','secret','credential','api_key'))
                        else redact(v)) for k,v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value
    print(json.dumps(redact({k:profile[k] for k in keys if k in profile}), indent=2, default=str))


def launch_experiment(profile_id, *, start_analysis):
    """Only the explicit Start action can reach the existing persistence confirmation."""
    displayed_profile = None
    checked_profile = None
    checks = None
    while True:
        try:
            profile = profile_manager.load_profile(profile_id)
        except (ValueError, OSError) as exc:
            du.print_warning(f'Experiment configuration unavailable ({type(exc).__name__}).')
            return 0
        if profile != displayed_profile:
            show_experiment(profile)
            displayed_profile = deepcopy(profile)
        if profile != checked_profile:
            checks = None
        blocked = checks is not None and not can_start(checks)
        choice = mu.display_menu([
            'Recheck data and training readiness' if checks is not None else 'Check data and training readiness',
            'View experiment configuration',
            'Why analysis is unavailable' if blocked else 'Start analysis',
        ], title='Experiment actions', exit_label='Back', action_hint='',
            selection_prompt='Enter your selection: ')
        if choice == 0:
            return 0
        if choice == 2:
            show_configuration(profile)
            continue
        if choice == 3 and blocked:
            show_start_blockers(checks)
            continue
        # Reload before a check/start so an earlier preview is never a readiness receipt.
        try:
            profile = profile_manager.load_profile(profile_id)
        except (ValueError, OSError) as exc:
            du.print_warning(f'Experiment configuration unavailable ({type(exc).__name__}).')
            continue
        checks = check_readiness(profile)
        checked_profile = deepcopy(profile)
        if choice == 1 and profile_id == 'android_malware_major_families':
            show_population(profile)
        if choice == 1 or can_start(checks):
            show_readiness(checks)
        if not can_start(checks):
            show_start_blockers(checks)
        if choice == 3 and can_start(checks):
            show_experiment(profile)
            du.print_stat('Required evidence status', 'Checked prerequisites passed; feature/split checks still run during analysis.')
            result = start_analysis(profile_id)
            if result:
                du.print_warning(f'Analysis ended with status {result}. Review run diagnostics.')
            # A completed or cancelled execution is not a current readiness receipt.
            checks = None


def show_start_blockers(checks):
    """Explain required failures without repeating deferred scientific checks."""
    du.print_subheader('Analysis unavailable')
    for check in checks:
        if check.required_before_start and check.status != READY:
            du.print_stat(check.name, f'{check.status} — {check.detail}')
    if any(c.name == 'Permission source' and c.status == BLOCKED for c in checks):
        du.print_info('This experiment requires permission features. Its permission source must permit research reads before analysis can start. Export acceptance alone does not authorize PI V2 training.')
    du.print_info('Choose 1 to recheck after the source or configuration issue is resolved, 2 to inspect configuration, or 0 to return. No analysis was started.')


def show_population(profile):
    """Show fresh catalog counts independently of permission execution authority."""
    from obsidiandroid.database.classification_population import major_family_population
    du.print_subheader('Selected profile population')
    try:
        result = major_family_population(profile)
    except Exception as exc:
        du.print_warning(f'Population unavailable ({type(exc).__name__}); eligible sample and family counts are unknown.')
        return
    du.print_stat('Checked', format_timestamp(result['checked_utc']))
    du.print_stat('Metadata-selected samples', f"{result['samples']:,}")
    du.print_stat('Observed families', len(result['families']))
    du.print_stat('With AV source rows', f"{result['av_source_rows']:,}")
    floor = profile.get('cohort_gates', {}).get('min_samples_per_family', 3)
    du.print_stat(f'Families with metadata n >= {floor}', sum(int(r['samples']) >= floor for r in result['families']))
    du.print_info('Before runtime dataset, feature and split checks. AV row presence is not feature readiness. Training-eligible population remains unverified; a permission blocker does not mean zero families.')
