# SolarSage installer — Windows PowerShell.
#
# Usage:
#   iwr -useb https://raw.githubusercontent.com/geekychris/solarsage/main/install.ps1 | iex
#
# Or, pinned:
#   $env:INSTALL_DIR = "$HOME\solarsage"
#   iwr -useb .../install.ps1 | iex

$ErrorActionPreference = 'Stop'

$RepoUrl   = if ($env:SOLARSAGE_REPO) { $env:SOLARSAGE_REPO } else { 'https://github.com/geekychris/solarsage.git' }
$Branch    = if ($env:SOLARSAGE_BRANCH) { $env:SOLARSAGE_BRANCH } else { 'main' }
$InstallDir = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { Join-Path $HOME 'solarsage' }

function Log($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host " ok  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "warn $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "fail $msg" -ForegroundColor Red; exit 1 }

function Need-Cmd($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

function Install-Winget($id) {
  if (Need-Cmd winget) {
    Log "Installing $id via winget"
    winget install -e --id $id --silent --accept-source-agreements --accept-package-agreements
  } else {
    Fail "winget not available. Install Git, Python 3.11, and Node 18+ manually, then re-run."
  }
}

Log "SolarSage installer starting"

if (-not (Need-Cmd git))    { Install-Winget 'Git.Git' }
if (-not (Need-Cmd python)) {
  Install-Winget 'Python.Python.3.11'
  $env:PATH = "$env:LOCALAPPDATA\Programs\Python\Python311;$env:LOCALAPPDATA\Programs\Python\Python311\Scripts;$env:PATH"
}
if (-not (Need-Cmd node))   { Install-Winget 'OpenJS.NodeJS.LTS' }

if (-not (Need-Cmd git))    { Fail "git missing after install" }
if (-not (Need-Cmd python)) { Fail "python missing after install" }
if (-not (Need-Cmd node))   { Fail "node missing after install" }

Ok ("prereqs present (git $((git --version).Split(' ')[2]), python $((python --version).Split(' ')[1]), node $(node -v))")

# --- clone / pull -----------------------------------------------------------
if (Test-Path (Join-Path $InstallDir '.git')) {
  Log "Updating existing checkout at $InstallDir"
  git -C $InstallDir fetch --depth 1 origin $Branch
  git -C $InstallDir reset --hard "origin/$Branch"
} else {
  Log "Cloning $RepoUrl into $InstallDir"
  git clone --depth 1 --branch $Branch $RepoUrl $InstallDir
}
Ok "source ready at $InstallDir"

# --- backend ----------------------------------------------------------------
Set-Location (Join-Path $InstallDir 'backend')
if (-not (Test-Path .venv)) {
  Log "Creating Python venv"
  python -m venv .venv
}
Log "Installing backend dependencies"
& .\.venv\Scripts\python -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python -m pip install --quiet -r requirements.txt
Ok "backend deps installed"

if (-not (Test-Path .env)) {
  Log "Seeding backend/.env"
  Copy-Item .env.example .env
  $key = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
  (Get-Content .env) `
    -replace 'EG4_API_KEY=local-dev-key-change-me', "EG4_API_KEY=$key" `
    -replace '^EG4_API_KEY=$', "EG4_API_KEY=$key" |
    Set-Content .env
  Ok "generated unique API key (see backend/.env)"
}

# --- frontend ---------------------------------------------------------------
Set-Location (Join-Path $InstallDir 'frontend')
Log "Installing frontend dependencies (npm install)"
npm install --silent --no-progress | Out-Null
Log "Building frontend bundle"
npm run build --silent | Out-Null
Ok "frontend built"

# --- launcher ---------------------------------------------------------------
$Launcher = Join-Path $env:USERPROFILE '.local\bin\solarsage.cmd'
New-Item -ItemType Directory -Force (Split-Path $Launcher) | Out-Null
Set-Content -Path $Launcher -Value "@echo off`r`npowershell -ExecutionPolicy Bypass -File `"$InstallDir\solarsage.ps1`" %*"
Ok "launcher at $Launcher"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notmatch [Regex]::Escape((Split-Path $Launcher))) {
  Warn "$($env:USERPROFILE)\.local\bin is not on your user PATH"
  Warn "Add it via System Settings → Edit environment variables, then re-open this window."
}

# --- done -------------------------------------------------------------------
Log "Starting SolarSage"
& (Join-Path $InstallDir 'start.ps1')

$apiKey = (Select-String -Path (Join-Path $InstallDir 'backend\.env') -Pattern '^EG4_API_KEY=(.*)$').Matches[0].Groups[1].Value

Write-Host @"

SolarSage is installed and running.

  UI         http://127.0.0.1:5173
  API docs   http://127.0.0.1:8000/docs
  Source     $InstallDir
  API key    $apiKey

Sign in via the UI with your monitor.eg4electronics.com credentials, leave
"Remember me" checked, and you're done.

Common commands:
  solarsage start | stop | status   (launcher on PATH)
  $InstallDir\start.ps1 | stop.ps1 | status.ps1

Docs:
  $InstallDir\docs\ARCHITECTURE.md
  $InstallDir\docs\INSTALLATION.md
"@ -ForegroundColor Green
