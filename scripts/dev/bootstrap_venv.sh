#!/usr/bin/env bash
# Set up the Fedora Python virtual environment for ObsidianDroid (canonical implementation).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON:-python3}"

cd "${ROOT_DIR}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python 3 was not found. Install it on Fedora with:"
    echo "  sudo dnf install python3 python3-pip python3-virtualenv"
    exit 1
fi

if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Fedora setup complete."
echo "Run the CLI with: ./run.sh"
