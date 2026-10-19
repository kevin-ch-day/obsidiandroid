"""Read-only console browsing, separate from profile selection and run slots."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from datetime import date
from obsidiandroid.common.time_display import format_timestamp
from obsidiandroid.cli.ui import display as du, menu as mu
from obsidiandroid.database.data_explorer import (
    ExplorerUnavailable, PAGE_SIZE, POPULATION_NOTE, explorer_session,
)


def _safe_text(value):
    return ''.join(char if char.isprintable() else f"\\x{ord(char):02x}" for char in str(value))


def show_fields(fields, *, labels=None):
    for label, value in fields.items():
        shown = 'Unavailable / not measured' if value is None else value
        if isinstance(shown, (int, Decimal)):
            shown = f'{shown:,}'
        display_label = (labels or {}).get(label, label.replace('_', ' ').capitalize())
        du.print_stat(display_label, _safe_text(format_timestamp(shown, assume_utc=label.endswith('_utc'))), width=28)


def show_rows(rows, **kwargs):
    du.print_table([{key: _safe_text(value) if isinstance(value, str) else value
                     for key, value in row.items()} for row in rows], **kwargs)


def header(service, title):
    du.print_subheader(title)
    du.print_info(f'Updated: {format_timestamp(service.checked_utc)}')
    du.print_info(POPULATION_NOTE)


def _overview_section(title):
    print('\n' + title.upper())
    du.print_rule(width=43)


def _overview_read(message, operation):
    """Show transient progress only on a terminal; clear it even on failure."""
    interactive = sys.stdout.isatty()
    if interactive:
        print(message, end='', flush=True)
    try:
        return operation()
    finally:
        if interactive:
            print('\r' + ' ' * len(message) + '\r', end='', flush=True)


def _overview_count(value):
    """Accept exact nonnegative counts, never coerce missing data to zero."""
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    return int(value) if value >= 0 and value == int(value) else None


def _overview_stat(label, value):
    text = 'Unavailable' if value is None else _safe_text(value)
    if isinstance(value, int):
        text = f'{value:,}'
    du.print_stat(label, text, width=28)


def _overview_types(service):
    """Read existing bounded pages to identify the actual category count."""
    rows = []
    seen = set()
    for page in range(10001):
        batch = service.browse(kind='type', page=page)
        for row in batch[:PAGE_SIZE]:
            label = row.get('label')
            if label in seen:
                raise ExplorerUnavailable('Type distribution changed or repeated a category; refresh the overview.')
            seen.add(label)
            rows.append(row)
        if len(batch) <= PAGE_SIZE:
            return sorted(rows, key=lambda row: (
                -(_overview_count(row.get('samples')) or 0), str(row.get('label') or '')
            ))
    raise ExplorerUnavailable('Type distribution exceeds the supported page bound.')


def _show_overview_types(rows, selected):
    displayed = rows[:PAGE_SIZE]
    partial = len(displayed) < len(rows)
    print(f"{'Type':<28} {'Samples':>12}")
    du.print_rule(width=43)
    for row in displayed:
        count = _overview_count(row.get('samples'))
        text = f'{count:,}' if count is not None else 'Unavailable'
        label = 'Unavailable' if row.get('label') is None else _safe_text(row['label'])
        print(f'{label:<28} {text:>12}')
    if not displayed:
        print('No malware-type categories returned.')
    du.print_rule(width=43)
    counts = [_overview_count(row.get('samples')) for row in displayed]
    subtotal = sum(counts) if all(count is not None for count in counts) else None
    total_label = 'Displayed subtotal' if partial else 'Total'
    total_text = f'{subtotal:,}' if subtotal is not None else 'Unavailable'
    print(f'{total_label:<28} {total_text:>12}')
    if partial:
        print(f'Showing {len(displayed)} of {len(rows)} types; use Malware families and types to browse all.')
    all_counts = [_overview_count(row.get('samples')) for row in rows]
    total = sum(all_counts) if all(count is not None for count in all_counts) else None
    if total is None or selected is None:
        print('Population consistency: unavailable; a count is missing.')
    elif total != selected:
        print(f'Population mismatch: all types total {total:,}; selected APKs {selected:,}.')


def show_overview(service):
    _overview_section('Dataset overview')
    print('Live catalog')
    timestamp = format_timestamp(service.checked_utc)
    if isinstance(timestamp, str) and ' | ' in timestamp:
        for instant in timestamp.split(' | '):
            date_time, abbreviation = instant.rsplit(' ', 1)
            print(f'[{abbreviation}] {_safe_text(date_time)}')
    else:
        print('Observation time: unavailable')
    print('\nScope: APKs with an effective date and registry match.')
    print('       Profile filters not applied.')

    _overview_section('Catalog')
    catalog = _overview_read('Reading catalog...', service.catalog_summary)
    for key, label in (
        ('android_catalog_records', 'Android records'), ('apk_records', 'APK records'),
        ('missing_effective_date', 'Missing date'), ('missing_registry', 'Missing registry match'),
    ):
        _overview_stat(label, _overview_count(catalog.get(key)))
    for key, label in (('earliest_effective_date', 'First provider date'),
                       ('latest_effective_date', 'Latest provider date')):
        value = catalog.get(key)
        try:
            parsed = date.fromisoformat(str(value)[:10]) if value is not None else None
        except ValueError:
            parsed = None
        _overview_stat(label, f'{parsed.month}-{parsed.day}-{parsed.year}' if parsed else None)

    _overview_section('Family coverage')
    family = _overview_read('Reading family coverage...', service.label_summary)
    selected = _overview_count(family.get('selected_apks'))
    known = _overview_count(family.get('known_family_samples'))
    unknown = _overview_count(family.get('unknown_family_samples'))
    consistent = selected is not None and known is not None and unknown is not None and known + unknown == selected
    _overview_stat('Selected APKs', selected)
    for label, count in (('Known-family samples', known), ('Unknown-family samples', unknown)):
        if consistent and selected > 0:
            value = f'{count:,} ({Decimal(count) * 100 / Decimal(selected):.1f}%)'
        else:
            value = f'{count:,} (percentage unavailable)' if count is not None else None
        _overview_stat(label, value)
    _overview_stat('Known families', _overview_count(family.get('observed_known_families')))
    if not consistent:
        print('Family coverage consistency: unavailable or counts do not match selected APKs.')

    _overview_section('Malware types')
    rows = _overview_read('Reading malware types...', lambda: _overview_types(service))
    _show_overview_types(rows, selected)

    _overview_section('Notes')
    _overview_stat('Training eligibility', 'Not evaluated')
    _overview_stat('Evidence coverage', 'Explore data > Option 4')
    print('Provider dates are not verified collection or deployment dates.')
    print('APK catalog records do not establish locally verified APK file availability.')


def browse_families(service):
    kinds = ['family', 'type', 'family', 'relationship', 'family']
    while True:
        choice = mu.display_menu(['Most common families', 'Malware types', 'Low support families (n < 3)',
                                  'Family-to-type relationships', 'Unknown family population'],
                                 title='Malware families and types', exit_label='Back')
        if choice == 0:
            return
        term = 'unknown' if choice == 5 else input('Exact label filter (Enter = all; 0 = back): ').strip()
        if term == '0':
            continue
        page = 0
        while True:
            header(service, f'Family/type distribution · page {page + 1}')
            rows = service.browse(kind=kinds[choice-1], term=term, low_support=choice == 3, page=page)
            show_rows(rows[:PAGE_SIZE])
            if not rows:
                du.print_info('No matching labels in this population.')
            options = ['Change filter / Back']
            if len(rows) > PAGE_SIZE:
                options.append('Next page')
            if page:
                options.append('Previous page')
            action = mu.display_menu(options, title='Browse pages', exit_label='Back')
            if action in (0, 1):
                break
            page += 1 if options[action-1] == 'Next page' else -1


def show_quality(service):
    header(service, 'Data quality and unknown labels')
    show_fields(service.quality())
    catalog = service.catalog_summary()
    show_fields({k: catalog[k] for k in ('android_catalog_records', 'apk_records', 'missing_effective_date', 'missing_registry')})
    du.print_info('Missingness totals overlap. Profile time, support and authority exclusions are not evaluated here.')
    du.print_info('Raw/canonical disagreement is alias-aware review evidence, not proof of an incorrect taxonomy.')
    du.print_info('Weak source label kinds are diagnostic counts; profile canonical-label overrides may admit some rows.')


def show_coverage(service, export_path):
    header(service, 'Antivirus and permission coverage')
    try:
        show_fields(service.av_coverage())
        show_fields(service.av_engines())
    except ExplorerUnavailable as exc:
        du.print_warning(str(exc))
    du.print_info('AV record presence is observed evidence, not usable engine coverage. Lifecycle readiness: not computed; requires run-scoped scoring.')
    show_fields(service.permission_coverage(export_path))
    du.print_info('Uncovered does not mean no permissions. Legacy PI reads remain governed; no features are fitted.')


def find_sample(service, export_path):
    value = input('Exact sample ID or SHA-256 (0 = back): ').strip()
    if value == '0':
        return
    rows = service.lookup(value)
    header(service, 'Exact Android sample lookup')
    if not rows:
        du.print_info('No matching Android catalog record.')
        return
    if len(rows) != 1:
        du.print_warning('Identity is ambiguous; inspect source integrity before using this sample.')
        return
    row = rows[0]
    show_fields(row)
    missing = [key for key, value in row.items() if value is None or value == '']
    if missing:
        du.print_warning('Missing metadata: ' + ', '.join(missing))
    from obsidiandroid.common.family_label_semantics import is_family_label_conflict
    if is_family_label_conflict(row['source_family'], row['canonical_family']):
        du.print_warning('Raw/canonical label disagreement needs review.')
    try:
        show_fields(service.av_coverage(row['sample_id']))
    except ExplorerUnavailable as exc:
        du.print_warning(str(exc))
    show_fields(service.permission_coverage(export_path, sample=row))


def launch_data_explorer():
    export_path = os.environ.get('OBSIDIANDROID_EXPLORER_PI_V2_EXPORT', '').strip()
    while True:
        choice = mu.display_menu(['Dataset overview', 'Malware families and types',
                                  'Data quality and unknown labels', 'Antivirus and permission coverage',
                                  'Find a sample by ID or SHA-256', 'Integrated research — retained evidence'],
                                 title='Explore Android data', exit_label='Return to Main Menu',
                                 action_hint='', selection_prompt='Enter your selection: ',
                                 context_lines=[('SOURCE', 'Live read-only catalog; saved runs are unchanged.')])
        if choice == 0:
            return 0
        try:
            if choice == 6:
                from obsidiandroid.cli.integrated_research import launch_integrated_research
                launch_integrated_research()
                continue
            if choice in (4, 5) and not export_path:
                export_path = input('Approved PI V2 export path (Enter = unavailable; 0 = back): ').strip()
                if export_path == '0':
                    export_path = ''
                    continue
            with explorer_session() as service:
                if choice == 1:
                    show_overview(service)
                elif choice == 2:
                    browse_families(service)
                elif choice == 3:
                    show_quality(service)
                elif choice == 4:
                    show_coverage(service, export_path)
                elif choice == 5:
                    find_sample(service, export_path)
        except (ExplorerUnavailable, ValueError) as exc:
            du.print_warning(str(exc))
        except (KeyboardInterrupt, EOFError):
            du.print_info('Explorer action cancelled.')
