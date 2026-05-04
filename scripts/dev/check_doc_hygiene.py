#!/usr/bin/env python3
"""Fail if operational docs reintroduce known-removed phantom paths.

Scans a fixed allowlist of user-facing markdown files (not migration history docs).
Exits 0 when clean, 1 when a forbidden substring appears on a non-negating line.

Run from repo root: ``python scripts/dev/check_doc_hygiene.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Operator / guide docs only — exclude STRUCTURE_MIGRATION_PLAN, audits, historical notes.
_RELATIVE_PATHS = (
    "README.md",
    "docs/user_guide.md",
    "docs/operations_playbook.md",
    "docs/architecture.md",
    "docs/modeling_reference.md",
    "docs/developer_guide.md",
    "docs/data_sources.md",
    "docs/pipeline_staging_guide.md",
    "docs/README.md",
)

# Substrings that must not appear as live references (removed or never existed).
_FORBIDDEN = (
    "scripts/backfill_labels.py",
    "scripts/export_feature_snapshot.py",
    "scripts/update_vendor_scores.py",
    "utils/config_loader.py",
)

# Lines matching this are allowed to mention a forbidden fragment (e.g. "does not ship X").
_NEGATION_HINT = re.compile(
    r"\b(no|not|never|removed|phantom|exclude|without|missing|non-existent)\b",
    re.IGNORECASE,
)


def _line_allowed(line: str, fragment: str) -> bool:
    if fragment not in line:
        return True
    return bool(_NEGATION_HINT.search(line))


def main() -> int:
    violations: list[str] = []
    for rel in _RELATIVE_PATHS:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for frag in _FORBIDDEN:
                if frag not in line:
                    continue
                if _line_allowed(line, frag):
                    continue
                violations.append(f"{rel}:{lineno}: {frag!r}\n  {line.strip()}")

    if violations:
        print("Doc hygiene FAILED — phantom paths in operational docs:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("OK   doc hygiene (no phantom script/module paths in scanned docs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
