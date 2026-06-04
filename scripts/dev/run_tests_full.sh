#!/usr/bin/env bash
# Full suite: all tests, overriding the default fast-loop marker filter.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec pytest -q -o addopts="--basetemp=.pytest_tmp" "$@"
