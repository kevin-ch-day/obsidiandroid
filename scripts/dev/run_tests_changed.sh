#!/usr/bin/env bash
# Run pytest for files touched vs a base ref (default: origin/main).
# Falls back to import smoke when no mapped tests are found.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

BASE_REF="${1:-origin/main}"
MARKER_EXPR='not (slow or integration or heavy or contract)'

collect_targets() {
  local path base stem candidates
  declare -A seen=()

  while IFS= read -r path; do
    [[ -z "${path}" ]] && continue
    case "${path}" in
      tests/test_*.py)
        seen["${path}"]=1
        ;;
      src/obsidiandroid/*.py | src/obsidiandroid/*/*.py | src/obsidiandroid/*/*/*.py)
        base="$(basename "${path}" .py)"
        if [[ "${base}" == "__init__" ]]; then
          continue
        fi
        for candidate in tests/test_"${base}".py tests/test_*"${base}"*.py; do
          if [[ -f "${candidate}" ]]; then
            seen["${candidate}"]=1
          fi
        done
        ;;
      scripts/*.py | scripts/*/*.py | config/*.py)
        base="$(basename "${path}" .py)"
        for candidate in tests/test_"${base}".py tests/test_*"${base}"*.py; do
          if [[ -f "${candidate}" ]]; then
            seen["${candidate}"]=1
          fi
        done
        ;;
    esac
  done < <(git diff --name-only "${BASE_REF}"...HEAD 2>/dev/null || true)

  for path in "${!seen[@]}"; do
    printf '%s\n' "${path}"
  done | sort -u
}

mapfile -t TARGETS < <(collect_targets)

if ((${#TARGETS[@]} == 0)); then
  echo "[test-changed] No mapped tests for diff vs ${BASE_REF}; running import smoke only."
  exec python scripts/dev/check_import_surface.py
fi

echo "[test-changed] Running ${#TARGETS[@]} test module(s) vs ${BASE_REF}:"
printf '  - %s\n' "${TARGETS[@]}"
exec pytest -q -m "${MARKER_EXPR}" "${TARGETS[@]}"
