"""Bounded, read-only Android catalog exploration; no pipeline dependencies."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re

from obsidiandroid.common.family_label_semantics import family_identity_sql
from .cohort_sql_fragments import latest_family_resolution_subquery

PAGE_SIZE = 20
UNKNOWN = "('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n/a')"
FAMILY = "COALESCE(NULLIF(TRIM(f.family_name), ''), 'unknown')"
TYPE = "COALESCE(NULLIF(TRIM(t.type_slug), ''), 'unknown')"
KNOWN = f"LOWER(TRIM({FAMILY})) NOT IN {UNKNOWN}"
APK = "m.file_extension = 'apk'"
DATED = "COALESCE(m.vt_first_seen_itw_date, m.vt_first_submission_at_utc)"
REGISTRY = "EXISTS (SELECT 1 FROM malware_artifact_hash_registry h WHERE h.sha256=m.sha256)"
POPULATION = f"m.platform='android' AND {APK} AND {DATED} IS NOT NULL AND {REGISTRY}"
JOINS = f"""FROM malware_sample_catalog m
LEFT JOIN {latest_family_resolution_subquery()} v ON v.sample_id=m.sample_id
LEFT JOIN (
    SELECT DISTINCT family_id, family_name, primary_type_id,
           LOWER(family_slug) AS family_slug_lc
    FROM android_malware_family
) f ON f.family_slug_lc=v.resolved_family_lc
LEFT JOIN android_malware_type t ON t.type_id=f.primary_type_id"""
POPULATION_NOTE = "Android APKs with an effective date and hash-registry match; no profile time/support/label gates applied."


class ExplorerUnavailable(RuntimeError):
    """A source could not be read; this is never an empty population."""


@contextmanager
def explorer_session():
    """Use the existing source identity with server-enforced read-only rollback."""
    from . import db_engine
    conn = None
    try:
        conn = db_engine._get_connection()
        conn.start_transaction(readonly=True)
        yield Explorer(conn)
    except ExplorerUnavailable:
        raise
    except Exception as exc:
        raise ExplorerUnavailable(
            f"Catalog unavailable ({type(exc).__name__}, code {getattr(exc, 'errno', 'unknown')}). "
            "Check source connectivity and SELECT privileges."
        ) from exc
    finally:
        if conn is not None:
            try:
                conn.rollback()
            finally:
                conn.close()


class Explorer:
    """Aggregate queries and parameterized pages on one read-only transaction."""

    def __init__(self, connection):
        self.connection = connection
        self.checked_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')

    def query(self, sql, params=()):
        if not sql.lstrip().upper().startswith('SELECT ') or ';' in sql:
            raise ValueError('Explorer accepts one SELECT only')
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        except Exception as exc:
            raise ExplorerUnavailable(
                f"Source unavailable ({type(exc).__name__}, code {getattr(exc, 'errno', 'unknown')}); "
                "no count inferred."
            ) from exc
        finally:
            cursor.close()

    def catalog_summary(self):
        """Return cheap catalog counts before the taxonomy query completes."""
        return self.query(f"""SELECT COUNT(*) AS android_catalog_records,
            COALESCE(SUM({APK}),0) AS apk_records,
            COALESCE(SUM({DATED} IS NULL),0) AS missing_effective_date,
            COALESCE(SUM(NOT {REGISTRY}),0) AS missing_registry,
            MIN({DATED}) AS earliest_effective_date, MAX({DATED}) AS latest_effective_date
            FROM malware_sample_catalog m WHERE m.platform='android'""")[0]
    def label_summary(self):
        """Count canonical labels for the selected APK population."""
        return self.query(f"""SELECT COUNT(*) AS selected_apks,
            COALESCE(SUM({KNOWN}),0) AS known_family_samples,
            COALESCE(SUM(NOT ({KNOWN})),0) AS unknown_family_samples,
            COUNT(DISTINCT CASE WHEN {KNOWN} THEN f.family_id END) AS observed_known_families
            {JOINS} WHERE {POPULATION}""")[0]
    def overview(self):
        return {**self.catalog_summary(), **self.label_summary()}

    def sources(self):
        return self.query(f"""SELECT COALESCE(NULLIF(TRIM(m.source_batch_label),''),'unknown') AS source,
            COUNT(*) AS samples FROM malware_sample_catalog m WHERE {POPULATION}
            GROUP BY source ORDER BY samples DESC, source LIMIT 20""")

    def browse(self, *, kind='family', term='', low_support=False, page=0):
        if kind not in {'family', 'type', 'relationship'}:
            raise ValueError('Unknown distribution kind')
        if not isinstance(page, int) or not 0 <= page <= 10000:
            raise ValueError('Invalid page')
        if len(term) > 160:
            raise ValueError('Filter is too long')
        expression = TYPE if kind == 'type' else FAMILY
        fields = f'{expression} AS label'
        grouping = 'label'
        if kind == 'relationship':
            fields += f', {TYPE} AS malware_type'
            grouping += ', malware_type'
        # Exact filters avoid wildcard ambiguity and are always bound parameters.
        condition = ' AND ' + expression + ' = %s' if term else ''
        params = (term,) if term else ()
        having = ' HAVING COUNT(*) < 3' if low_support else ''
        return self.query(f"""SELECT {fields}, COUNT(*) AS samples {JOINS}
            WHERE {POPULATION}{condition} GROUP BY {grouping}{having}
            ORDER BY samples {'ASC' if low_support else 'DESC'}, {grouping}
            LIMIT %s OFFSET %s""", params + (PAGE_SIZE + 1, page * PAGE_SIZE))

    def quality(self):
        raw, canonical = family_identity_sql('m.family_label'), family_identity_sql('f.family_name')
        conflict = (f"{KNOWN} AND {raw} NOT IN ('','unknown','generic','unclassified','unlabeled',"
                    f"'other','unmapped','none','null','nan','n_a') AND {raw} <> {canonical} "
                    "AND LOWER(TRIM(m.family_label)) NOT REGEXP "
                    "'^(?:[0-9]+|(?:family|unresolved([ _-]*family)?)[ _:=#-]*(id[ _:=#-]*)?[0-9]+)$'")
        return self.query(f"""SELECT COUNT(*) AS selected_apks,
            COALESCE(SUM(NOT ({KNOWN})),0) AS unknown_or_unmapped_family,
            COALESCE(SUM(COALESCE(TRIM(m.family_label),'')=''),0) AS missing_raw_family,
            COALESCE(SUM(LOWER(TRIM(COALESCE(m.sample_label_kind,''))) IN
                ('filename','hash_like','opaque_string','unclassified')),0) AS weak_source_label_kind,
            COALESCE(SUM(COALESCE(TRIM(m.sample_label_kind),'')=''),0) AS missing_source_label_kind,
            COALESCE(SUM({conflict}),0) AS raw_canonical_disagreements,
            COALESCE(SUM(COALESCE(TRIM(m.android_package_name),'')=''),0) AS missing_package,
            COALESCE(SUM(m.vt_first_seen_itw_date > m.vt_first_submission_at_utc),0) AS itw_after_submission_review
            {JOINS} WHERE {POPULATION}""")[0]

    def av_engines(self, sample_id=None):
        """Count nonblank observed engine columns, without computing lifecycle scores."""
        columns = self.query("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                             "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION LIMIT 257",
                             ('virustotal_sample_vendor_engine_verdicts',))
        if not columns or len(columns) > 256:
            raise ExplorerUnavailable('AV engine schema unavailable or exceeds browse bound.')
        names = [r['COLUMN_NAME'] for r in columns
                 if r['COLUMN_NAME'] not in {'sample_id', 'updated_at'}]
        if any(not re.fullmatch(r'[a-zA-Z0-9_]+', n) for n in names):
            raise ExplorerUnavailable('AV engine schema contains unsupported identifiers.')
        if not names:
            raise ExplorerUnavailable('No AV engine columns visible.')
        fields = ', '.join(f"COALESCE(MAX(NULLIF(TRIM(e.`{n}`),'') IS NOT NULL),0) AS `{n}`" for n in names)
        scope = POPULATION if sample_id is None else "m.platform='android' AND m.sample_id=%s"
        row = self.query(f"SELECT {fields} FROM virustotal_sample_vendor_engine_verdicts e "
                         f"JOIN malware_sample_catalog m ON m.sample_id=e.sample_id WHERE {scope}",
                         () if sample_id is None else (sample_id,))[0]
        return {'observed_nonblank_engine_columns': sum(int(v or 0) for v in row.values()),
                'visible_engine_columns': len(names), 'lifecycle_ready_engines': None}

    def av_coverage(self, sample_id=None):
        clause = ' AND m.sample_id=%s' if sample_id is not None else ''
        return self.query(f"""SELECT COUNT(*) AS population,
            COALESCE(SUM(EXISTS (SELECT 1 FROM virustotal_sample_scan_summary s
                WHERE s.sample_id=m.sample_id)),0) AS with_scan_summary,
            COALESCE(SUM(EXISTS (SELECT 1 FROM virustotal_sample_vendor_engine_verdicts e
                WHERE e.sample_id=m.sample_id)),0) AS with_engine_verdict_record
            FROM malware_sample_catalog m WHERE m.platform='android'
            {'AND '+POPULATION if sample_id is None else ''}{clause}""",
            (sample_id,) if sample_id is not None else ())[0]

    def lookup(self, value):
        value = value.strip()
        if re.fullmatch(r'[0-9a-fA-F]{64}', value):
            condition, param = 'm.sha256=%s', value.lower()
        elif re.fullmatch(r'[1-9][0-9]{0,18}', value):
            condition, param = 'm.sample_id=%s', int(value)
        else:
            raise ValueError('Enter an exact positive sample ID or 64-character SHA-256.')
        return self.query(f"""SELECT m.sample_id, m.sha256, m.file_extension,
            m.android_package_name, m.sample_label_kind, m.android_min_sdk, m.android_target_sdk,
            m.family_label AS source_family,
            {FAMILY} AS canonical_family, {TYPE} AS malware_type,
            m.vt_first_seen_itw_date, m.vt_first_submission_at_utc,
            m.source_batch_label, ({KNOWN}) AS known_family,
            ({DATED} IS NOT NULL AND {APK} AND {REGISTRY}) AS in_explorer_population
            {JOINS} WHERE m.platform='android' AND {condition} LIMIT 2""", (param,))

    def permission_coverage(self, export_path, sample=None):
        """Validate root-anchored bytes; intersect exact identities, never fit features."""
        if not export_path:
            return {'status': 'Unavailable: choose an approved export file; approval is checked independently.'}
        from obsidiandroid.orchestration import permission_v2_export as v2
        try:
            _, _, export = v2._checked_export(Path(export_path))
            rows = export['samples']
            pairs = [(r['sample_id'], r['sha256']) for r in rows]
            if len(set(pairs)) != len(pairs):
                raise ValueError('Duplicate export identities')
            if sample is not None:
                covered = (sample['sample_id'], sample['sha256']) in pairs
                return {'status': 'Approved export coverage' if covered else 'Uncovered; permissions unknown',
                        'covered': int(covered), 'evidence': 'PROVIDER_REPORTED_UNRESOLVED' if covered else 'Unavailable',
                        'training_authority': 'Not granted by coverage'}
            # At most 200 exact identities per query; never load the whole catalog.
            matched = 0
            for start in range(0, len(pairs), 200):
                batch = pairs[start:start + 200]
                predicates = ' OR '.join('(m.sample_id=%s AND BINARY m.sha256=%s)' for _ in batch)
                result = self.query(f'SELECT COUNT(*) AS n FROM malware_sample_catalog m WHERE {POPULATION} AND ({predicates})',
                                    tuple(v for pair in batch for v in pair))
                matched += int(result[0]['n'])
            total = int(self.query(f'SELECT COUNT(*) AS n FROM malware_sample_catalog m WHERE {POPULATION}')[0]['n'])
            return {'status': 'Independently approved export', 'export_samples': len(pairs),
                    'selected_apks': total, 'covered': matched, 'uncovered_permissions_unknown': total - matched,
                    'evidence': 'PROVIDER_REPORTED_UNRESOLVED', 'training_authority': 'Not granted by coverage'}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return {'status': f'Unavailable: approval/export validation failed ({type(exc).__name__})'}
