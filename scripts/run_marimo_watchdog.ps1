param(
  [int]$Port = 2718,
  [int]$IdleSecondsToStop = 30
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $project ".venv\Scripts\python.exe"
$app = Join-Path $project "apps\espac_lci_pipeline_marimo.py"

if (-not (Test-Path $python)) { throw "Missing venv python: $python" }
if (-not (Test-Path $app)) { throw "Missing app file: $app" }

# Kill stale marimo runs for this app first.
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -match "marimo" -and
    $_.CommandLine -match "espac_lci_pipeline_marimo.py"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Starting marimo app on http://localhost:$Port/ ..."
$proc = Start-Process -FilePath $python -ArgumentList @("-m","marimo","run",$app) -WorkingDirectory $project -PassThru

try {
  $hadClient = $false
  $idle = 0
  while (-not $proc.HasExited) {
    Start-Sleep -Seconds 2
    $conns = @(Get-NetTCPConnection -LocalPort $Port -State Established -ErrorAction SilentlyContinue)
    if ($conns.Count -gt 0) {
      $hadClient = $true
      $idle = 0
    } elseif ($hadClient) {
      $idle += 2
      if ($idle -ge $IdleSecondsToStop) {
        Write-Host "No client connection for $IdleSecondsToStop seconds. Stopping marimo."
        break
      }
    }
  }
}
finally {
  # Kill all marimo processes for this app to avoid leftovers.
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -eq "python.exe" -and
      $_.CommandLine -match "marimo" -and
      $_.CommandLine -match "espac_lci_pipeline_marimo.py"
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

