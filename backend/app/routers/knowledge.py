"""Knowledge-base controller — document upload, listing, indexing, and download.

Model  : app.database  (add/list/delete/rename knowledge documents)
         app.chroma_store  (vector chunk storage)
View   : Document metadata JSON responses
"""

import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.auth import decode_token, get_current_user, get_optional_user, require_admin, require_embedding
from app.chroma_store import add_knowledge_chunks, clear_knowledge, delete_knowledge_chunks
from app.config import ALLOWED_EXTENSIONS, KNOWLEDGE_DIR, MAX_UPLOAD_SIZE_MB
from app.database import (
    add_knowledge_document,
    clear_knowledge_documents,
    delete_knowledge_document,
    find_duplicate_document,
    get_knowledge_document,
    list_knowledge_documents,
    rename_knowledge_document,
    update_knowledge_document_chunks,
)
from app.utils.document_loader import load_and_split

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Upload ─────────────────────────────────────────────────────────────────
@router.post("/upload")
def api_knowledge_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    _emb: None = Depends(require_embedding),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    safe_filename = Path(file.filename).name
    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # ── Duplicate detection ────────────────────────────────────────────────
    file_hash = hashlib.sha256(contents).hexdigest()
    duplicate = find_duplicate_document(safe_filename, file_hash)
    if duplicate:
        if duplicate["match_type"] == "hash":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This file's content already exists in the library as '{duplicate['filename']}'. "
                "The same document cannot be uploaded twice even under a different name.",
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A document named '{safe_filename}' already exists in the library. "
            "Remove the existing document first or rename the file before uploading.",
        )

    doc_id = str(uuid.uuid4())
    save_dir = KNOWLEDGE_DIR / doc_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / safe_filename

    try:
        with open(save_path, "wb") as f:
            f.write(contents)

        log.info(
            "Knowledge upload: saved '%s' (%d bytes) by '%s'",
            safe_filename, len(contents), user.get("username", "unknown"),
        )

        doc = add_knowledge_document(
            doc_id, safe_filename, len(contents), 0,
            uploaded_by=user.get("username", "unknown"),
            file_path=str(save_path),
            file_hash=file_hash,
        )

        def _index_in_background(path: Path, d_id: str, fname: str) -> None:
            try:
                chunks = load_and_split(path)
                chunk_dicts = [
                    {"content": c.page_content, "metadata": str(c.metadata)}
                    for c in chunks
                ]
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
        if save_dir.exists():
            shutil.rmtree(save_dir)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to process file: {e}")


# ── List documents ─────────────────────────────────────────────────────────
@router.get("/documents")
def api_knowledge_list(_user: dict = Depends(get_current_user)):
    return list_knowledge_documents()


