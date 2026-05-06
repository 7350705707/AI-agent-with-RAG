"""FastAPI application — all API routes for the multi-agent dashboard."""

import hashlib
import json
import logging
import os
import shutil
import time
import uuid
import secrets
import asyncio
import threading
import queue as _queue
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from fastapi import FastAPI, Request, UploadFile, File, HTTPException, status, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.logger import setup_logging
setup_logging()  # Must be first so all module-level loggers are configured

log = logging.getLogger(__name__)

from app.config import (
    CORS_ORIGINS,
    UPLOAD_DIR,
    KNOWLEDGE_DIR,
    MAX_UPLOAD_SIZE_MB,
    ALLOWED_EXTENSIONS,
)
from app.database import (
    init_db,
    create_conversation,
    list_conversations,
    delete_conversation,
    rename_conversation,
    add_message,
    get_messages,
    get_user_by_username,
    get_user_by_id,
    create_user,
    list_users,
    update_user,
    delete_user,
    update_user_password,
    add_knowledge_document,
    update_knowledge_document_chunks,
    find_duplicate_document,
    list_knowledge_documents,
    delete_knowledge_document,
    clear_knowledge_documents,
    get_knowledge_document,
    register_conversation_file,
    rename_knowledge_document,
)
from app.chroma_store import (
    add_knowledge_chunks,
    delete_knowledge_chunks,
    clear_knowledge,
)
from app.models import (
    ChatRequest,
    ExamRequest,
    ConversationCreate,
    ConversationOut,
    MessageOut,
    LoginRequest,
    SignupRequest,
    UserCreate,
    UserUpdate,
    UserPasswordUpdate,
    UserOut,
)
from app.auth import (
    hash_password,
    verify_password,
    create_token,
    get_current_user,
    get_optional_user,
    require_admin,
)
from app.agents.chat_agent import run_chat, run_chat_stream, run_general_chat_stream
from app.agents.exam_agent import run_exam_generator, run_exam_generator_steps, parse_exam_to_json
from app.document_loader import load_and_split
from app.llm import list_available_models, get_active_model, set_active_model, ensure_model_loaded, is_no_model_error
from app.mcp_server import mcp as mcp_server

# ── Global LLM concurrency limiter ─────────────────────────────────────────
# LM Studio processes one request at a time (single model on GPU).
# This semaphore prevents multiple simultaneous requests from colliding
# and causing context / resource errors.
_llm_semaphore = asyncio.Semaphore(1)

# ── App Setup ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Sarvam AI API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response logging middleware ────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = None
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


@app.on_event("startup")
def startup():
    log.info("Sarvam AI backend starting up…")
    init_db()
    log.info("Database initialised.")
    # Load model in background so the server is immediately ready
    threading.Thread(target=ensure_model_loaded, daemon=True).start()
    log.info("Startup complete.")


# ── Health ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Models ─────────────────────────────────────────────────────────────────
@app.get("/api/models")
def api_list_models():
    """List all models available in LM Studio."""
    models = list_available_models()
    active = get_active_model()
    return {
        "active": active,
        "models": [{"id": m.get("id", ""), "object": m.get("object", "")} for m in models],
    }


@app.post("/api/models/select")
def api_select_model(body: dict):
    """Switch the active LLM model at runtime."""
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing 'model' field")
    set_active_model(model_id)
    return {"active": model_id}


@app.post("/api/models/load")
def api_load_model(body: dict):
    """Select a model and trigger loading it in LM Studio."""
    model_id = body.get("model")
    if not model_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing 'model' field")
    set_active_model(model_id)
    loaded = ensure_model_loaded()
    return {"active": model_id, "loaded": loaded}


