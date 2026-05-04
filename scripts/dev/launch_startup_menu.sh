#!/usr/bin/env bash
# Launch the ObsidianDroid startup menu from the local Fedora virtual environment.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

cd "${ROOT_DIR}"

# Allow ``import obsidiandroid`` when the venv has no editable install yet.
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "Missing virtual environment at ${VENV_DIR}."
    echo "Run ./setup.sh first."
    exit 1
fi

exec "${VENV_DIR}/bin/python" -m utils.startup_menu "$@"
