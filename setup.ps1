# One-time setup on Windows (PowerShell):  powershell -ExecutionPolicy Bypass -File setup.ps1
# Requires Python 3.11+ and Node.js 18+ (uses .tools\node if present, e.g. a portable Node 22).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# $ErrorActionPreference does not cover native commands, so check their exit codes explicitly.
function Assert-LastExit([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE). Setup is NOT complete." }
}

Write-Host "== Backend: virtual environment + dependencies"
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv; Assert-LastExit "Creating the virtual environment" }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
Assert-LastExit "Upgrading pip"
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Assert-LastExit "Installing backend dependencies"
& .\.venv\Scripts\python.exe scripts\manage.py init-db
Assert-LastExit "Initialising the database"
Pop-Location

Write-Host "== Frontend: npm install"
if (Test-Path "$root\.tools\node\node.exe") { $env:Path = "$root\.tools\node;" + $env:Path }
Push-Location "$root\frontend"
npm install --no-fund --no-audit
Assert-LastExit "npm install"
Pop-Location

if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env"; Write-Host "Created .env from .env.example (no API key set: offline mock mode)" }
Write-Host "Done. Start the API with run-backend.ps1 and the UI with run-frontend.ps1"