# ── Auth ───────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
def api_login(body: LoginRequest):
    user = get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password"]):
        log.warning("Failed login attempt for username='%s'", body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.get("is_active"):
        log.warning("Login attempt on disabled account username='%s'", body.username)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    token = create_token(user["id"], user["username"], user["role"], user["agents"])
    log.info("User logged in: username='%s' role='%s'", user["username"], user["role"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "agents": user["agents"],
        },
    }


@app.post("/api/auth/signup")
def api_signup(body: SignupRequest):
    if get_user_by_username(body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    pw_hash = hash_password(body.password)
    user = create_user(body.username, pw_hash, role="user", agents=["chat"])
    token = create_token(user["id"], user["username"], user["role"], user["agents"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "agents": user["agents"],
        },
    }


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    db_user = get_user_by_id(user["sub"])
    if not db_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {
        "id": db_user["id"],
        "username": db_user["username"],
        "role": db_user["role"],
        "agents": db_user["agents"],
    }


# ── Admin: User Management ────────────────────────────────────────────────
@app.get("/api/admin/users", response_model=list[UserOut])
def api_list_users(_admin: dict = Depends(require_admin)):
    return list_users()


@app.post("/api/admin/users", response_model=UserOut, status_code=201)
def api_create_user(body: UserCreate, _admin: dict = Depends(require_admin)):
    if get_user_by_username(body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    pw_hash = hash_password(body.password)
    return create_user(body.username, pw_hash, body.role, body.agents)


@app.put("/api/admin/users/{user_id}", response_model=UserOut)
def api_update_user(user_id: str, body: UserUpdate, _admin: dict = Depends(require_admin)):
    if not update_user(
        user_id,
        role=body.role,
        agents=body.agents,
        is_active=int(body.is_active) if body.is_active is not None else None,
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user = get_user_by_id(user_id)
    return user


@app.put("/api/admin/users/{user_id}/password")
def api_reset_password(user_id: str, body: UserPasswordUpdate, _admin: dict = Depends(require_admin)):
    pw_hash = hash_password(body.password)
    if not update_user_password(user_id, pw_hash):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"detail": "Password updated"}


@app.delete("/api/admin/users/{user_id}", status_code=204)
def api_delete_user(user_id: str, admin: dict = Depends(require_admin)):
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target["username"] == "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the default admin")
    delete_user(user_id)


# ── Conversations CRUD ─────────────────────────────────────────────────────
@app.post("/api/conversations", response_model=ConversationOut, status_code=201)
def api_create_conversation(body: ConversationCreate, user: dict | None = Depends(get_optional_user)):
    user_id = user["sub"] if user else None
    return create_conversation(body.agent_type, body.title, user_id=user_id)


@app.get("/api/conversations", response_model=list[ConversationOut])
def api_list_conversations(agent_type: str | None = None, user: dict | None = Depends(get_optional_user)):
    user_id = user["sub"] if user else None
    return list_conversations(agent_type, user_id=user_id)


@app.patch("/api/conversations/{conv_id}")
def api_rename_conversation(conv_id: str, body: dict, _user: dict | None = Depends(get_optional_user)):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(400, "Title required")
    if not rename_conversation(conv_id, title):
        raise HTTPException(404, "Conversation not found")
    return {"id": conv_id, "title": title}


@app.delete("/api/conversations/{conv_id}", status_code=204)
def api_delete_conversation(conv_id: str, _user: dict | None = Depends(get_optional_user)):
    if not delete_conversation(conv_id):
        raise HTTPException(404, "Conversation not found")


@app.get("/api/conversations/{conv_id}/messages", response_model=list[MessageOut])
def api_get_messages(conv_id: str, _user: dict | None = Depends(get_optional_user)):
    return get_messages(conv_id)


# ── File Upload ────────────────────────────────────────────────────────────
@app.post("/api/upload")
def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    _user: dict = Depends(get_current_user),
):
    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file (sync — FastAPI runs this in a threadpool automatically)
    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # Sanitize filename and save
    file_id = str(uuid.uuid4())
    safe_filename = Path(file.filename).name  # strip path components
    save_dir = UPLOAD_DIR / file_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / safe_filename

    with open(save_path, "wb") as f:
        f.write(contents)

    # Track file against conversation so it gets cleaned up on conversation delete
    if conversation_id:
        register_conversation_file(conversation_id, file_id, str(save_path))

    return {
        "file_id": file_id,
        "filename": safe_filename,
        "size_bytes": len(contents),
    }


# ── Knowledge Base ─────────────────────────────────────────────────────────
@app.post("/api/knowledge/upload")
def api_knowledge_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    safe_filename = Path(file.filename).name

    # Read file bytes early so we can hash for duplicate detection
    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # ── Duplicate detection (hash + filename) ─────────────────────────────
    file_hash = hashlib.sha256(contents).hexdigest()
    duplicate = find_duplicate_document(safe_filename, file_hash)
    if duplicate:
        if duplicate["match_type"] == "hash":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This file's content already exists in the library as '{duplicate['filename']}'. "
                "The same document cannot be uploaded twice even under a different name.",
            )
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A document named '{safe_filename}' already exists in the library. "
                "Remove the existing document first or rename the file before uploading.",
            )

    # Save permanently in knowledge_files directory
    doc_id = str(uuid.uuid4())
    save_dir = KNOWLEDGE_DIR / doc_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / safe_filename

    try:
        with open(save_path, "wb") as f:
            f.write(contents)

        log.info("Knowledge upload: saved '%s' (%d bytes) by '%s'", safe_filename, len(contents), user.get("username", "unknown"))

        # Record document immediately (chunk_count=0); splitting + embedding
        # happen in the background so the client gets a fast response.
        doc = add_knowledge_document(
            doc_id, safe_filename, len(contents), 0,
            uploaded_by=user.get("username", "unknown"),
            file_path=str(save_path),
            file_hash=file_hash,
        )

        def _index_in_background(path, d_id, fname):
            try:
                chunks = load_and_split(path)
                chunk_dicts = [{"content": c.page_content, "metadata": str(c.metadata)} for c in chunks]
                log.info("Knowledge index: '%s' split into %d chunks", fname, len(chunk_dicts))
                add_knowledge_chunks(d_id, fname, chunk_dicts)
                update_knowledge_document_chunks(d_id, len(chunk_dicts))
                log.info("Knowledge index: '%s' fully indexed", fname)
            except Exception as exc:
                log.error("Knowledge index failed for '%s': %s", fname, exc, exc_info=True)

        background_tasks.add_task(_index_in_background, save_path, doc_id, safe_filename)

        return doc

    except HTTPException:
        raise
    except Exception as e:
        log.error("Knowledge upload failed for '%s': %s", safe_filename, e, exc_info=True)
        # Clean up on failure
        if save_dir.exists():
            shutil.rmtree(save_dir)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to process file: {e}")


