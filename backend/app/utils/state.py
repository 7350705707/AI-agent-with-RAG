"""Global shared application state.

Centralises runtime state that needs to be shared across routers without
circular imports. Import from here instead of defining singletons in main.py.
"""

import asyncio

# ── LLM concurrency limiter ───────────────────────────────────────────────
# LM Studio processes one request at a time (single model on GPU).
# The semaphore serialises LLM access; requests that arrive while the model
# is busy WAIT (are queued by asyncio) rather than being rejected.
llm_semaphore = asyncio.Semaphore(1)

# Maximum number of requests allowed to be in-flight (waiting + processing)
# simultaneously.  Requests beyond this cap are rejected with a 503-style
# SSE error so the queue never grows unboundedly.
LLM_QUEUE_MAX = 10

# Current in-flight count (incremented before awaiting the semaphore,
# decremented in the finally block).  Safe without a lock — asyncio is
# single-threaded cooperative multitasking.
llm_inflight: int = 0

# ── Embedding availability ────────────────────────────────────────────────
# Set to True in main.py startup once the embedding model is confirmed ready.
# Routes that require embeddings check this flag via the require_embedding dep.
embedding_ready: bool = False
