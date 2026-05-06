<#
.SYNOPSIS
    Builds the Docker image and exports it to a .tar file for transfer to an offline PC.

.DESCRIPTION
    Run this script ONCE on an internet-connected machine.
    It builds the model-ai:latest image (frontend + backend in one container) and
    saves it as  model-ai-export.tar  in the project root.

    Transfer the following to the offline PC (USB drive / network share):
      - model-ai-export.tar          (the container image)
      - The entire project folder    (for docker-compose.yml + persistent data volumes)

.USAGE
    cd D:\Model-AI
    .\export-for-offline.ps1
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ImageName  = "model-ai"
$ImageTag   = "latest"
$ExportFile = "model-ai-export.tar"

Write-Host ""
Write-Host "============================================================"
Write-Host "============================================================"
Write-Host ""

# ── Verify Docker is running ──────────────────────────────────────────────
Write-Host "[1/3] Checking Docker..."
try {
    docker info | Out-Null
} catch {
    Write-Error "Docker is not running or not installed. Please start Docker Desktop first."
    exit 1
}
Write-Host "      Docker OK"
Write-Host ""

# ── Build the image ───────────────────────────────────────────────────────
Write-Host "[2/3] Building image  ${ImageName}:${ImageTag}  ..."
Write-Host "      (this may take 5-15 minutes the first time)"
Write-Host ""
docker compose build --no-cache

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker build failed. Review the output above."
    exit 1
}
Write-Host ""
Write-Host "      Build successful."
Write-Host ""

# ── Export the image ──────────────────────────────────────────────────────
Write-Host "[3/3] Saving image to  $ExportFile  ..."
docker save -o $ExportFile "${ImageName}:${ImageTag}"

if ($LASTEXITCODE -ne 0) {
    Write-Error "docker save failed."
    exit 1
}

$SizeMB = [math]::Round((Get-Item $ExportFile).Length / 1MB, 1)
Write-Host ""
Write-Host "============================================================"
Write-Host " DONE!  $ExportFile  ($SizeMB MB)"
Write-Host "============================================================"
Write-Host ""
Write-Host "Copy the following to the offline PC:"
Write-Host "  1.  $ExportFile"
Write-Host "  2.  The entire project folder (D:\Model-AI\)"
Write-Host ""
Write-Host "On the offline PC, run:"
Write-Host "  Windows :  .\deploy-offline.ps1"
Write-Host "  Linux   :  chmod +x deploy-offline.sh && ./deploy-offline.sh"
Write-Host "  macOS   :  chmod +x deploy-offline-macos.sh && ./deploy-offline-macos.sh"
Write-Host ""