@app.get("/api/knowledge/documents")
def api_knowledge_list(user: dict = Depends(get_current_user)):
    return list_knowledge_documents()


@app.delete("/api/knowledge/documents/{doc_id}", status_code=204)
def api_knowledge_delete(doc_id: str, _admin: dict = Depends(require_admin)):
    # Remove vector chunks from ChromaDB first
    delete_knowledge_chunks(doc_id)
    if not delete_knowledge_document(doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


@app.post("/api/knowledge/documents/{doc_id}/index")
def api_knowledge_index(doc_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Manually trigger indexing for a document that has not been indexed yet."""
    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    file_path = doc.get("file_path", "")
    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not available on disk")

    def _index(path, d_id, fname):
        try:
            chunks = load_and_split(path)
            chunk_dicts = [{"content": c.page_content, "metadata": str(c.metadata)} for c in chunks]
            log.info("Manual index: '%s' split into %d chunks", fname, len(chunk_dicts))
            add_knowledge_chunks(d_id, fname, chunk_dicts)
            update_knowledge_document_chunks(d_id, len(chunk_dicts))
            log.info("Manual index: '%s' fully indexed", fname)
        except Exception as exc:
            log.error("Manual index failed for '%s': %s", fname, exc, exc_info=True)

    background_tasks.add_task(_index, Path(file_path), doc_id, doc["filename"])
    return {"detail": "Indexing started", "doc_id": doc_id}


@app.patch("/api/knowledge/documents/{doc_id}")
def api_knowledge_rename(doc_id: str, body: dict, _admin: dict = Depends(require_admin)):
    """Rename a knowledge document's display name."""
    new_name = (body.get("filename") or "").strip()
    if not new_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "filename required")
    if not rename_knowledge_document(doc_id, new_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return {"id": doc_id, "filename": new_name}


@app.delete("/api/knowledge/clear", status_code=204)
def api_knowledge_clear(_admin: dict = Depends(require_admin)):
    clear_knowledge()          # wipe ChromaDB collection
    clear_knowledge_documents()  # wipe SQLite document metadata


@app.get("/api/knowledge/documents/{doc_id}/download")
def api_knowledge_download(doc_id: str, token: str | None = None, _user: dict = Depends(get_optional_user)):
    """Download the original uploaded document. Accepts token as query param for direct links."""
    from app.auth import decode_token
    if not _user and token:
        _user = decode_token(token)
    if not _user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    file_path = doc.get("file_path", "")
    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not available on disk")
    return FileResponse(
        path=file_path,
        filename=doc["filename"],
        media_type="application/octet-stream",
    )


# ── General Chat ───────────────────────────────────────────────────────────
@app.post("/api/chat")
def api_chat(body: ChatRequest, _user: dict | None = Depends(get_optional_user)):
    add_message(body.conversation_id, "user", body.message)
    log.info("Chat request conv_id=%s", body.conversation_id)
    try:
        response = run_chat(body.conversation_id, body.message)
    except Exception as e:
        log.error("Chat LLM error conv_id=%s: %s", body.conversation_id, e, exc_info=True)
        raise HTTPException(500, f"LLM error: {e}")
    add_message(body.conversation_id, "assistant", response)
    return {"conversation_id": body.conversation_id, "response": response}


@app.post("/api/chat/stream")
async def api_chat_stream(request: Request, body: ChatRequest, _user: dict | None = Depends(get_optional_user)):
    """Stream chat response tokens via SSE. Cancels LM Studio when client disconnects."""
    add_message(body.conversation_id, "user", body.message)
    conv_id = body.conversation_id

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run():
        full = ""
        all_sources = []
        try:
            for token, sources in run_chat_stream(conv_id, body.message, stop_event):
                if stop_event.is_set():
                    break
                full += token
                if sources:
                    all_sources = sources
                q.put(("token", token, sources))
            cited = [s for s in all_sources if s["filename"].lower() in full.lower()]
            q.put(("done", full, cited))
        except Exception as e:
            q.put(("error", str(e), []))

    async def event_stream():
        full_response = ""
        cited_sources = []
        # Queue with a 503 response if another LLM request is already in flight
        if _llm_semaphore.locked():
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Model is busy with another request. Please wait a moment and try again.'})}\n\n"
            return
        async with _llm_semaphore:
            threading.Thread(target=_run, daemon=True).start()
            try:
                while True:
                    if await request.is_disconnected():
                        stop_event.set()
                        return
                    try:
                        kind, data, extra = q.get_nowait()
                    except _queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    if kind == "done":
                        cited_sources = extra
                        yield f"data: {json.dumps({'token': '', 'done': True, 'sources': cited_sources})}\n\n"
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'token': '', 'done': True, 'error': data})}\n\n"
                        break
                    else:
                        full_response += data
                        yield f"data: {json.dumps({'token': data, 'done': False})}\n\n"
            finally:
                if full_response and not stop_event.is_set():
                    add_message(conv_id, "assistant", full_response, sources=cited_sources)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── General Chat (no RAG) ──────────────────────────────────────────────────
