#!/usr/bin/env bash
# Map committed and local changes against a base ref to fast pytest modules.
set -euo pipefail

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${DEV_DIR}/../.." && pwd)"
cd "${ROOT}"

BASE_REF="${1:-origin/main}"
if ! diff_base="$(git merge-base -- "${BASE_REF}" HEAD 2>/dev/null)"; then
    echo "[test-changed] Cannot resolve base ref: ${BASE_REF}" >&2
    exit 2
fi

mapfile -d '' -t changed_paths < <(
    git diff --name-only -z "${diff_base}" --
    git ls-files --others --exclude-standard -z
)
mapfile -d '' -t test_paths < <(git ls-files --cached --others --exclude-standard -z -- tests)

declare -A seen=()
for path in "${changed_paths[@]}"; do
    case "${path}" in
        tests/test_*.py | tests/*/test_*.py)
            if [[ -f "${path}" ]]; then
                seen["${path}"]=1
            fi
            ;;
        src/obsidiandroid/*.py | scripts/*.py | config/*.py)
            stem="$(basename "${path}" .py)"
            if [[ "${stem}" == "__init__" ]]; then
                continue
            fi
            for candidate in "${test_paths[@]}"; do
                if [[ "${candidate##*/}" == test_*"${stem}"*.py && -f "${candidate}" ]]; then
                    seen["${candidate}"]=1
                fi
            done
            ;;
    esac
done

if ((${#seen[@]} == 0)); then
    echo "[test-changed] No mapped tests for diff vs ${BASE_REF}; running import smoke only."
    venv_bin="$("${DEV_DIR}/checkout_venv.sh")"
    python=python
    if [[ -n "${venv_bin}" ]]; then
        python="${venv_bin}/python"
    fi
    exec "${python}" scripts/dev/check_import_surface.py
fi

mapfile -t targets < <(printf '%s\n' "${!seen[@]}" | sort)
echo "[test-changed] Running ${#targets[@]} test module(s) vs ${BASE_REF}:"
printf '  - %s\n' "${targets[@]}"
exec "${DEV_DIR}/run_pytest.sh" "${targets[@]}"
