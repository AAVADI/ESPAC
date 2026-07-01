param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $project ".venv\Scripts\python.exe"
$csvDir = Join-Path $project "outputs\CSVs"
$db = Join-Path $project "outputs\01_espac_2024.sqlite"
$cropMain = Join-Path $csvDir "02_espac_crop_lci_table__summary_province.csv"
$cropUncertainty = Join-Path $csvDir "02_espac_crop_lci_table__summary_province_uncertainty.csv"

if (-not (Test-Path $python)) { throw "Missing venv python: $python" }

$env:PYTHONPATH = "$project;$project\scripts" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })
New-Item -ItemType Directory -Force -Path $csvDir | Out-Null

function Invoke-Notebook {
  param(
    [string]$Notebook,
    [string]$OutputName,
    [int]$TimeoutSeconds = 1800
  )

  & $python -m jupyter nbconvert `
    --to notebook `
    --execute $Notebook `
    --output $OutputName `
    --output-dir (Join-Path $project "outputs") `
    --ExecutePreprocessor.timeout=$TimeoutSeconds `
    --ExecutePreprocessor.kernel_name=python3
}

if ($Force -or -not (Test-Path $db)) {
  Write-Host "Regenerating ESPAC SQLite database..."
  Invoke-Notebook `
    -Notebook (Join-Path $project "notebooks\1_espac_2024_etl_to_sqlite.ipynb") `
    -OutputName "_tmp_nb1_espac_sqlite_executed.ipynb"
}

if ($Force -or -not (Test-Path $cropMain) -or -not (Test-Path $cropUncertainty)) {
  Write-Host "Regenerating crop stage-02 province CSVs..."
  Invoke-Notebook `
    -Notebook (Join-Path $project "notebooks\2_crops_espac_2024_sqlite_explorer.ipynb") `
    -OutputName "_tmp_nb2_crops_executed.ipynb"
}

Write-Host "Marimo inputs are ready."