@app.post("/api/general-chat/stream")
async def api_general_chat_stream(request: Request, body: ChatRequest, _user: dict | None = Depends(get_optional_user)):
    """Stream pure LLM chat (no RAG) via SSE. Cancels LM Studio when client disconnects."""
    add_message(body.conversation_id, "user", body.message)
    conv_id = body.conversation_id

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run():
        full = ""
        try:
            for token in run_general_chat_stream(conv_id, body.message, stop_event):
                if stop_event.is_set():
                    break
                full += token
                q.put(("token", token))
            q.put(("done", full))
        except Exception as e:
            q.put(("error", str(e)))

    async def event_stream():
        full_response = ""
        if _llm_semaphore.locked():
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Model is busy with another request. Please wait a moment and try again.'})}\n\n"
            return
        async with _llm_semaphore:
            threading.Thread(target=_run, daemon=True).start()
            try:
                while True:
                    if await request.is_disconnected():
                        stop_event.set()
                        return
                    try:
                        item = q.get_nowait()
                    except _queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    kind = item[0]
                    if kind == "done":
                        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'token': '', 'done': True, 'error': item[1]})}\n\n"
                        break
                    else:
                        full_response += item[1]
                        yield f"data: {json.dumps({'token': item[1], 'done': False})}\n\n"
            finally:
                if full_response and not stop_event.is_set():
                    add_message(conv_id, "assistant", full_response)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Exam Generator ─────────────────────────────────────────────────────────
