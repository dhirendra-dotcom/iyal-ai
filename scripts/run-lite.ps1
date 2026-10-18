param(
    [int]$Port = 8000,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendRoot = Join-Path $ProjectRoot "backend"
if (-not (Test-Path (Join-Path $BackendRoot ".env"))) {
    throw "Create backend/.env from backend/.env.example and configure your Google Cloud project and bucket first."
}
if (-not $Python) {
    $LocalPython = Join-Path $BackendRoot ".venv/Scripts/python.exe"
    if (Test-Path (Join-Path $BackendRoot ".venv/pyvenv.cfg")) { $Python = $LocalPython }
    else { $Python = "python" }
}
Write-Host "Iyal.ai v0.13.2 Lite: open http://127.0.0.1:$Port/ (chat at /app/)"
Write-Host "The browser UI needs no Node.js, npm, build step, or CDN."
Push-Location $BackendRoot
try {
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Backend did not start. Install backend/requirements.txt in the selected Python environment." }
} finally { Pop-Location }
