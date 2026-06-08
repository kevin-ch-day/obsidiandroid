#!/usr/bin/env bash
# Full partial run_pipeline integration lane (slowest orchestration tests).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec pytest -q -m "pipeline_heavy" "$@"
