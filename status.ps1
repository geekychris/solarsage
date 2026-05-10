$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

function ProcOnPort($p) {
  Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
}

$bp = ProcOnPort 8000
$fp = ProcOnPort 5173
if ($bp) { Write-Host "  backend  (:8000)  running  pid $bp" } else { Write-Host "  backend  (:8000)  stopped" }
if ($fp) { Write-Host "  frontend (:5173)  running  pid $fp" } else { Write-Host "  frontend (:5173)  stopped" }

if ($bp) {
  Write-Host ""
  try {
    Write-Host "  health:   $((Invoke-RestMethod http://127.0.0.1:8000/api/health) | ConvertTo-Json -Compress)"
    Write-Host "  sessions: $((Invoke-RestMethod http://127.0.0.1:8000/api/auth/status) | ConvertTo-Json -Compress)"
  } catch {}
}
Write-Host ""
Write-Host "logs: $DIR\.run\{backend,frontend}.log"
