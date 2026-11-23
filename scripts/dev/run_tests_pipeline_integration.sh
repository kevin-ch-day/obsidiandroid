#!/usr/bin/env bash
# Full partial run_pipeline integration lane (slowest orchestration tests).
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/run_pytest.sh" -m "pipeline_heavy" "$@"
