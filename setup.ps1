# One-time setup on Windows (PowerShell):  powershell -ExecutionPolicy Bypass -File setup.ps1
# Requires Python 3.11+ and Node.js 18+ (uses .tools\node if present, e.g. a portable Node 22).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "== Backend: virtual environment + dependencies"
Push-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts\manage.py init-db
Pop-Location

Write-Host "== Frontend: npm install"
if (Test-Path "$root\.tools\node\node.exe") { $env:Path = "$root\.tools\node;" + $env:Path }
Push-Location "$root\frontend"
npm install --no-fund --no-audit
Pop-Location

if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env"; Write-Host "Created .env from .env.example (no API key set: offline mock mode)" }
Write-Host "Done. Start the API with run-backend.ps1 and the UI with run-frontend.ps1"
