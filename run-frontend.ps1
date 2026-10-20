# Starts the Vite dev server on http://127.0.0.1:5173 (proxies /api to the backend on :8000)
$ErrorActionPreference = "Stop"
if (Test-Path "$PSScriptRoot\.tools\node\node.exe") { $env:Path = "$PSScriptRoot\.tools\node;" + $env:Path }
Push-Location "$PSScriptRoot\frontend"
try { npm run dev -- --host 127.0.0.1 --port 5173 }
finally { Pop-Location }
