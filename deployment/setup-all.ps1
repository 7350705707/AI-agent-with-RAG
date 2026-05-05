<#
.SYNOPSIS
    Master setup script - builds frontend, copies to IIS, installs backend service.
    Run as Administrator on Windows Server 2019.
#>

param(
    [string]$ProjectRoot = "D:\Model-AI",
    [string]$IISSitePath = "C:\inetpub\AIDashboard",
    [string]$PythonExe   = "python"
)

# ── Require Administrator ──────────────────────────────────────────────────
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "  Right-click PowerShell -> 'Run as administrator', then re-run." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

# ── 1. Python backend setup ────────────────────────────────────────────────
Write-Host "`n=== BACKEND SETUP ===" -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"

if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..."
    & $PythonExe -m venv venv
}
& .\venv\Scripts\Activate.ps1

Write-Host "Installing Python dependencies (offline)..."
if (Test-Path "packages") {
    pip install --no-index --find-links=packages -r requirements.txt
} else {
    Write-Host "  (No offline packages/ folder found - installing from pip cache or internet)"
    pip install -r requirements.txt
}

pip install pywin32

Write-Host "Installing backend as Windows Service..."
& $PythonExe win_service.py install
& $PythonExe win_service.py start
Write-Host "Backend service started." -ForegroundColor Green

# ── 2. Frontend build ──────────────────────────────────────────────────────
Write-Host "`n=== FRONTEND BUILD ===" -ForegroundColor Cyan
Set-Location "$ProjectRoot\frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm packages (offline)..."
    if (Test-Path "npm-cache") {
        npm install --cache ./npm-cache --prefer-offline
    } else {
        npm install
    }
}

Write-Host "Building production bundle..."
npm run build

# ── 3. Deploy to IIS (optional - skip if IIS not installed) ────────────────
$iisInstalled = Get-Module -ListAvailable -Name WebAdministration -ErrorAction SilentlyContinue
if ($iisInstalled) {
    Write-Host "`n=== IIS DEPLOYMENT ===" -ForegroundColor Cyan
    if (-not (Test-Path $IISSitePath)) {
        New-Item -ItemType Directory -Path $IISSitePath -Force | Out-Null
    }

    Write-Host "Copying build output to $IISSitePath ..."
    Copy-Item -Path "$ProjectRoot\frontend\build\*" -Destination $IISSitePath -Recurse -Force
    Copy-Item -Path "$ProjectRoot\deployment\web.config" -Destination $IISSitePath -Force

    # ── 4. HTTPS ────────────────────────────────────────────────────────────
    Write-Host "`n=== HTTPS SETUP ===" -ForegroundColor Cyan
    & "$ProjectRoot\deployment\setup-https.ps1" -SitePath $IISSitePath

    Write-Host "`n  Deployment complete!" -ForegroundColor Green
    Write-Host "   Frontend: https://$env:COMPUTERNAME" -ForegroundColor White
} else {
    Write-Host "`n=== IIS NOT INSTALLED - SKIPPING ===" -ForegroundColor Yellow
    Write-Host "  IIS (WebAdministration module) not found." -ForegroundColor Yellow
    Write-Host "  To install IIS:" -ForegroundColor Yellow
    Write-Host "    Windows Server:  Install-WindowsFeature Web-Server,Web-Default-Doc,Web-Static-Content,Web-Http-Redirect,Web-Filtering,Web-Mgmt-Console" -ForegroundColor White
    Write-Host "    Windows Desktop: dism /online /enable-feature /featurename:IIS-WebServerRole /featurename:IIS-WebServer /featurename:IIS-DefaultDocument /featurename:IIS-StaticContent /featurename:IIS-HttpRedirect /featurename:IIS-RequestFiltering /featurename:IIS-ManagementConsole /all" -ForegroundColor White
    Write-Host "  Also install URL Rewrite + ARR modules, then re-run this script." -ForegroundColor Yellow
    Write-Host "`n  Frontend build output is ready at: $ProjectRoot\frontend\build\" -ForegroundColor White
}

Write-Host "`n  Backend API: http://localhost:8000/docs" -ForegroundColor White
