# Start FastAPI with proxy bypass for localhost (company laptops).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:NO_PROXY = "localhost,127.0.0.1,[::1],<local>,*.local"
$env:no_proxy = $env:NO_PROXY

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

Write-Host "NO_PROXY=$env:NO_PROXY"
Write-Host "Starting server at http://127.0.0.1:8000"
Write-Host "Ollama diagnostics: http://127.0.0.1:8000/api/ollama-health"
Write-Host ""

uvicorn app:app --app-dir src --reload --host 127.0.0.1 --port 8000
