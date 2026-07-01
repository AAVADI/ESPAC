#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-2720}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELEGATE="${SCRIPT_DIR}/run_marimo_clean.sh"

if [[ ! -f "${DELEGATE}" ]]; then
  echo "Missing delegate script: ${DELEGATE}" >&2
  exit 1
fi

exec "${DELEGATE}" "${PORT}"
