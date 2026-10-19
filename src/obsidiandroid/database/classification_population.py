"""Bounded metadata census for the current major-family profile, not fit admission."""
from .data_explorer import explorer_session
from .db_sample_metadata_fetchers import _execute_samples_by_type_query


def major_family_population(profile):
    """Reuse loader SQL in a read-only transaction; never read permission observations.

    Counts precede runtime dataset, feature, confidence and split checks. In
    particular an AV source row does not prove usable or authorized features.
    """
    if profile.get('profile_id') != 'android_malware_major_families':
        raise ValueError('Population census is not implemented for this profile')
    gates = profile.get('cohort_gates', {})
    query, params = _execute_samples_by_type_query(
        output_columns='sample_id, family_id, family_canonical',
        type_slug=profile.get('type_slug_filter'),
        require_mapped_family=gates.get('require_mapped_family', True),
        require_sha256=gates.get('require_sha256', True),
        allow_missing_package_name=gates.get('allow_missing_package_name', True),
        exclude_unknown_type_slug=gates.get('exclude_unknown_type_slug', False),
        exclude_weak_label_kinds=gates.get('exclude_weak_label_kinds', False),
        exclude_family_label_conflicts=gates.get('exclude_family_label_conflicts', False),
        effective_time_start_utc=gates.get('time_window_start_utc'),
        effective_time_end_utc=gates.get('time_window_end_utc'),
        include_family_canonical=tuple(gates.get('include_families', [])),
        query_only=True,
    )
    # Reject unsupported membership changes rather than silently count another cohort.
    if any(gates.get(k) for k in ('limit', 'family_cap', 'type_cap', 'type_cap_by_slug', 'exclude_families')):
        raise ValueError('Population census does not support capped or excluded-family profiles')
    if gates.get('support_floor_mode') != 'benchmark_eligibility':
        raise ValueError('Population census requires benchmark eligibility support semantics')
    with explorer_session() as source:
        source.connection.cmd_query('SET SESSION max_statement_time=45')
        rows = source.query(f"""SELECT c.family_id, c.family_canonical,
            COUNT(*) AS samples,
            SUM(EXISTS(SELECT 1 FROM virustotal_sample_vendor_engine_verdicts a
                WHERE a.sample_id=c.sample_id)) AS av_source_rows
            FROM ({query}) c GROUP BY c.family_id, c.family_canonical
            ORDER BY samples DESC, c.family_id LIMIT 1001""", params)
        if len(rows) > 1000:
            raise ValueError('Family census exceeds the bounded result limit')
        return {'checked_utc': source.checked_utc, 'families': rows,
                'samples': sum(int(row['samples']) for row in rows),
                'av_source_rows': sum(int(row['av_source_rows']) for row in rows)}
