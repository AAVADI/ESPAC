param(
  [int]$Port = 2720
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $project ".venv\Scripts\python.exe"
$app = Join-Path $project "apps\espac_lci_pipeline_marimo.py"

if (-not (Test-Path $python)) { throw "Missing venv python: $python" }
if (-not (Test-Path $app)) { throw "Missing app file: $app" }

# Kill all marimo python processes to avoid stale servers and wrong index pages.
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "marimo" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Launching app on http://127.0.0.1:$Port/"
Write-Host "Press Ctrl+C to stop."

try {
  & $python -m marimo run --host 127.0.0.1 --port $Port --show-tracebacks $app
}
finally {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "marimo" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

