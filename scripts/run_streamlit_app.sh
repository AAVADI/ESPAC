#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-8501}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_PATH="${PROJECT_DIR}/apps/espac_lci_pipeline_streamlit.py"

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

kill_stale_streamlit() {
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command \
      "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'streamlit' -and \$_.CommandLine -match 'espac_lci_pipeline_streamlit.py' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" \
      >/dev/null 2>&1 || true
  elif command -v pkill >/dev/null 2>&1; then
    pkill -f 'streamlit.*espac_lci_pipeline_streamlit.py' >/dev/null 2>&1 || true
  fi
}

kill_stale_streamlit
trap kill_stale_streamlit EXIT

echo "Launching Streamlit app on http://127.0.0.1:${PORT}/"
echo "Press Ctrl+C to stop."

cd "${PROJECT_DIR}"
exec "${PYTHON_BIN}" -m streamlit run "${APP_PATH}" --server.address 127.0.0.1 --server.port "${PORT}" --server.headless true
