"""Authentication controller — login, signup, current-user routes.

Model  : app.database  (get_user_by_username / get_user_by_id / create_user)
View   : JSON response dicts (token + user payload)
"""

import logging
import threading
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import create_user, get_user_by_id, get_user_by_username, update_user_password
from app.models import LoginRequest, SignupRequest
from app.utils.audit import audit_log

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── In-memory rate limiter — shared by login AND signup ───────────────────
_RATE_LIMIT = 5          # max failed attempts per window
_RATE_WINDOW = 60        # seconds
_BLOCK_DURATION = 300    # 5 minutes block after repeated IP failures

_fail_counts: dict[str, list[float]] = defaultdict(list)
_blocked_until: dict[str, float] = {}
_rate_lock = threading.Lock()

# ── Per-username lockout (independent of IP) ──────────────────────────────
_USERNAME_FAIL_LIMIT = 10    # max consecutive failures per username
_USERNAME_BLOCK_DURATION = 600  # 10 minutes

_user_fail_counts: dict[str, list[float]] = defaultdict(list)
_user_blocked_until: dict[str, float] = {}
_user_lock = threading.Lock()

# ── Signup rate limiter (per IP) ──────────────────────────────────────────
_SIGNUP_LIMIT = 3            # max signups per window per IP
_SIGNUP_WINDOW = 300         # 5 minutes
_SIGNUP_BLOCK = 600          # 10 minutes block

