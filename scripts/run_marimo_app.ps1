param(
  [int]$Port = 2720
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $project ".venv\Scripts\python.exe"
$app = Join-Path $project "apps\espac_lci_pipeline_marimo.py"
$ensureInputs = Join-Path $project "scripts\ensure_marimo_inputs.ps1"

if (-not (Test-Path $python)) { throw "Missing venv python: $python" }
if (-not (Test-Path $app)) { throw "Missing app file: $app" }
if (-not (Test-Path $ensureInputs)) { throw "Missing input bootstrap script: $ensureInputs" }

$env:PYTHONPATH = "$project;$project\scripts" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })
& $ensureInputs

# Kill stale marimo processes before launching a fresh app instance.
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "marimo" -and $_.CommandLine -match "espac_lci_pipeline_marimo.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Launching marimo app on http://127.0.0.1:$Port/"
Write-Host "Press Ctrl+C to stop."

& $python -m marimo run --host 127.0.0.1 --port $Port --show-tracebacks $app
