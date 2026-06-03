#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-2720}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_PATH="${PROJECT_DIR}/apps/espac_lci_pipeline_marimo.py"

WINDOWS_PYTHON="${PROJECT_DIR}/.venv/Scripts/python.exe"
POSIX_PYTHON="${PROJECT_DIR}/.venv/bin/python"

if [[ -x "${WINDOWS_PYTHON}" ]]; then
  PYTHON_BIN="${WINDOWS_PYTHON}"
elif [[ -x "${POSIX_PYTHON}" ]]; then
  PYTHON_BIN="${POSIX_PYTHON}"
else
  echo "Missing venv python in ${PROJECT_DIR}/.venv" >&2
  exit 1
fi

if [[ ! -f "${APP_PATH}" ]]; then
  echo "Missing app file: ${APP_PATH}" >&2
  exit 1
fi

kill_stale_marimo() {
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command \
      "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'marimo' -and \$_.CommandLine -match 'espac_lci_pipeline_marimo.py' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" \
      >/dev/null 2>&1 || true
  elif command -v pkill >/dev/null 2>&1; then
    pkill -f 'marimo.*espac_lci_pipeline_marimo.py' >/dev/null 2>&1 || true
  fi
}

kill_stale_marimo
trap kill_stale_marimo EXIT

echo "Launching app on http://127.0.0.1:${PORT}/"
echo "Press Ctrl+C to stop."

cd "${PROJECT_DIR}"
exec "${PYTHON_BIN}" -m marimo run --host 127.0.0.1 --port "${PORT}" --show-tracebacks "${APP_PATH}"