@app.post("/api/exam")
def api_exam(body: ExamRequest, _user: dict = Depends(get_current_user)):
    add_message(body.conversation_id, "user", body.instructions)
    for attempt in range(2):
        try:
            response = run_exam_generator(
                body.conversation_id, body.instructions, body.file_ids,
                mcq_count=body.mcq_count, tf_count=body.tf_count, fitb_count=body.fitb_count,
            )
            break
        except Exception as e:
            if attempt == 0 and is_no_model_error(e):
                log.warning("No model loaded (exam); attempting auto-load...")
                ensure_model_loaded()
                continue
            raise HTTPException(500, f"LLM error: {e}")
    add_message(body.conversation_id, "assistant", response)
    return {"conversation_id": body.conversation_id, "response": response}


@app.post("/api/exam/stream")
async def api_exam_stream(request: Request, body: ExamRequest, _user: dict = Depends(get_current_user)):
    add_message(body.conversation_id, "user", body.instructions)
    conv_id = body.conversation_id

    # Register uploaded files with this conversation so they're deleted with it
    from app.config import UPLOAD_DIR as _UDIR
    for fid in (body.file_ids or []):
        fdir = _UDIR / fid
        if fdir.is_dir():
            for fp in fdir.iterdir():
                if fp.is_file():
                    register_conversation_file(conv_id, fid, str(fp))
                    break

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run():
        final = ""
        def _do_run():
            nonlocal final
            for step, label, content in run_exam_generator_steps(
                conv_id, body.instructions, body.file_ids,
                mcq_count=body.mcq_count, tf_count=body.tf_count, fitb_count=body.fitb_count,
                stop_event=stop_event,
            ):
                if stop_event.is_set():
                    return
                final = content
                q.put(("event", step, label, content))
            q.put(("done", final))

        try:
            _do_run()
        except Exception as e:
            if is_no_model_error(e):
                log.warning("No model loaded (exam stream); attempting auto-load...")
                if ensure_model_loaded():
                    final = ""
                    try:
                        _do_run()
                        return
                    except Exception as e2:
                        q.put(("error", str(e2)))
                        return
            q.put(("error", str(e)))

    threading.Thread(target=_run, daemon=True).start()

    async def event_stream():
        final_content = ""
        try:
            while True:
                if await request.is_disconnected():
                    stop_event.set()
                    return
                try:
                    item = q.get_nowait()
                except _queue.Empty:
                    await asyncio.sleep(0.01)
                    continue
                kind = item[0]
                if kind == "done":
                    final_content = item[1]
                    break
                elif kind == "error":
                    err = json.dumps({"step": "error", "label": item[1], "content": ""})
                    yield f"data: {err}\n\n"
                    return
                else:
                    _, step, label, content = item
                    final_content = content
                    payload = json.dumps({"step": step, "label": label, "content": content})
                    yield f"data: {payload}\n\n"
        finally:
            if final_content and not stop_event.is_set():
                add_message(conv_id, "assistant", final_content)
                try:
                    questions = parse_exam_to_json(final_content)
                    if questions:
                        structured_payload = json.dumps({"step": "structured", "label": "structured", "content": "", "questions": questions})
                        yield f"data: {structured_payload}\n\n"
                except Exception as parse_err:
                    log.warning("Failed to parse exam to JSON: %s", parse_err)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Serve React frontend (SPA fallback) ───────────────────────────────────
_FRONTEND_BUILD = BASE_DIR.parent / "frontend" / "build"

if _FRONTEND_BUILD.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_BUILD / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Catch-all: return index.html for any non-API route (React SPA)."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(str(_FRONTEND_BUILD / "index.html"))
