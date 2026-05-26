"""FastAPI application factory — wires middleware, MCP, and domain routers.

MVC layers
----------
Model      : app/database.py  (SQLite ORM helpers)
             app/chroma_store.py  (ChromaDB vector store)
View       : app/models.py  (Pydantic request/response schemas)
Controller : app/routers/  (domain-specific APIRouter modules)
"""

import logging
import os
import collections
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import CORS_ORIGINS, DEBUG, _FRONTEND_BUILD, _MCP_SECRET_KEY
from app.utils.logger import setup_logging

setup_logging()  # Must be first so all module-level loggers are configured

log = logging.getLogger(__name__)

from app.database import init_db
from app.llm import ensure_model_loaded, ensure_embedding_model_loaded
from app.chroma_store import check_embedding_health
from app.mcp_server import mcp as mcp_server

# ── Controllers (domain routers) ───────────────────────────────────────────
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router
from app.routers.exam import router as exam_router
from app.routers.files import router as files_router
from app.routers.knowledge import router as knowledge_router
from app.routers.llm_router import router as llm_router
from app.routers.analytics import router as analytics_router
from app.routers.approval import router as approval_router

BASE_DIR = Path(__file__).resolve().parent.parent

# ── MCP secret key (set MCP_SECRET_KEY env var to protect the /mcp endpoint)


# ── Global per-IP rate limiter ─────────────────────────────────────────────
_GLOBAL_LIMIT = 120        # max requests per window per IP
_GLOBAL_WINDOW = 60.0      # seconds
_global_rate_store: dict[str, list[float]] = collections.defaultdict(list)
_global_rate_lock = threading.Lock()

# ── App factory ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Sarvam AI API",
    version="1.0.0",
    docs_url="/docs" if DEBUG else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# ── MCP endpoint authentication middleware ─────────────────────────────────
@app.middleware("http")
async def mcp_auth_middleware(request: Request, call_next):
    """Require a Bearer token on /mcp when MCP_SECRET_KEY is configured."""
    if _MCP_SECRET_KEY and request.url.path.startswith("/mcp"):
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {_MCP_SECRET_KEY}":
            return JSONResponse(
                status_code=401,
                content={"detail": "MCP endpoint requires a valid secret key."},
            )
    return await call_next(request)


# ── Global per-IP rate limiting middleware ─────────────────────────────────
@app.middleware("http")
async def global_rate_limit_middleware(request: Request, call_next):
    """Hard cap: max 120 requests / 60 s per IP (excludes health check)."""
    if request.url.path == "/api/health":
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _global_rate_lock:
        _global_rate_store[ip] = [
            t for t in _global_rate_store[ip] if now - t < _GLOBAL_WINDOW
        ]
        if len(_global_rate_store[ip]) >= _GLOBAL_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(int(_GLOBAL_WINDOW))},
            )
        _global_rate_store[ip].append(now)
    return await call_next(request)


# ── Security headers middleware ────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )
    return response


# ── Request/Response logging middleware ────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        log.info(
            "HTTP %s %s → %d  (%.1f ms)",
            request.method, request.url.path, response.status_code, elapsed,
        )
        return response
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        log.error(
            "HTTP %s %s → UNHANDLED EXCEPTION  (%.1f ms): %s",
            request.method, request.url.path, elapsed, exc, exc_info=True,
        )
        raise


# ── Mount MCP Server (SSE transport at /mcp) ──────────────────────────────
app.mount("/mcp", mcp_server.sse_app())

# ── Register domain routers ────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(llm_router)
app.include_router(conversations_router)
app.include_router(admin_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(exam_router)
app.include_router(files_router)
app.include_router(analytics_router)
app.include_router(approval_router)


# ── Startup ────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    log.info("Sarvam AI backend starting up…")
    try:
        init_db()
        log.info("Database initialised.")
    except Exception as exc:
        log.critical("Database initialisation failed — server cannot start: %s", exc, exc_info=True)
        raise RuntimeError(f"Database init failed: {exc}") from exc

    # ── Embedding health check + auto-load ─────────────────────────────────
    from app.config import EMBEDDING_MODE, EMBEDDING_MODEL
    from app.utils import state as _state
    embed_status = check_embedding_health()
    if embed_status["lmstudio_available"]:
        _state.embedding_ready = True
        log.info(
            "Embedding: LM Studio reachable at %s (mode=%s).",
            embed_status["lmstudio_url"], EMBEDDING_MODE,
        )
    elif EMBEDDING_MODE == "lmstudio":
        log.warning(
            "Embedding: /v1/embeddings not reachable (%s). "
            "Attempting to auto-load '%s'...",
            embed_status.get("error", "unknown error"),
            EMBEDDING_MODEL or "(EMBEDDING_MODEL not set)",
        )
        loaded = ensure_embedding_model_loaded()
        if loaded:
            embed_status = check_embedding_health()
            if embed_status["lmstudio_available"]:
                _state.embedding_ready = True
                log.info("Embedding model '%s' loaded and ready.", EMBEDDING_MODEL)
            else:
                log.error(
                    "Embedding model loaded but /v1/embeddings still unreachable. "
                    "Knowledge upload, search and chat will return errors until resolved."
                )
        else:
            log.error(
                "Could not auto-load embedding model '%s'. "
                "Knowledge upload, search and chat will return errors until resolved. "
                "Set EMBEDDING_MODEL env var or start LM Studio manually.",
                EMBEDDING_MODEL or "(not set)",
            )
    else:
        # auto mode — ONNX fallback is always available
        _state.embedding_ready = True
        log.warning(
            "Embedding: LM Studio NOT reachable (%s). "
            "Falling back to ONNX (all-MiniLM-L6-v2). "
            "Vectors indexed now will differ from any previously indexed with LM Studio.",
            embed_status.get("error", "unknown error"),
        )

    # Load LLM model in background so the server is immediately ready
    threading.Thread(target=ensure_model_loaded, daemon=True).start()
    log.info("Startup complete.")


# ── Health ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Serve React frontend (SPA fallback) ───────────────────────────────────


if _FRONTEND_BUILD.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_BUILD / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Catch-all: serve static files from build root when they exist, else return index.html."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        # Serve root-level static files (images, favicon, manifests, etc.)
        candidate = _FRONTEND_BUILD / full_path
        if candidate.is_file() and candidate.resolve().is_relative_to(_FRONTEND_BUILD.resolve()):
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_BUILD / "index.html"))
