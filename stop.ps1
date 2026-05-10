# Stop both SolarSage servers.
$ErrorActionPreference = 'Continue'
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($svc in 'backend','frontend') {
  $pf = "$DIR\.run\$svc.pid"
  if (Test-Path $pf) {
    $sp = Get-Content $pf
    try { Stop-Process -Id $sp -Force; Write-Host "stopped $svc (pid $sp)" } catch {}
    Remove-Item $pf -Force -ErrorAction SilentlyContinue
  }
}
# Kill anything still bound to the ports
foreach ($port in 8000, 5173) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { try { Stop-Process -Id $_ -Force } catch {} }
}
Write-Host "SolarSage stopped"
