"""Backward-compatibility shim — import from app.utils.state instead."""
from app.utils.state import *  # noqa: F401,F403
from app.utils.state import llm_semaphore  # noqa: F401

import asyncio

# ── LLM concurrency limiter ───────────────────────────────────────────────
# LM Studio processes one request at a time (single model on GPU).
# This semaphore prevents multiple simultaneous requests from colliding
# and causing context / resource errors.
llm_semaphore = asyncio.Semaphore(1)
