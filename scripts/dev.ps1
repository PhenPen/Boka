# Restart the local API on http://127.0.0.1:8010 and run it in this terminal.
# Ctrl+C stops it. Logs go to the terminal.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 [-ApiKey <key>]

param([string]$ApiKey = "")

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($ApiKey) { $env:API_KEY = $ApiKey }

$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Milliseconds 800
}

& (Join-Path $root ".venv\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port 8010
