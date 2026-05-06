#!/usr/bin/env bash
# deploy-offline-macos.sh — Load and start Model-AI on an offline macOS machine.
#
# PREREQUISITES on the offline Mac:
#   - Docker Desktop for Mac installed  (https://www.docker.com/products/docker-desktop/)
#     (No internet needed after install — install from the .dmg offline)
#   - Docker Desktop is RUNNING (check the whale icon in the menu bar)
#   - LM Studio running with a model loaded and its local server on port 1234
#   - model-ai-export.tar copied to the same folder as this script
#
# USAGE:
#   cd /path/to/Model-AI
#   chmod +x deploy-offline-macos.sh
#   ./deploy-offline-macos.sh
#
# USEFUL COMMANDS:
#   docker compose logs -f      # follow live logs
#   docker compose down         # stop
#   docker compose restart      # restart without recreating

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EXPORT_FILE="model-ai-export.tar"

echo ""
echo "============================================================"
echo " Model-AI  —  Offline Deployment (macOS)"
echo "============================================================"
echo ""

# ── 1. Docker Desktop check ───────────────────────────────────────────────
echo "[1/4] Checking Docker Desktop..."

if ! command -v docker > /dev/null 2>&1; then
    echo "ERROR: 'docker' command not found."
    echo "       Install Docker Desktop for Mac and make sure it is running."
    echo "       Download (offline .dmg): https://docs.docker.com/desktop/install/mac-install/"
    exit 1
fi

# Docker Desktop may be installed but not started yet
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running."
    echo "       Open Docker Desktop from Applications (or Spotlight → Docker) and wait"
    echo "       for the whale icon in the menu bar to stop animating, then retry."
    exit 1
fi
echo "      Docker OK"

# docker compose v2 ships with Docker Desktop — no separate install needed
if ! docker compose version > /dev/null 2>&1; then
    echo "ERROR: 'docker compose' (v2) not available."
    echo "       Update Docker Desktop to a recent version."
    exit 1
fi
echo "      docker compose OK"
echo ""

# ── 2. Verify export file ─────────────────────────────────────────────────
echo "[2/4] Looking for $EXPORT_FILE ..."
if [[ ! -f "$EXPORT_FILE" ]]; then
    echo "ERROR: $EXPORT_FILE not found in $SCRIPT_DIR"
    echo "       Copy it from the internet machine first."
    exit 1
fi
echo "      Found."
echo ""

# ── 3. Load image ─────────────────────────────────────────────────────────
echo "[3/4] Loading Docker image (may take 1-2 minutes)..."
docker load -i "$EXPORT_FILE"
echo "      Image loaded."
echo ""

# ── 4. Prepare data dirs & files, then start ─────────────────────────────
echo "[4/4] Starting Model-AI container..."

# Ensure bind-mount target directories exist under the current user
mkdir -p backend/uploads backend/chroma_db backend/knowledge_files

# chat_history.db must be a FILE before Docker mounts it.
# Docker would create it as a directory otherwise, breaking SQLite.
if [[ ! -f backend/chat_history.db ]]; then
    touch backend/chat_history.db
fi

# .jwt_secret must also be a file (FastAPI reads/writes it on first run).
if [[ ! -f backend/.jwt_secret ]]; then
    touch backend/.jwt_secret
fi

# On macOS with Docker Desktop, host.docker.internal resolves to the host
# automatically — no extra_hosts workaround required (unlike bare Linux).
docker compose up -d

# ── Print access info ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Model-AI is running!"
echo ""
echo "  App URL :  http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo ""

# Try to get the active network IP so users can reach it from other devices
HOST_IP=$(ipconfig getifaddr en0 2>/dev/null \
       || ipconfig getifaddr en1 2>/dev/null \
       || echo "<this-machine-ip>")
echo "  From another device on the LAN:"
echo "  http://${HOST_IP}:8000"
echo ""
echo " Make sure LM Studio is open on this Mac with a model loaded"
echo " and its local server enabled on port 1234."
echo " The app reaches it via host.docker.internal:1234 (built-in on macOS)."
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # follow live logs"
echo "  docker compose down           # stop container"
echo "  docker compose restart        # restart"
echo ""
