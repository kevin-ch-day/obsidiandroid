"""Operator views of explicitly selected, frozen descriptive research packets."""
from __future__ import annotations

import os
import json
from obsidiandroid.cli.ui import display as du, menu as mu
from obsidiandroid.cli.data_explorer import show_fields, show_rows
from obsidiandroid.common.time_display import format_timestamp
from obsidiandroid.reporting.integrated_research import open_research_packet


def show_paged_rows(rows, *, records=False, page_size=20):
    """Navigate bounded terminal pages without discarding the remaining evidence."""
    offset = 0
    while rows:
        du.print_info(f'Rows {offset + 1}–{min(offset + page_size, len(rows))} of {len(rows)}')
        page = rows[offset:offset + page_size]
        if records:
            for row in page:
                show_fields(row)
        else:
            show_rows([{k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list))
                        else 'UNAVAILABLE' if v is None else v for k, v in row.items()}
                       for row in page])
        if len(rows) <= page_size:
            return
        action = input('n = next, p = previous, Enter = next section: ').strip().lower()
        if action == 'n':
            offset = min(offset + page_size, ((len(rows) - 1) // page_size) * page_size)
        elif action == 'p':
            offset = max(0, offset - page_size)
        else:
            return


def launch_integrated_research(*, consumer=None):
    """Browse retained evidence without connecting to a DB or loading a model."""
    path = os.environ.get('OBSIDIANDROID_RESEARCH_PACKET', '').strip()
    try:
        if consumer is None and not path:
            path = input('Integrated research packet directory (0 = back): ').strip()
        if consumer is None and (not path or path == '0'):
            return 0
        av_path = os.environ.get('OBSIDIANDROID_RESEARCH_AV_PACKET', '').strip()
        packet = consumer if consumer is not None else (
            open_research_packet(path, av_packet=av_path) if av_path else open_research_packet(path))
        options = [('Evidence overview', 'overview'), ('Sample by ID or SHA-256', 'sample'),
                   ('Malware family', 'family'), ('Malware type', 'type')]
        if getattr(packet, 'supports_permission_queries', False):
            options += [('Permission identity across families', 'permission'),
                        ('AV and permission evidence comparison', 'comparison')]
        if getattr(packet, 'supports_engine_queries', False):
            options += [('Antivirus engine', 'engine'), ('AV/PI overlap and missingness', 'overlap'), ('Prior approved PI export — separate contract', 'export')]
        if getattr(packet, 'interpretation_pin', None):
            options += [('Permission associations within AV groups', 'association')]
        if getattr(packet, 'supports_engine_queries', False):
            options += [('Family permission structure and temporal sensitivity', 'structure')]
        if len(getattr(packet, 'pi_cohorts', {})) > 1:
            options += [('Select retained PI cohort', 'cohort')]
        if hasattr(packet, 'alias_sensitivity'):
            options += [('Vendor alias naming sensitivity', 'aliases')]
        while True:
            choice = mu.display_menu(
                [label for label, _ in options],
                title='Integrated Android research', exit_label='Return to Data Explorer',
                action_hint='', selection_prompt='Enter your selection: ',
                context_lines=[('SOURCE', 'Frozen retained evidence; no model inference or training.'),
                               ('PERMISSIONS', 'Observed declarations, not runtime behavior; governed capabilities may be unavailable.')])
            if choice == 0:
                return 0
            kind = options[choice - 1][1]
            if kind == 'cohort':
                names = list(packet.pi_cohorts) + ['combined']
                selected = input('PI cohort (' + ', '.join(names) + '): ').strip()
                try:
                    packet.select_pi_cohort(selected)
                except ValueError as exc:
                    du.print_warning(str(exc))
                continue
            value = '' if kind in {'overview', 'comparison', 'overlap', 'export', 'structure', 'aliases'} else input(f'{kind.capitalize()} (exact value; 0 = back): ').strip()
            if value == '0':
                continue
            result = packet.describe(kind, value)
            show_fields({k: v for k, v in result.items() if not isinstance(v, (dict, list))})
            du.print_info('Permission consumer availability:')
            show_fields(result['permission_consumer_availability'])
            for key in ['research_readiness', 'classification_versions', 'comparison_readiness', 'pi_population', 'vendor_intelligence_summary']:
                if result.get(key):
                    du.print_info(key.replace('_', ' ').capitalize())
                    show_fields(result[key])
            for key in ['pi_cohort_sources', 'source_context_records', 'structure_coverage', 'structure_pairs', 'structure_component_sensitivity', 'structure_source_sensitivity', 'structure_temporal', 'structure_contributions', 'structure_profiles', 'structure_annual', 'association_contrasts', 'association_strata', 'association_samples', 'permission_coverage_matrix', 'records', 'vendor_claims', 'exact_permission_tokens', 'permission_profile', 'authority_and_protection',
                        'unresolved_evidence', 'lineage_signatures', 'temporal_permissions',
                        'permission_comparison', 'permission_totals', 'modality_comparison', 'vendor_evidence',
                        'capability_interpretations', 'permission_evidence', 'category_counts', 'engine_coverage', 'family_av', 'raw_claims', 'normalized_claims', 'coverage_populations', 'av_strata', 'interpretation_outcomes', 'vendor_label_review']:
                rows = result.get(key, [])
                if rows:
                    if kind == 'overview' and key not in {'permission_coverage_matrix', 'modality_comparison', 'category_counts', 'engine_coverage', 'family_av', 'coverage_populations', 'interpretation_outcomes'}:
                        continue
                    if key == 'permission_profile' and result.get('permission_totals'):
                        continue
                    du.print_info(f'{key.replace("_", " ").capitalize()}:')
                    if key == 'permission_coverage_matrix':
                        rows = [{k: format_timestamp(v) if k == 'observed_utc'
                                    else 'Unknown' if v is None else v
                                    for k, v in row.items()} for row in rows]
                    if key == 'permission_evidence':
                        du.print_info('Exact source/history/version objects remain available in the research CLI JSON.')
                        rows = [dict(obs_id=row['obs_id'], sample_id=row['sample_id'],
                                     token=row['exact_token'], canonical=row['canonical_identity'] or 'UNRESOLVED',
                                     protection=row['protection_base'], authority=row['evidence_level'],
                                     source_match=row['source'].get('match_state', 'UNAVAILABLE'),
                                     historical_binding=row['source']['historical_relationship'],
                                     abstentions=', '.join(row['abstentions'])) for row in rows]
                    show_paged_rows(rows, records=key == 'records')
            if result.get('raw_source'):
                raw_source = result['raw_source']
                show_fields({k:v for k,v in raw_source.items() if k != 'engines'})
                show_paged_rows(raw_source.get('engines', []))
            for key in ['families', 'types', 'sources', 'label_authority', 'vendor_family_relationships', 'first_submission_months']:
                rows = result.get(key, {})
                if rows:
                    du.print_info(f'{key.replace("_", " ").capitalize()}:')
                    show_paged_rows([{'label': k, 'samples': v} for k, v in rows.items()])
    except (OSError, ValueError, KeyError) as exc:
        du.print_warning(f'Research packet unavailable: {type(exc).__name__}. Check the packet path and integrity.')
    except (EOFError, KeyboardInterrupt):
        du.print_info('Research view cancelled.')
    return 0
