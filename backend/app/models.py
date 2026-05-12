"""Pydantic request/response schemas."""

import re

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    conversation_id: str
    message: str = Field(..., min_length=1, max_length=10000)
    file_ids: list[str] = Field(
        default_factory=list,
        description="Optional list of uploaded file IDs to include as extra context",
    )


class ExamRequest(BaseModel):
    conversation_id: str
    instructions: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="e.g. 'Create 10 MCQs and 5 short-answer questions'",
    )
    file_ids: list[str] = Field(
        default_factory=list,
        description="List of previously uploaded file IDs to use as source material",
    )
    mcq_count: int = Field(default=10, ge=0, le=100)
    tf_count: int = Field(default=10, ge=0, le=100)
    fitb_count: int = Field(default=10, ge=0, le=100)


class ConversationCreate(BaseModel):
    agent_type: str = Field(..., pattern="^(chat|exam|general)$")
    title: str = Field(default="New Chat", max_length=200)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sources: list = []
    created_at: str


class ConversationOut(BaseModel):
    id: str
    agent_type: str
    title: str
    created_at: str
    updated_at: str


# ── Auth models ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        errors = []
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain at least {', '.join(errors)}")
        return v


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)
    role: str = Field(default="user", pattern="^(user|admin)$")
    agents: list[str] = Field(default_factory=lambda: ["chat"])


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    agents: list[str] | None = None
    is_active: bool | None = None


class UserPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    agents: list[str]
    is_active: bool
    created_at: str
    updated_at: str
