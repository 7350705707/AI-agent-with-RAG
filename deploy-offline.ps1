<#
.SYNOPSIS
    Loads the exported Docker image and starts the application on an offline PC.

.DESCRIPTION
    Run this script on the offline PC after copying:
      - model-ai-export.tar   (the container image)
      - The project folder    (this file lives inside it)

    Prerequisites on the offline PC:
      - Docker Desktop installed (no internet needed after install)
      - LM Studio installed with a model loaded and running on port 1234

.USAGE
    cd D:\Model-AI
    .\deploy-offline.ps1

.NOTES
    To stop:    docker compose down
    To restart: docker compose up -d
    Logs:       docker compose logs -f
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ExportFile = "model-ai-export.tar"

Write-Host ""
Write-Host "============================================================"
Write-Host " Model-AI  —  Offline Deployment"
Write-Host "============================================================"
Write-Host ""

# ── Verify Docker is running ──────────────────────────────────────────────
Write-Host "[1/4] Checking Docker..."
try {
    docker info | Out-Null
} catch {
    Write-Error "Docker is not running. Please start Docker Desktop and try again."
    exit 1
}
Write-Host "      Docker OK"
Write-Host ""

# ── Check export file ─────────────────────────────────────────────────────
Write-Host "[2/4] Looking for $ExportFile ..."
if (-not (Test-Path $ExportFile)) {
    Write-Error "$ExportFile not found in $PSScriptRoot.`nCopy it from the internet machine first."
    exit 1
}
Write-Host "      Found."

# Warn if RAG data folders are missing
if (-not (Test-Path "backend\chroma_db") -or -not (Get-ChildItem "backend\chroma_db" -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "  WARNING: backend\chroma_db\ is empty or missing."
    Write-Host "           RAG search will return no results until you copy it from"
    Write-Host "           the source machine or re-upload your documents."
    Write-Host ""
}
Write-Host ""

# ── Load the image ────────────────────────────────────────────────────────
Write-Host "[3/4] Loading image (this may take a minute)..."
docker load -i $ExportFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "docker load failed."
    exit 1
}
Write-Host "      Image loaded."
Write-Host ""

# ── Ensure persistent data directories and files exist ───────────────────
# Directories
$dirs = @(
    "backend\uploads",
    "backend\chroma_db",
    "backend\knowledge_files"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d | Out-Null
        Write-Host "      Created $d"
    }
}

# chat_history.db must be a FILE before Docker mounts it.
# Docker would create it as a directory otherwise, breaking SQLite.
if (-not (Test-Path "backend\chat_history.db")) {
    New-Item -ItemType File -Path "backend\chat_history.db" | Out-Null
    Write-Host "      Created backend\chat_history.db"
}

# .jwt_secret must also be a file (FastAPI reads/writes it on first run).
if (-not (Test-Path "backend\.jwt_secret")) {
    New-Item -ItemType File -Path "backend\.jwt_secret" | Out-Null
    Write-Host "      Created backend\.jwt_secret"
}

# ── Start the container ───────────────────────────────────────────────────
Write-Host "[4/4] Starting Model-AI container..."
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up failed."
    exit 1
}

Write-Host ""
Write-Host "============================================================"
Write-Host " Model-AI is running!"
Write-Host ""
Write-Host "  App URL :  http://localhost:8000"
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host ""
Write-Host " Make sure LM Studio is running on this PC with a model"
Write-Host " loaded — the app talks to it at http://localhost:1234"
Write-Host "============================================================"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose logs -f        # follow logs"
Write-Host "  docker compose down           # stop"
Write-Host "  docker compose restart        # restart"
Write-Host ""
