#!/usr/bin/env bash
# Prepare a source checkout and hand arguments to the shared operator command.
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${DEV_DIR}/../.." && pwd)"
venv_bin="$("${DEV_DIR}/checkout_venv.sh")"
if [[ -z "${venv_bin}" ]]; then
    echo "Missing checkout virtual environment. Run ./setup.sh first." >&2
    exit 1
fi

cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${venv_bin}/python" -m obsidiandroid.cli "$@"
