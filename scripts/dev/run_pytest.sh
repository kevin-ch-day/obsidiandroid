#!/usr/bin/env bash
# Run a pytest lane with one interpreter and the active source checkout.
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${DEV_DIR}/../.." && pwd)"
venv_bin="$("${DEV_DIR}/checkout_venv.sh")"
python=python
if [[ -n "${venv_bin}" ]]; then
    python="${venv_bin}/python"
fi

cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${python}" -m pytest -q "$@"
