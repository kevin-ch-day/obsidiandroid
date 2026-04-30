#!/usr/bin/env bash
# Install dependencies in the repo virtual environment and run unit tests.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "Missing virtual environment at ${VENV_DIR}."
    echo "Run ./setup.sh first."
    exit 1
fi

"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"
"${VENV_DIR}/bin/python" -m pytest -q "$@"
