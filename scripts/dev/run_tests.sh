#!/usr/bin/env bash
# Default: fast test selection (excludes `slow`, `integration`, `heavy`, and `contract`; see tests/conftest.py and pyproject.toml [tool.pytest.ini_options]).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec pytest -q -m "not (slow or integration or heavy or contract or pipeline_heavy)" "$@"
