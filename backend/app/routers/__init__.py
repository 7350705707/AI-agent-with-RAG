"""Backend routers (controllers) package.

Each module in this package is a FastAPI APIRouter that owns one domain
of the API surface:

  auth.py          — /api/auth/*         login / signup / me
  llm_router.py    — /api/models/*       LLM model management
  conversations.py — /api/conversations/* conversation CRUD + messages
  admin.py         — /api/admin/*        user management (admin only)
  knowledge.py     — /api/knowledge/*    knowledge-base documents
  chat.py          — /api/chat/* and /api/general-chat/*  chat streaming
  exam.py          — /api/exam/*         exam paper generator
  files.py         — /api/upload         conversation file uploads
"""
