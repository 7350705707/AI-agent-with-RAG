"""Conversations controller — CRUD and message retrieval routes.

Model  : app.database  (create/list/rename/delete conversation, get_messages)
View   : ConversationOut / MessageOut Pydantic response models
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_optional_user
from app.database import (
    create_conversation,
    delete_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
)
from app.models import ConversationCreate, ConversationOut, MessageOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ── Create ─────────────────────────────────────────────────────────────────
@router.post("", response_model=ConversationOut, status_code=201)
def api_create_conversation(
    body: ConversationCreate,
    user: dict | None = Depends(get_optional_user),
):
    user_id = user["sub"] if user else None
    try:
        result = create_conversation(body.agent_type, body.title, user_id=user_id)
    except Exception as exc:
        log.error("Failed to create conversation (agent=%s): %s", body.agent_type, exc, exc_info=True)
        raise HTTPException(500, "Failed to create conversation")
    log.info("Conversation created: id=%s agent=%s user=%s", result["id"], body.agent_type, user_id)
    return result


# ── List ───────────────────────────────────────────────────────────────────
@router.get("", response_model=list[ConversationOut])
def api_list_conversations(
    agent_type: str | None = None,
    user: dict | None = Depends(get_optional_user),
):
    user_id = user["sub"] if user else None
    try:
        return list_conversations(agent_type, user_id=user_id)
    except Exception as exc:
        log.error("Failed to list conversations (user=%s): %s", user_id, exc, exc_info=True)
        raise HTTPException(500, "Failed to retrieve conversations")


# ── Rename ─────────────────────────────────────────────────────────────────
@router.patch("/{conv_id}")
def api_rename_conversation(
    conv_id: str,
    body: dict,
    _user: dict | None = Depends(get_optional_user),
):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(400, "Title required")
    try:
        if not rename_conversation(conv_id, title):
            raise HTTPException(404, "Conversation not found")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to rename conversation %s: %s", conv_id, exc, exc_info=True)
        raise HTTPException(500, "Failed to rename conversation")
    return {"id": conv_id, "title": title}


# ── Delete ─────────────────────────────────────────────────────────────────
@router.delete("/{conv_id}", status_code=204)
def api_delete_conversation(
    conv_id: str,
    _user: dict | None = Depends(get_optional_user),
):
    try:
        if not delete_conversation(conv_id):
            raise HTTPException(404, "Conversation not found")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to delete conversation %s: %s", conv_id, exc, exc_info=True)
        raise HTTPException(500, "Failed to delete conversation")
    log.info("Conversation deleted: id=%s", conv_id)


# ── Messages ───────────────────────────────────────────────────────────────
@router.get("/{conv_id}/messages", response_model=list[MessageOut])
def api_get_messages(
    conv_id: str,
    _user: dict | None = Depends(get_optional_user),
):
    try:
        return get_messages(conv_id)
    except Exception as exc:
        log.error("Failed to fetch messages for conv %s: %s", conv_id, exc, exc_info=True)
        raise HTTPException(500, "Failed to retrieve messages")
