[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [switch]$SkipDevDependencies,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "== Vox AI Input dev bootstrap =="
Write-Host "Repository: $RepoRoot"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python $PythonVersion and try again."
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv with Python $PythonVersion..."
    & py "-$PythonVersion" -m venv .venv
}

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python not found at $VenvPython"
}

Write-Host "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip

Write-Host "Installing runtime dependencies..."
& $VenvPython -m pip install -r requirements.txt

if (-not $SkipDevDependencies) {
    Write-Host "Installing development dependencies..."
    & $VenvPython -m pip install -r requirements-dev.txt
}

if (-not (Test-Path "config.yaml")) {
    Write-Host "Creating local config.yaml from config.example.yaml..."
    Copy-Item -Path "config.example.yaml" -Destination "config.yaml"
} else {
    Write-Host "config.yaml already exists; leaving it unchanged."
}

if (-not (Test-Path "models")) {
    New-Item -ItemType Directory -Path "models" | Out-Null
}

if (-not $SkipVerify) {
    Write-Host "Running compile verification..."
    & $VenvPython -m compileall -q run.py src tests

    if (-not $SkipDevDependencies) {
        Write-Host "Running test suite..."
        & $VenvPython -m pytest -q
    }
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
Write-Host "Open settings with: python run.py --open-settings"
