"""Published CCNCPS 2026 numbers may appear in tests only as labelled reference values.

The values were first committed in df88e67 (2026-04-29), before the frozen
benchmark run, and no retained run, warehouse row or backup reproduces them
(output/reports/ccncps2026_provenance_search_2026-10-19.md). Tests that use
them as formatting fixtures must import them from
``ccncps2026_published_reference`` so no test reads as a reproduction.
"""

from __future__ import annotations

import re
from pathlib import Path

import ccncps2026_published_reference as published

TESTS_DIR = Path(__file__).resolve().parent
_LITERAL = re.compile(
    r"(?<![\d.])(" + "|".join(re.escape(v) for v in published.PUBLISHED_VALUE_LITERALS) + r")(?!\d)"
)


def test_published_values_are_only_defined_in_the_reference_module() -> None:
    offenders = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if path.name in {"ccncps2026_published_reference.py", Path(__file__).name}:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _LITERAL.search(line):
                offenders.append(f"{path.relative_to(TESTS_DIR)}:{lineno}")
    assert not offenders, (
        "Use ccncps2026_published_reference instead of hard-coding published values: "
        + ", ".join(offenders)
    )


def test_reference_module_states_values_are_not_reproduced() -> None:
    assert published.NOT_REPRODUCED is True
    assert "not reproduced by any retained run" in (published.__doc__ or "")
