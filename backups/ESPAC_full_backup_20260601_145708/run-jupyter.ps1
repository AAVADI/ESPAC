$bootstrap = Join-Path $PSScriptRoot 'scripts\bootstrap_venv.ps1'
if (-not (Test-Path $bootstrap)) {
    throw "Bootstrap script not found at $bootstrap"
}

& $bootstrap
if ($LASTEXITCODE -ne 0) {
    throw "Failed to prepare the virtual environment"
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$argsList = @('-m', 'jupyterlab') + $args
& $python @argsList
