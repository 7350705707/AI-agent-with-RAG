"""Authentication & authorization helpers — JWT + bcrypt."""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS

log = logging.getLogger(__name__)
_bearer = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)


# ── Password helpers ───────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT helpers ────────────────────────────────────────────────────────────

def create_token(user_id: str, username: str, role: str, agents: list[str]) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "agents": agents,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        log.debug("JWT decode failed: token expired")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError as exc:
        log.warning("JWT decode failed: invalid token (%s)", type(exc).__name__)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


# ── FastAPI dependencies ───────────────────────────────────────────────────

def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> dict:
    """Decode JWT from Bearer header or httpOnly cookie."""
    if creds is not None:
        return decode_token(creds.credentials)
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return decode_token(cookie_token)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def get_optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> dict | None:
    """Return user payload if token present (header or cookie), else None (guest)."""
    if creds is not None:
        try:
            return decode_token(creds.credentials)
        except HTTPException:
            return None
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        try:
            return decode_token(cookie_token)
        except HTTPException:
            return None
    return None


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Raise 403 if user is not admin."""
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def require_embedding() -> None:
    """Raise 503 if the embedding model is not available.

    Automatically attempts to load the embedding model via LM Studio before
    raising an error, so the user does not need to restart the server manually.
    Inject as a dependency on any route that calls the vector store.
    """
    import logging
    import app.utils.state as _state

    if not _state.embedding_ready:
        _log = logging.getLogger(__name__)
        _log.info("Embedding not ready — attempting auto-load on demand...")
        try:
            from app.llm import ensure_embedding_model_loaded
            from app.chroma_store import reset_collection
            if ensure_embedding_model_loaded():
                # ensure_embedding_model_loaded() already confirmed the endpoint
                # is reachable via its internal probe-with-retries; reset the
                # cached collection so it re-initializes with LM Studio embeddings.
                reset_collection()
                _state.embedding_ready = True
                _log.info("Embedding model auto-loaded on demand — request will proceed.")
                return
        except Exception as _exc:
            _log.warning("Auto-load attempt raised an exception: %s", _exc)

        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Embedding model is not available and could not be auto-loaded. "
            "Please ensure LM Studio is running and the embedding model is loaded.",
        )
