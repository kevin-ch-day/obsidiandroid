#!/usr/bin/env bash
# Thin wrapper: canonical script is scripts/dev/run_tests.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT}/scripts/dev/run_tests.sh" "$@"