# ── Delete document ────────────────────────────────────────────────────────
@router.delete("/documents/{doc_id}", status_code=204)
def api_knowledge_delete(doc_id: str, _admin: dict = Depends(require_admin)):
    delete_knowledge_chunks(doc_id)
    if not delete_knowledge_document(doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


# ── Trigger indexing ───────────────────────────────────────────────────────
@router.post("/documents/{doc_id}/index")
def api_knowledge_index(
    doc_id: str,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(get_current_user),
    _emb: None = Depends(require_embedding),
):
    """Manually trigger indexing for a document that has not been indexed yet."""
    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    file_path = doc.get("file_path", "")
    resolved = Path(file_path) if file_path else None
    if not resolved or not resolved.is_file():
        # Stored path may be from a different OS/environment; reconstruct from KNOWLEDGE_DIR
        resolved = KNOWLEDGE_DIR / doc_id / doc["filename"]
    if not resolved.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not available on disk")

    def _index(path: Path, d_id: str, fname: str) -> None:
        try:
            chunks = load_and_split(path)
            chunk_dicts = [
                {"content": c.page_content, "metadata": str(c.metadata)}
                for c in chunks
            ]
            log.info("Manual index: '%s' split into %d chunks", fname, len(chunk_dicts))
            add_knowledge_chunks(d_id, fname, chunk_dicts)
            update_knowledge_document_chunks(d_id, len(chunk_dicts))
            log.info("Manual index: '%s' fully indexed", fname)
        except Exception as exc:
            log.error("Manual index failed for '%s': %s", fname, exc, exc_info=True)

    background_tasks.add_task(_index, resolved, doc_id, doc["filename"])
    return {"detail": "Indexing started", "doc_id": doc_id}


# ── Rename document ────────────────────────────────────────────────────────
@router.patch("/documents/{doc_id}")
def api_knowledge_rename(
    doc_id: str,
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """Rename a knowledge document's display name."""
    new_name = (body.get("filename") or "").strip()
    if not new_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "filename required")
    if not rename_knowledge_document(doc_id, new_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return {"id": doc_id, "filename": new_name}


# ── Clear all documents ────────────────────────────────────────────────────
@router.delete("/clear", status_code=204)
def api_knowledge_clear(_admin: dict = Depends(require_admin)):
    clear_knowledge()
    clear_knowledge_documents()


# ── Download document ──────────────────────────────────────────────────────
@router.get("/documents/{doc_id}/download")
def api_knowledge_download(
    doc_id: str,
    token: str | None = None,
    _user: dict | None = Depends(get_optional_user),
):
    """Download the original uploaded document. Accepts token query param for direct links."""
    if not _user and token:
        _user = decode_token(token)
    if not _user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    file_path = doc.get("file_path", "")
    resolved = Path(file_path) if file_path else None
    if not resolved or not resolved.is_file():
        # Stored path may be from a different OS/environment; reconstruct from KNOWLEDGE_DIR
        resolved = KNOWLEDGE_DIR / doc_id / doc["filename"]
    if not resolved.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not available on disk")
    return FileResponse(
        path=resolved,
        filename=doc["filename"],
        media_type="application/octet-stream",
    )


# ── Summarize document ─────────────────────────────────────────────────────
@router.post("/documents/{doc_id}/summarize")
def api_knowledge_summarize(
    doc_id: str,
    _user: dict = Depends(get_current_user),
    _emb: None = Depends(require_embedding),
):
    """Generate an AI summary of the document using indexed chunks."""
    from app.chroma_store import search_knowledge, get_knowledge_chunk_count
    from app.llm import get_llm
    from app.utils.prompts import SUMMARIZE_PROMPT

    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    if get_knowledge_chunk_count() == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Document has not been indexed yet")

    # Fetch representative chunks from this document (broad query to get overview)
    results = search_knowledge(doc["filename"], limit=12)
    # Filter to only chunks belonging to this document
    chunks = [r for r in results if r.get("doc_id") == doc_id]
    if not chunks:
        # Fallback: try with a generic query
        chunks = results[:8]
    if not chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No indexed content found for this document")

    content = "\n\n".join(c["content"] for c in chunks[:10])[:6000]

    try:
        llm = get_llm(temperature=0.3, num_predict=800)
        result = (SUMMARIZE_PROMPT | llm).invoke({
            "filename": doc["filename"],
            "content": content,
        })
        summary_text = result.content if hasattr(result, "content") else str(result)
        return {"doc_id": doc_id, "filename": doc["filename"], "summary": summary_text.strip()}
    except Exception as e:
        log.error("Summarize failed for doc_id=%s: %s", doc_id, e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Summarization failed: {e}")


# ── Semantic Knowledge Base Search ─────────────────────────────────────────
@router.get("/search")
def api_knowledge_search(
    q: str,
    limit: int = 10,
    _user: dict = Depends(get_current_user),
    _emb: None = Depends(require_embedding),
):
    """Hybrid semantic + BM25 search over the entire knowledge base."""
    from app.chroma_store import search_knowledge, get_knowledge_chunk_count

    q = q.strip()
    if not q:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Query cannot be empty")
    if get_knowledge_chunk_count() == 0:
        return {"query": q, "results": []}

    limit = min(max(1, limit), 30)
    results = search_knowledge(q, limit=limit)
    return {
        "query": q,
        "results": [
            {
                "doc_id": r["doc_id"],
                "filename": r["filename"],
                "snippet": r["content"][:500],
                "score": r["score"],
            }
            for r in results
        ],
    }

