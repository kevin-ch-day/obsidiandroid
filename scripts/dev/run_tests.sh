#!/usr/bin/env bash
# Default: fast test selection (excludes `slow`, `integration`, `heavy`, and `contract`; see tests/conftest.py and pyproject.toml [tool.pytest.ini_options]).
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/run_pytest.sh" "$@"
