#!/usr/bin/env bash
# Default: fast test selection (excludes `slow` modules; see tests/conftest.py and pytest.ini).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
exec pytest -q -m "not slow" "$@"
