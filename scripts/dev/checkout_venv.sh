#!/usr/bin/env bash
# Print the checkout's venv bin directory, with a fallback for linked worktrees.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
local_bin="${ROOT}/.venv/bin"
if [[ -x "${local_bin}/python" ]]; then
    printf '%s\n' "${local_bin}"
elif common_git_dir="$(git -C "${ROOT}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
    shared_bin="$(dirname "${common_git_dir}")/.venv/bin"
    if [[ -x "${shared_bin}/python" ]]; then
        printf '%s\n' "${shared_bin}"
    fi
fi
