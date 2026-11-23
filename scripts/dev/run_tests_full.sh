#!/usr/bin/env bash
# Full suite: all tests, overriding the default fast-loop marker filter.
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/run_pytest.sh" -o addopts="" "$@"
