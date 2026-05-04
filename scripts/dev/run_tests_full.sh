#!/usr/bin/env bash
# Full suite: all tests including `slow` integration modules.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
exec pytest -q -m "slow or not slow" "$@"
