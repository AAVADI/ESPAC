[CmdletBinding()]
param(
    [switch]$ForceRecreate
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"

function Get-BasePythonCommand {
    $preferred = @(
        @{ Exe = "py"; Args = @("-3.13") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )

    foreach ($candidate in $preferred) {
        try {
            & $candidate.Exe @($candidate.Args + @("-c", "import sys; print(sys.executable)")) *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
        }
    }

    throw "No usable base Python interpreter was found. Install Python 3 and make `py` or `python` available."
}

function Test-VenvHealthy {
    param([string]$InterpreterPath)

    if (-not (Test-Path $InterpreterPath)) {
        return $false
    }

    try {
        & $InterpreterPath -c "import sys, venv, pip, ipykernel, jupyterlab; print(sys.executable)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if ($ForceRecreate -and (Test-Path $VenvPath)) {
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}

if (-not (Test-VenvHealthy -InterpreterPath $PythonExe)) {
    if (Test-Path $VenvPath) {
        Remove-Item -LiteralPath $VenvPath -Recurse -Force
    }

    $basePython = Get-BasePythonCommand
    Write-Host "Creating virtual environment with $($basePython.Exe) $($basePython.Args -join ' ')"
    & $basePython.Exe @($basePython.Args + @("-m", "venv", $VenvPath))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment at $VenvPath"
    }
}

Write-Host "Upgrading packaging tools in .venv"
& $PythonExe -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip/setuptools/wheel in .venv"
}

Write-Host "Installing project requirements"
& $PythonExe -m pip install -r $RequirementsPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Python requirements"
}

Write-Host "Registering explicit Jupyter kernels for this project"
$LocalKernelPath = Join-Path $VenvPath "share\jupyter\kernels\python3"
if (Test-Path $LocalKernelPath) {
    Remove-Item -LiteralPath $LocalKernelPath -Recurse -Force
}

& $PythonExe -m ipykernel install --prefix $VenvPath --name python3 --display-name "ESPAC (.venv)"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the local python3 kernelspec into .venv"
}

& $PythonExe -m ipykernel install --user --name espac-venv --display-name "ESPAC (.venv)"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the user espac-venv kernelspec"
}

Write-Host "Virtual environment is ready:"
& $PythonExe -c "import sys; print(sys.executable)"
