<#
.SYNOPSIS
    Fully automated offline setup for the AI Dashboard project.
    Run this script on the target (offline) PC as Administrator.

.DESCRIPTION
    This script:
      1. Creates a Python virtual environment
      2. Installs all packages from the local packages/ folder (no internet)
      3. Installs the backend as a Windows auto-start service
      4. Optionally sets up IIS to serve the frontend on port 80

.PARAMETER ProjectRoot
    Where the project lives on this machine. Default: D:\Model-AI

.PARAMETER InstallService
    Install the FastAPI backend as a Windows Service. Default: $true

.PARAMETER SetupIIS
    Install IIS and serve the frontend on port 80. Default: $false
    (Not needed — the FastAPI backend already serves the frontend on port 8000)

.EXAMPLE
    # Simple run — backend service only (recommended)
    .\setup-offline.ps1

    # Also install IIS frontend on port 80
    .\setup-offline.ps1 -SetupIIS $true

    # Custom install path
    .\setup-offline.ps1 -ProjectRoot "C:\Apps\Model-AI"
#>

param(
    [string]$ProjectRoot   = "D:\Model-AI",
    [bool]$InstallService  = $true,
    [bool]$SetupIIS        = $false
)

# ── Require Administrator ─────────────────────────────────────────────────
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Run this script as Administrator." -ForegroundColor Red
    Write-Host "  Right-click PowerShell → 'Run as administrator'" -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}
