#!/usr/bin/env bash
# Thin wrapper: canonical script is scripts/dev/launch_startup_menu.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT}/scripts/dev/launch_startup_menu.sh" "$@"
