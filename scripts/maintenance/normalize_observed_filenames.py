"""Maintenance tool to normalize clearly synthetic catalog filenames.

This script only targets safe cleanup patterns that commonly leak in from IOC
feeds or transport encoding:

- HTML entities like ``&igrave;``
- percent-encoded fragments like ``%20``
- duplicated extensions like ``.apk.apk``
- trailing punctuation after the extension like ``.apk-``
- literal ``\\r`` / ``\\n`` / ``\\t`` fragments
- actual control characters and excess whitespace

It intentionally does not strip all Unicode or invent a filename from labels or
URLs. Non-ASCII filenames can still be legitimate observed names.
"""

from __future__ import annotations

import argparse
import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import sys
import unicodedata
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database import db_engine


_SUSPICIOUS_PATTERN = re.compile(
    r"(&[A-Za-z#0-9]+;)|(%[0-9A-Fa-f]{2})|(\.apk\.apk$)|(\.apk-$)|(\\[rnt])|([\x00-\x1f\x7f])|(\s+\.apk$)"
)
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PERCENT_ESCAPE_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
_ASCII_FILENAME_PATTERN = re.compile(r"^[ -~]+$")


@dataclass(frozen=True)
class FilenameFixCandidate:
    """One filename normalization candidate."""

    sample_id: int
    observed_filename: str
    normalized_filename: str | None
    source_batch_label: str | None


@dataclass(frozen=True)
class FilenameNormalizeSummary:
    """Summary for one normalization run."""

    candidate_rows: int
    updated_rows: int


def _scalar(query: str, params: Iterable[object] = ()) -> int:
    """Return the first scalar value from a query as an integer."""
    _cols, rows = db_engine.execute_query(
        query,
        params=tuple(params),
        fetch=True,
        return_columns=True,
    )
    if not rows:
        return 0
    return int(rows[0][0] or 0)


def normalize_observed_filename(value: str | None) -> str | None:
    """Return a conservative normalized filename or the original semantic value."""
    if value is None:
        return None

    normalized = value
    normalized = html.unescape(normalized)
    if _PERCENT_ESCAPE_PATTERN.search(normalized):
        normalized = unquote(normalized)
    normalized = normalized.replace("\\r", " ").replace("\\n", " ").replace("\\t", " ")
    normalized = _CONTROL_CHAR_PATTERN.sub(" ", normalized)
    normalized = normalized.strip()
    normalized = re.sub(r"\s+\.apk$", ".apk", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\.apk-+$", ".apk", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(\.apk)+$", ".apk", normalized, flags=re.IGNORECASE)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized or None


def is_legitimate_multilingual_filename(value: str | None) -> bool:
    """Return True when a filename contains Unicode text but no transport/corruption signal.

    This protects real multilingual observed filenames such as Arabic, Chinese,
    Turkish, or stylized Unicode titles from being treated as cleanup debt.
    """
    if value is None:
        return False
    if _ASCII_FILENAME_PATTERN.fullmatch(value):
        return False
    if _SUSPICIOUS_PATTERN.search(value) or value != value.strip():
        return False
    for char in value:
        if ord(char) < 128:
            continue
        category = unicodedata.category(char)
        if category.startswith(("L", "M", "N", "S", "P")):
            continue
        return False
    return True


def is_suspicious_filename(value: str | None) -> bool:
    """Return True when the filename matches a safe normalization pattern."""
    if value is None:
        return False
    if is_legitimate_multilingual_filename(value):
        return False
    return bool(_SUSPICIOUS_PATTERN.search(value) or value != value.strip())


def load_candidates(*, limit: int | None = None) -> list[FilenameFixCandidate]:
    """Load Android observed_filename rows that match safe normalization patterns."""
    sql = """
        SELECT sample_id, observed_filename, source_batch_label
        FROM malware_sample_catalog
        WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
          AND observed_filename IS NOT NULL
    """
    sql += " ORDER BY sample_id"
    _cols, rows = db_engine.execute_query(sql, fetch=True, return_columns=True)
    candidates: list[FilenameFixCandidate] = []
    for sample_id, observed_filename, source_batch_label in rows:
        if not is_suspicious_filename(observed_filename):
            continue
        normalized = normalize_observed_filename(observed_filename)
        if normalized == observed_filename:
            continue
        candidates.append(
            FilenameFixCandidate(
                sample_id=int(sample_id),
                observed_filename=str(observed_filename),
                normalized_filename=normalized,
                source_batch_label=str(source_batch_label) if source_batch_label is not None else None,
            )
        )
        if limit is not None and len(candidates) >= int(limit):
            break
    return candidates


def apply_candidates(candidates: list[FilenameFixCandidate]) -> int:
    """Persist candidate normalizations."""
    if not candidates:
        return 0
    with db_engine.database_connection() as conn:
        cur = conn.cursor()
        updated_rows = 0
        for candidate in candidates:
            cur.execute(
                """
                UPDATE malware_sample_catalog
                SET observed_filename = %s
                WHERE sample_id = %s
                """,
                (candidate.normalized_filename, candidate.sample_id),
            )
            updated_rows += int(cur.rowcount or 0)
        cur.close()
    return updated_rows


def normalize_catalog_observed_filenames(*, commit: bool, limit: int | None = None) -> FilenameNormalizeSummary:
    """Load and optionally persist safe observed_filename normalizations."""
    candidates = load_candidates(limit=limit)
    updated_rows = apply_candidates(candidates) if commit else 0
    return FilenameNormalizeSummary(
        candidate_rows=len(candidates),
        updated_rows=updated_rows,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Normalize clearly synthetic malware_sample_catalog observed_filename values."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply the normalization updates. Without this flag the script is a dry run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for candidate inspection or bounded updates.",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    args = build_arg_parser().parse_args()
    candidates = load_candidates(limit=args.limit)
    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"mode={mode}")
    print(f"candidate_rows={len(candidates)}")
    for candidate in candidates[:20]:
        print(
            f"sample_id={candidate.sample_id} | batch={candidate.source_batch_label or '<blank>'} "
            f"| before={candidate.observed_filename!r} | after={candidate.normalized_filename!r}"
        )
    updated_rows = apply_candidates(candidates) if args.commit else 0
    print(f"updated_rows={updated_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
