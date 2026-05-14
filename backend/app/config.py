"""Application configuration — all paths and settings for offline operation."""

import os
import secrets
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
KNOWLEDGE_DIR = BASE_DIR / "knowledge_files"
SQLITE_DB = BASE_DIR / "chat_history.db"
CHROMA_DIR = BASE_DIR / "chroma_db"

UPLOAD_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR.mkdir(exist_ok=True)

# ── LM Studio / LLM ───────────────────────────────────────────────────────
# Default to host.docker.internal so the container can always reach LM Studio
# running on the host machine — works on Docker Desktop (Windows/Mac) and
# bare Linux Docker Engine (via the extra_hosts → host-gateway in docker-compose).
# When running bare Python outside Docker, override with:
#   set LM_STUDIO_BASE_URL=http://localhost:1234/v1
# LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://host.docker.internal:1234/v1")
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct-1m")

# Embedding mode:
#   "auto"      — LM Studio first; falls back to ChromaDB ONNX (all-MiniLM-L6-v2) when LM Studio
#                 is unreachable.  Safe for offline deployments but risks mixing vector spaces if
#                 LM Studio availability changes between indexing runs.
#   "lmstudio"  — LM Studio only.  Backend refuses to start if /v1/embeddings is unreachable and
#                 document upload/search will fail while LM Studio is down.  Use this when you want
#                 higher-quality embeddings and can guarantee LM Studio is always running.
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "lmstudio")  # "auto" | "lmstudio"

# Seconds to wait for a single LM Studio /v1/embeddings batch call.
# Increase if you embed very large chunks or use a slow GPU.
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "120"))

# Number of chunks sent to LM Studio per /v1/embeddings request.
# Smaller = fewer timeout risks; larger = fewer round-trips.
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

# Context window (tokens) sent to LM Studio when loading a model
MODEL_CONTEXT_LENGTH = int(os.getenv("MODEL_CONTEXT_LENGTH", "10000"))


# ── Upload limits ─────────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = 200
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx"}

# ── JWT / Auth ─────────────────────────────────────────────────────────────
_jwt_secret_file = BASE_DIR / ".jwt_secret"
if _jwt_secret_file.exists():
    JWT_SECRET = _jwt_secret_file.read_text().strip()
else:
    JWT_SECRET = secrets.token_hex(32)
    _jwt_secret_file.write_text(JWT_SECRET)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# ── CORS origins (intranet only) ──────────────────────────────────────────
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost,http://localhost:3000,http://localhost:5173,"
    "http://127.0.0.1,http://127.0.0.1:3000,http://127.0.0.1:5173,"
    "https://localhost,https://127.0.0.1"
).split(",")