_signup_counts: dict[str, list[float]] = defaultdict(list)
_signup_blocked: dict[str, float] = {}
_signup_lock = threading.Lock()


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if *ip* has exceeded the failed login threshold."""
    now = time.time()
    with _rate_lock:
        if ip in _blocked_until:
            if now < _blocked_until[ip]:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many failed login attempts. Please try again later.",
                    headers={"Retry-After": str(int(_blocked_until[ip] - now))},
                )
            else:
                del _blocked_until[ip]
                _fail_counts.pop(ip, None)

        _fail_counts[ip] = [t for t in _fail_counts[ip] if now - t < _RATE_WINDOW]
        if len(_fail_counts[ip]) >= _RATE_LIMIT:
            _blocked_until[ip] = now + _BLOCK_DURATION
            _fail_counts.pop(ip, None)
            log.warning("IP %s blocked for %ds after repeated login failures", ip, _BLOCK_DURATION)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many failed login attempts. Please try again later.",
                headers={"Retry-After": str(_BLOCK_DURATION)},
            )


def _record_failure(ip: str) -> None:
    now = time.time()
    with _rate_lock:
        _fail_counts[ip].append(now)


def _clear_failures(ip: str) -> None:
    with _rate_lock:
        _fail_counts.pop(ip, None)
        _blocked_until.pop(ip, None)


def _check_username_lockout(username: str) -> None:
    """Raise 429 if *username* has too many recent failed attempts."""
    now = time.time()
    with _user_lock:
        if username in _user_blocked_until:
            if now < _user_blocked_until[username]:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Account temporarily locked. Please try again later.",
                    headers={"Retry-After": str(int(_user_blocked_until[username] - now))},
                )
            else:
                del _user_blocked_until[username]
                _user_fail_counts.pop(username, None)

        _user_fail_counts[username] = [
            t for t in _user_fail_counts[username] if now - t < _RATE_WINDOW
        ]
        if len(_user_fail_counts[username]) >= _USERNAME_FAIL_LIMIT:
            _user_blocked_until[username] = now + _USERNAME_BLOCK_DURATION
            _user_fail_counts.pop(username, None)
            log.warning("Username '%s' locked for %ds after repeated failures", username, _USERNAME_BLOCK_DURATION)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Account temporarily locked. Please try again later.",
                headers={"Retry-After": str(_USERNAME_BLOCK_DURATION)},
            )


def _record_user_failure(username: str) -> None:
    now = time.time()
    with _user_lock:
        _user_fail_counts[username].append(now)


def _clear_user_failures(username: str) -> None:
    with _user_lock:
        _user_fail_counts.pop(username, None)
        _user_blocked_until.pop(username, None)


def _check_signup_rate_limit(ip: str) -> None:
    """Raise 429 if *ip* is creating accounts too rapidly."""
    now = time.time()
    with _signup_lock:
        if ip in _signup_blocked:
            if now < _signup_blocked[ip]:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many signup attempts. Please try again later.",
                    headers={"Retry-After": str(int(_signup_blocked[ip] - now))},
                )
            else:
                del _signup_blocked[ip]
                _signup_counts.pop(ip, None)

        _signup_counts[ip] = [t for t in _signup_counts[ip] if now - t < _SIGNUP_WINDOW]
        if len(_signup_counts[ip]) >= _SIGNUP_LIMIT:
            _signup_blocked[ip] = now + _SIGNUP_BLOCK
            _signup_counts.pop(ip, None)
            log.warning("IP %s blocked from signup for %ds", ip, _SIGNUP_BLOCK)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many signup attempts. Please try again later.",
                headers={"Retry-After": str(_SIGNUP_BLOCK)},
            )
        _signup_counts[ip].append(now)


# ── Login ──────────────────────────────────────────────────────────────────
@router.post("/login")
def api_login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)
    _check_username_lockout(body.username)

    user = get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password"]):
        _record_failure(ip)
        _record_user_failure(body.username)
        log.warning("Failed login attempt for username='%s' from ip=%s", body.username, ip)
        audit_log("LOGIN_FAILURE", username=body.username, ip=ip, reason="invalid_credentials")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.get("is_active"):
        _record_failure(ip)
        _record_user_failure(body.username)
        log.warning("Login attempt on disabled/pending account username='%s'", body.username)
        # Distinguish between pending-approval accounts and admin-disabled accounts
        pending = user.get("pending_approval", False)
        if pending:
            audit_log("LOGIN_FAILURE", username=body.username, ip=ip, reason="pending_approval")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account pending admin approval")
        audit_log("LOGIN_FAILURE", username=body.username, ip=ip, reason="account_disabled")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    _clear_failures(ip)
    _clear_user_failures(body.username)
    token = create_token(user["id"], user["username"], user["role"], user["agents"])
    log.info("User logged in: username='%s' role='%s'", user["username"], user["role"])
    audit_log("LOGIN_SUCCESS", username=user["username"], ip=ip, role=user["role"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "agents": user["agents"],
        },
    }


# ── Signup ─────────────────────────────────────────────────────────────────
@router.post("/signup")
def api_signup(body: SignupRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    _check_signup_rate_limit(ip)

    if get_user_by_username(body.username):
        audit_log("SIGNUP_FAILURE", username=body.username, ip=ip, reason="username_taken")
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    pw_hash = hash_password(body.password)
    # New signups require admin approval — created as inactive with pending_approval flag
    user = create_user(body.username, pw_hash, role="user", agents=["chat"], is_active=0, pending_approval=True)
    audit_log("SIGNUP_SUCCESS", username=user["username"], ip=ip)
    return {
        "pending_approval": True,
        "message": "Account created successfully. Please wait for admin approval before you can log in.",
    }


# ── Current user ───────────────────────────────────────────────────────────
@router.get("/me")
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


# ── Change own password ────────────────────────────────────────────────────
@router.put("/me/password")
def api_change_password(body: dict, user: dict = Depends(get_current_user)):
    """Allow the authenticated user to change their own password."""
    current_pw = body.get("current_password", "")
    new_pw = body.get("new_password", "")
    if not current_pw or not new_pw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "current_password and new_password are required")
    if len(new_pw) < 8:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password must be at least 8 characters")
    db_user = get_user_by_id(user["sub"])
    if not db_user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if not verify_password(current_pw, db_user["password"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    update_user_password(db_user["id"], hash_password(new_pw))
    audit_log(db_user["username"], "change_password", "own password changed")
    return {"message": "Password updated successfully"}
