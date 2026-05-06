# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Build React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend

# Install dependencies first (better layer caching)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ ./
RUN npm run build


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Python backend (serves API + static frontend)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS backend

WORKDIR /app

# System build tools (needed for some Python packages that compile from source)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Isolated virtualenv so site-packages stay clean
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (cached layer — only rebuilds when requirements.txt changes)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/ ./

# Copy built React app to the path FastAPI expects:
#   BASE_DIR = /app  →  BASE_DIR.parent = /  →  /frontend/build
COPY --from=frontend-builder /frontend/build /frontend/build

# Persistent data directories (override with bind-mounts or named volumes)
VOLUME ["/app/uploads", "/app/chroma_db", "/app/knowledge_files"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
