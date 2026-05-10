# Start both SolarSage servers.
$ErrorActionPreference = 'Stop'
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force "$DIR\.run" | Out-Null

function PortInUse($p) {
  $null -ne (Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue)
}

if (-not (PortInUse 8000)) {
  $p = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory "$DIR\backend" `
    -FilePath ".\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "app.main:app","--host","127.0.0.1","--port","8000" `
    -RedirectStandardOutput "$DIR\.run\backend.log" -RedirectStandardError "$DIR\.run\backend.err.log"
  $p.Id | Set-Content "$DIR\.run\backend.pid"
  Write-Host "started backend (pid $($p.Id))"
} else { Write-Host "backend already running on :8000" }

if (-not (PortInUse 5173)) {
  $p = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory "$DIR\frontend" `
    -FilePath "npm.cmd" -ArgumentList "run","dev","--","--host","127.0.0.1","--port","5173" `
    -RedirectStandardOutput "$DIR\.run\frontend.log" -RedirectStandardError "$DIR\.run\frontend.err.log"
  $p.Id | Set-Content "$DIR\.run\frontend.pid"
  Write-Host "started frontend (pid $($p.Id))"
} else { Write-Host "frontend already running on :5173" }

for ($i = 0; $i -lt 10; $i++) {
  try { Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
}
Write-Host ""
Write-Host "SolarSage running:"
Write-Host "  UI       http://127.0.0.1:5173"
Write-Host "  API docs http://127.0.0.1:8000/docs"
Write-Host "  logs     $DIR\.run\{backend,frontend}.log"
