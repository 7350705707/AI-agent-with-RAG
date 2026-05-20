"""Admin controller — user management routes (admin-only).

Model  : app.database  (list/create/update/delete users, update password)
View   : UserOut Pydantic response model
"""

import threading
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.auth import hash_password, require_admin
from app.database import (
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    list_pending_users,
    approve_pending_user,
    list_knowledge_documents,
    update_knowledge_document_chunks,
    update_user,
    update_user_password,
)
from app.models import UserCreate, UserOut, UserPasswordUpdate, UserUpdate

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Reindex state (module-level, single-process safe) ─────────────────────
_reindex_lock = threading.Lock()
_reindex_state: dict = {"status": "idle", "progress": None, "error": None}


# ── List users ─────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserOut])
def api_list_users(_admin: dict = Depends(require_admin)):
    return list_users()


# ── Pending user approvals ─────────────────────────────────────────────────
@router.get("/pending-users")
def api_pending_users(_admin: dict = Depends(require_admin)):
    """Return users who signed up and are awaiting admin approval."""
    return list_pending_users()


@router.post("/users/{user_id}/approve", response_model=UserOut)
def api_approve_user(user_id: str, _admin: dict = Depends(require_admin)):
    """Approve a pending user signup — activates their account."""
    if not approve_pending_user(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pending user not found")
    return get_user_by_id(user_id)


# ── Create user ────────────────────────────────────────────────────────────
@router.post("/users", response_model=UserOut, status_code=201)
def api_create_user(body: UserCreate, _admin: dict = Depends(require_admin)):
    if get_user_by_username(body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    pw_hash = hash_password(body.password)
    return create_user(body.username, pw_hash, body.role, body.agents)


# ── Update user (role / agents / active) ──────────────────────────────────
@router.put("/users/{user_id}", response_model=UserOut)
def api_update_user(
    user_id: str,
    body: UserUpdate,
    _admin: dict = Depends(require_admin),
):
    if not update_user(
        user_id,
        role=body.role,
        agents=body.agents,
        is_active=int(body.is_active) if body.is_active is not None else None,
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return get_user_by_id(user_id)


# ── Reset password ─────────────────────────────────────────────────────────
@router.put("/users/{user_id}/password")
def api_reset_password(
    user_id: str,
    body: UserPasswordUpdate,
    _admin: dict = Depends(require_admin),
):
    pw_hash = hash_password(body.password)
    if not update_user_password(user_id, pw_hash):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"detail": "Password updated"}


# ── Delete user ────────────────────────────────────────────────────────────
@router.delete("/users/{user_id}", status_code=204)
def api_delete_user(user_id: str, _admin: dict = Depends(require_admin)):
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target["username"] == "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the default admin")
    delete_user(user_id)


# ── Embedding status ───────────────────────────────────────────────────────
@router.get("/embedding-status")
def api_embedding_status(_admin: dict = Depends(require_admin)):
    """Return current embedding backend health and configuration."""
    from app.chroma_store import check_embedding_health, get_knowledge_chunk_count
    status_info = check_embedding_health()
    status_info["total_chunks"] = get_knowledge_chunk_count()
    status_info["reindex"] = _reindex_state.copy()
    return status_info


# ── Full re-index ──────────────────────────────────────────────────────────
@router.post("/reindex", status_code=202)
def api_reindex(
    background_tasks: BackgroundTasks,
    _admin: dict = Depends(require_admin),
):
    """Drop the ChromaDB collection and re-embed all knowledge documents.

    Runs in the background.  Poll GET /api/admin/embedding-status to track
    progress.  While re-indexing is in progress, new uploads are still
    accepted but will queue behind the running task.
    """
    with _reindex_lock:
        if _reindex_state["status"] == "running":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A re-index is already in progress. Check /api/admin/embedding-status for progress.",
            )
        _reindex_state.update({"status": "running", "progress": "starting", "error": None})

    background_tasks.add_task(_run_reindex)
    return {"detail": "Re-index started in the background."}


def _run_reindex() -> None:
    """Background worker: wipe ChromaDB collection and re-embed every document."""
    from app.chroma_store import clear_knowledge, add_knowledge_chunks, check_embedding_health
    from app.utils.document_loader import load_and_split

    # Verify embedding backend is reachable before wiping anything
    health = check_embedding_health()
    if not health["lmstudio_available"]:
        from app.config import EMBEDDING_MODE
        if EMBEDDING_MODE == "lmstudio":
            with _reindex_lock:
                _reindex_state.update({
                    "status": "failed",
                    "progress": None,
                    "error": (
                        "LM Studio /v1/embeddings is not reachable and EMBEDDING_MODE=lmstudio. "
                        "Start an embedding model in LM Studio before re-indexing."
                    ),
                })
            return

    docs = list_knowledge_documents()
    total = len(docs)
    log.info("Re-index: starting — %d document(s) to process.", total)

    try:
        # Drop the collection so old vectors (potentially from a different model) are gone
        clear_knowledge()
        log.info("Re-index: ChromaDB collection cleared.")

        errors = []
        for i, doc in enumerate(docs, 1):
            doc_id = doc["id"]
            filename = doc["filename"]
            file_path = doc.get("file_path", "")

            with _reindex_lock:
                _reindex_state["progress"] = f"{i}/{total}: {filename}"

            if not file_path or not Path(file_path).exists():
                msg = f"File not found for '{filename}' (doc_id={doc_id}); skipping."
                log.warning("Re-index: %s", msg)
                errors.append(msg)
                continue

            try:
                chunks = load_and_split(Path(file_path))
                chunk_dicts = [
                    {"content": c.page_content, "metadata": str(c.metadata)}
                    for c in chunks
                ]
                add_knowledge_chunks(doc_id, filename, chunk_dicts)
                update_knowledge_document_chunks(doc_id, len(chunk_dicts))
                log.info("Re-index: '%s' → %d chunks.", filename, len(chunk_dicts))
            except Exception as exc:
                msg = f"Failed to index '{filename}': {exc}"
                log.error("Re-index: %s", msg, exc_info=True)
                errors.append(msg)

        final_status = "completed" if not errors else "completed_with_errors"
        with _reindex_lock:
            _reindex_state.update({
                "status": final_status,
                "progress": f"Done — {total} document(s) processed, {len(errors)} error(s).",
                "error": "; ".join(errors) if errors else None,
            })
        log.info("Re-index: finished (%s).", final_status)

    except Exception as exc:
        log.error("Re-index: unexpected failure: %s", exc, exc_info=True)
        with _reindex_lock:
            _reindex_state.update({
                "status": "failed",
                "progress": None,
                "error": str(exc),
            })
