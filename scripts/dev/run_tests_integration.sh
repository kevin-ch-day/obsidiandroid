#!/usr/bin/env bash
# Pipeline/menu integration lane: partial run_pipeline and subprocess smoke tests.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec pytest -q -m "integration and not (slow or heavy or contract or pipeline_heavy)" "$@"