function Write-OK($msg) {
    Write-Host "    OK: $msg" -ForegroundColor Green
}
function Write-Warn($msg) {
    Write-Host "    WARN: $msg" -ForegroundColor Yellow
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 0 — Validate project folder
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Checking project folder: $ProjectRoot"
if (-not (Test-Path "$ProjectRoot\backend\run.py")) {
    Write-Host "ERROR: Project not found at $ProjectRoot" -ForegroundColor Red
    Write-Host "  Copy the entire Model-AI folder to $ProjectRoot and re-run." -ForegroundColor Yellow
    exit 1
}
Write-OK "Project found."

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Check Python 3.12
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Checking Python installation"
try {
    $pyVersion = & python --version 2>&1
    if ($pyVersion -notmatch "Python 3\.(1[2-9]|[2-9]\d)") {
        Write-Warn "Found $pyVersion but Python 3.12+ is recommended."
        Write-Warn "If packages fail, install Python 3.12 first."
    } else {
        Write-OK $pyVersion
    }
} catch {
    Write-Host "ERROR: Python not found. Install Python 3.12 first." -ForegroundColor Red
    Write-Host "  Download the offline installer: python-3.12.x-amd64.exe" -ForegroundColor Yellow
    exit 1
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — Create virtual environment
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Setting up Python virtual environment"
Set-Location "$ProjectRoot\backend"

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "    Creating venv..."
    python -m venv venv
    Write-OK "venv created."
} else {
    Write-OK "venv already exists, skipping creation."
}

$PythonExe = "$ProjectRoot\backend\venv\Scripts\python.exe"
$PipExe    = "$ProjectRoot\backend\venv\Scripts\pip.exe"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Install Python packages (offline)
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Installing Python packages from packages\ folder (offline)"

$pkgDir = "$ProjectRoot\backend\packages"
if (-not (Test-Path $pkgDir)) {
    Write-Host "ERROR: packages\ folder not found at $pkgDir" -ForegroundColor Red
    exit 1
}

# Install all packages in one shot from the local wheel directory
& $PipExe install `
    --no-index `
    --find-links="$pkgDir" `
    -r requirements.txt

Write-OK "Core packages installed."

# pywin32 — needed for Windows Service
& $PipExe install --no-index --find-links="$pkgDir" pywin32
Write-OK "pywin32 installed."

# Run pywin32 post-install script (registers COM helpers)
$postInstall = "$ProjectRoot\backend\venv\Scripts\pywin32_postinstall.py"
if (Test-Path $postInstall) {
    & $PythonExe $postInstall -install 2>$null
    Write-OK "pywin32 post-install complete."
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Smoke test (import check)
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Running import smoke test"
$testScript = @"
import sys
try:
    from langchain_openai import ChatOpenAI
    from mcp.server.fastmcp import FastMCP
    from fastapi import FastAPI
    print("OK")
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"@
$result = & $PythonExe -c $testScript
if ($result -eq "OK") {
    Write-OK "All critical imports pass."
} else {
    Write-Host "ERROR: Import test failed: $result" -ForegroundColor Red
    Write-Host "  Some packages may be missing from packages\ folder." -ForegroundColor Yellow
    exit 1
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Check LM Studio
# ═══════════════════════════════════════════════════════════════════════════
Write-Step "Checking LM Studio"
$lmPath1 = "$env:LOCALAPPDATA\Programs\LM-Studio\LM Studio.exe"
$lmPath2 = "$env:PROGRAMFILES\LM Studio\LM Studio.exe"
if ((Test-Path $lmPath1) -or (Test-Path $lmPath2)) {
    Write-OK "LM Studio is installed."
} else {
    Write-Warn "LM Studio not found."
    Write-Warn "  Install 'LM Studio Setup.exe' then copy your model files to:"
    Write-Warn "  %USERPROFILE%\.lmstudio\models\"
    Write-Warn "  After installing LM Studio, open it and load a model, then re-run this script."
}

# Test if LM Studio API is running
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:1234/v1/models" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-OK "LM Studio API is running at http://localhost:1234"
} catch {
    Write-Warn "LM Studio API not reachable at http://localhost:1234"
    Write-Warn "  Open LM Studio → Start Server (or load any model)"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Install as Windows Service (auto-start)
# ═══════════════════════════════════════════════════════════════════════════
if ($InstallService) {
    Write-Step "Installing backend as Windows Service (AIDashboardBackend)"

    # Remove old service if it exists
    $svc = Get-Service -Name "AIDashboardBackend" -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Warn "Service already exists — stopping and removing..."
        & $PythonExe win_service.py stop  2>$null
        & $PythonExe win_service.py remove 2>$null
        Start-Sleep -Seconds 2
    }

    & $PythonExe win_service.py install
    & $PythonExe win_service.py start

    Start-Sleep -Seconds 4

    $svc = Get-Service -Name "AIDashboardBackend" -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Write-OK "Service is Running."
        Write-OK "Backend available at: http://localhost:8000"
        Write-OK "Full app (UI + API): http://localhost:8000"
    } else {
        Write-Warn "Service may not have started. Check Event Viewer for errors."
        Write-Warn "To test manually: cd $ProjectRoot\backend ; .\venv\Scripts\activate ; python run.py"
    }
} else {
    Write-Step "Skipping Windows Service install (manual mode)"
    Write-Host "    To run manually:" -ForegroundColor White
    Write-Host "      cd $ProjectRoot\backend" -ForegroundColor White
    Write-Host "      .\venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "      python run.py" -ForegroundColor White
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7 — Optional IIS frontend (port 80)
# ═══════════════════════════════════════════════════════════════════════════
if ($SetupIIS) {
    Write-Step "Installing IIS to serve frontend on port 80"

    # Install IIS
    Install-WindowsFeature -Name Web-Server, Web-Default-Doc, Web-Static-Content, `
        Web-Http-Redirect, Web-Filtering, Web-Mgmt-Console -IncludeManagementTools | Out-Null
    Write-OK "IIS installed."

    $sitePath = "C:\inetpub\AIDashboard"
    New-Item -ItemType Directory -Path $sitePath -Force | Out-Null

    # Copy frontend build
    Copy-Item -Path "$ProjectRoot\frontend\build\*" -Destination $sitePath -Recurse -Force
    Write-OK "Frontend files copied to $sitePath"

    # Copy web.config
    Copy-Item -Path "$ProjectRoot\deployment\web.config" -Destination $sitePath -Force

    # Create IIS site
    Import-Module WebAdministration -ErrorAction SilentlyContinue
    $existingSite = Get-Website -Name "AIDashboard" -ErrorAction SilentlyContinue
    if ($existingSite) { Remove-Website -Name "AIDashboard" }

    New-Website -Name "AIDashboard" `
        -PhysicalPath $sitePath `
        -Port 80 `
        -Force | Out-Null

    Write-OK "IIS site created. Frontend at: http://localhost"
    Write-Warn "NOTE: Frontend calls the API at http://localhost:8000 (backend must be running)"
}

# ═══════════════════════════════════════════════════════════════════════════
# DONE
# ═══════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  SETUP COMPLETE" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  App URL  : http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs : http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  REQUIREMENTS:" -ForegroundColor Yellow
Write-Host "   1. LM Studio must be running with a model loaded" -ForegroundColor Yellow
Write-Host "      - Open LM Studio → load your model → click 'Start Server'" -ForegroundColor Yellow
Write-Host "   2. Backend service auto-starts with Windows" -ForegroundColor Yellow
Write-Host "      - Manage: Get-Service AIDashboardBackend" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To restart backend:" -ForegroundColor Cyan
Write-Host "    Restart-Service AIDashboardBackend" -ForegroundColor White
Write-Host ""
