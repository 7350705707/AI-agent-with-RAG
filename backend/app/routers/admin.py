"""Admin controller — user management routes (admin-only).

Model  : app.database  (list/create/update/delete users, update password)
View   : UserOut Pydantic response model
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import hash_password, require_admin
from app.database import (
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    update_user,
    update_user_password,
)
from app.models import UserCreate, UserOut, UserPasswordUpdate, UserUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── List users ─────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserOut])
def api_list_users(_admin: dict = Depends(require_admin)):
    return list_users()


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
