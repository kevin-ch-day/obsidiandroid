#!/usr/bin/env bash
# Pipeline/menu integration lane: partial run_pipeline and subprocess smoke tests.
set -euo pipefail
exec "$(dirname "${BASH_SOURCE[0]}")/run_pytest.sh" -m "integration and not (slow or heavy or contract or pipeline_heavy)" "$@"
