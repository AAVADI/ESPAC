param(
  [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $project ".venv\Scripts\python.exe"
$app = Join-Path $project "apps\espac_lci_pipeline_streamlit.py"

if (-not (Test-Path $python)) { throw "Missing venv python: $python" }
if (-not (Test-Path $app)) { throw "Missing app file: $app" }

# Kill stale streamlit processes for this app to avoid orphaned servers.
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "streamlit" -and $_.CommandLine -match "espac_lci_pipeline_streamlit.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Launching Streamlit app on http://127.0.0.1:$Port/"
Write-Host "Press Ctrl+C to stop."

try {
  & $python -m streamlit run $app --server.address 127.0.0.1 --server.port $Port --server.headless true
}
finally {
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -match "streamlit" -and $_.CommandLine -match "espac_lci_pipeline_streamlit.py" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
