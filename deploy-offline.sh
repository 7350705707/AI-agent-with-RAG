#!/usr/bin/env bash
# deploy-offline.sh — Load and start Model-AI on an offline Linux machine.
#
# PREREQUISITES on the offline Linux PC:
#   - Docker Engine installed  (https://docs.docker.com/engine/install/)
#   - docker-compose-plugin OR docker compose (v2) installed
#   - LM Studio running with a model loaded on port 1234
#   - model-ai-export.tar copied to the same folder as this script
#
# USAGE:
#   cd /path/to/Model-AI
#   chmod +x deploy-offline.sh
#   ./deploy-offline.sh
#
# USEFUL COMMANDS:
#   docker compose logs -f      # follow logs
#   docker compose down         # stop
#   docker compose restart      # restart without recreating
#   docker compose pull         # (offline — skip this)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EXPORT_FILE="model-ai-export.tar"

echo ""
echo "============================================================"
echo " Model-AI  —  Offline Deployment (Linux)"
echo "============================================================"
echo ""

# ── 1. Docker check ───────────────────────────────────────────────────────
echo "[1/4] Checking Docker..."
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running or not installed."
    echo "       Install: https://docs.docker.com/engine/install/"
    exit 1
fi
echo "      Docker OK"

# Check docker compose v2 (preferred) or fall back to docker-compose v1
if docker compose version > /dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose > /dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    echo "ERROR: Neither 'docker compose' (v2) nor 'docker-compose' (v1) found."
    echo "       Install the compose plugin: https://docs.docker.com/compose/install/"
    exit 1
fi
echo "      Compose: $COMPOSE"
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

# Ensure bind-mount targets exist with correct types.
# Docker creates missing paths as root-owned directories; pre-creating them
# here keeps ownership under the current user.
mkdir -p backend/uploads backend/chroma_db backend/knowledge_files

# chat_history.db must be a FILE before Docker mounts it, otherwise Docker
# creates it as a directory and SQLite fails.
if [[ ! -f backend/chat_history.db ]]; then
    touch backend/chat_history.db
fi

# .jwt_secret must also be a file (FastAPI reads/writes it on first run).
if [[ ! -f backend/.jwt_secret ]]; then
    touch backend/.jwt_secret
fi

$COMPOSE up -d

echo ""
echo "============================================================"
echo " Model-AI is running!"
echo ""
echo "  App URL :  http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo ""
echo "  From another machine on the LAN:"
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<this-machine-ip>")
echo "  http://${HOST_IP}:8000"
echo ""
echo " Make sure LM Studio is running on this PC with a model"
echo " loaded — the app talks to it at http://localhost:1234"
echo " (via host.docker.internal → host-gateway)"
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  $COMPOSE logs -f        # follow live logs"
echo "  $COMPOSE down           # stop container"
echo "  $COMPOSE restart        # restart"
echo ""
