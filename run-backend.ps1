# Starts the FastAPI backend on http://127.0.0.1:8000  (API docs: /docs)
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot\backend"
try { & .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
finally { Pop-Location }
