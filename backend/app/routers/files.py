"""File upload controller — conversation-scoped document uploads.

Model  : app.database  (register_conversation_file)
View   : JSON response with file metadata
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import get_current_user
from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.database import register_conversation_file
from app.utils.audit import audit_log

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["files"])

# ── Magic-byte signatures for allowed file types ──────────────────────────
# Office Open XML (.docx / .pptx) are ZIP archives — share the same header.
_MAGIC: dict[str, list[bytes]] = {
    ".pdf":  [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
}


def _verify_magic(ext: str, data: bytes) -> bool:
    """Return True if *data* starts with a known magic byte for *ext*."""
    signatures = _MAGIC.get(ext, [])
    return any(data[: len(sig)] == sig for sig in signatures)


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # Validate actual file content via magic bytes (prevents extension spoofing)
    if not _verify_magic(ext, contents):
        log.warning(
            "Magic-byte mismatch: user=%s ext=%s size=%d",
            user.get("username", "?"), ext, len(contents),
        )
        audit_log(
            "UPLOAD_REJECTED",
            username=user.get("username", "?"),
            ext=ext,
            reason="magic_byte_mismatch",
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "File content does not match the declared file type.",
        )

    file_id = str(uuid.uuid4())
    safe_filename = Path(file.filename).name  # strip any path components
    save_dir = UPLOAD_DIR / file_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / safe_filename

    with open(save_path, "wb") as f:
        f.write(contents)

    if conversation_id:
        register_conversation_file(conversation_id, file_id, str(save_path))

    log.info("File uploaded: file_id=%s name='%s' size=%d", file_id, safe_filename, len(contents))
    audit_log("UPLOAD_SUCCESS", username=user.get("username", "?"), file_id=file_id, ext=ext, size=len(contents))

    return {
        "file_id": file_id,
        "filename": safe_filename,
        "size_bytes": len(contents),
    }
