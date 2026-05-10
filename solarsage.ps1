$cmd = if ($args.Count -gt 0) { $args[0] } else { 'status' }
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
switch ($cmd) {
  'start'   { & "$DIR\start.ps1" }
  'stop'    { & "$DIR\stop.ps1" }
  'status'  { & "$DIR\status.ps1" }
  'restart' { & "$DIR\stop.ps1"; Start-Sleep -Seconds 1; & "$DIR\start.ps1" }
  'logs'    {
    $svc = if ($args.Count -gt 1) { $args[1] } else { 'backend' }
    if ($svc -ne 'backend' -and $svc -ne 'frontend') {
      Write-Host "usage: solarsage logs [backend|frontend]"; exit 1
    }
    Get-Content "$DIR\.run\$svc.log" -Wait
  }
  'update'  {
    git -C $DIR pull --ff-only
    & "$DIR\backend\.venv\Scripts\python" -m pip install --quiet -r "$DIR\backend\requirements.txt"
    Push-Location "$DIR\frontend"; npm install --silent; npm run build --silent; Pop-Location
    Write-Host "updated to $(git -C $DIR rev-parse --short HEAD)"
  }
  default   { Write-Host "usage: solarsage <start|stop|status|restart|logs|update>" }
}
