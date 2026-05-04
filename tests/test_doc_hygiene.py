"""Guardrail: operational docs must not reintroduce removed phantom paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_doc_hygiene_exits_zero() -> None:
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "dev" / "check_doc_hygiene.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
