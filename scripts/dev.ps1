# Restart the local API on http://127.0.0.1:8010.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/dev.ps1

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Stop-Process -Id $listener.OwningProcess -Force
    Start-Sleep -Milliseconds 800
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$out = Join-Path $root "dev-server.log"
$err = Join-Path $root "dev-server.err.log"

Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010" `
    -WindowStyle Hidden `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err

Start-Sleep -Seconds 2
Write-Output "api on http://127.0.0.1:8010 (logs: dev-server.log)"
