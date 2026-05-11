"""Chat controller — RAG chat and general chat streaming routes.

Model  : app.database / app.agents.chat_agent / app.history_store
View   : SSE (Server-Sent Events) streaming responses
"""

import asyncio
import json
import logging
import queue as _queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agents.agentic_rag import run_agentic_chat, run_agentic_chat_stream
from app.agents.chat_agent import run_chat, run_chat_stream, run_general_chat_stream
from app.auth import get_optional_user
from app.database import add_message
from app.utils.history_store import append_exchange
from app.models import ChatRequest
from app.utils.sanitizer import sanitize_user_input
import app.utils.state as _state
from app.utils.state import llm_semaphore

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# ── RAG Chat (non-streaming) ───────────────────────────────────────────────
@router.post("/chat")
def api_chat(body: ChatRequest, _user: dict | None = Depends(get_optional_user)):
    body.message = sanitize_user_input(body.message)
    add_message(body.conversation_id, "user", body.message)
    log.info("Chat request conv_id=%s", body.conversation_id)
    try:
        response = run_chat(body.conversation_id, body.message)
    except Exception as e:
        log.error("Chat LLM error conv_id=%s: %s", body.conversation_id, e, exc_info=True)
        raise HTTPException(500, f"LLM error: {e}")
    add_message(body.conversation_id, "assistant", response)
    return {"conversation_id": body.conversation_id, "response": response}


# ── RAG Chat (streaming) ───────────────────────────────────────────────────
@router.post("/chat/stream")
async def api_chat_stream(
    request: Request,
    body: ChatRequest,
    _user: dict | None = Depends(get_optional_user),
):
    """Stream RAG chat response tokens via SSE. Cancels when client disconnects."""
    body.message = sanitize_user_input(body.message)
    add_message(body.conversation_id, "user", body.message)
    conv_id = body.conversation_id
    user_id = _user["sub"] if _user else None

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        full = ""
        all_sources: list = []
        try:
            for token, sources in run_chat_stream(conv_id, body.message, stop_event, user_id=user_id):
                if stop_event.is_set():
                    break
                full += token
                if sources:
                    all_sources = sources
                q.put(("token", token, sources))
            cited = [s for s in all_sources if s["filename"].lower() in full.lower()]
            q.put(("done", full, cited))
        except Exception as e:
            q.put(("error", str(e), []))

    async def event_stream():
        full_response = ""
        cited_sources: list = []

        # Queue-depth guard — reject only when the backlog is truly full
        if _state.llm_inflight >= _state.LLM_QUEUE_MAX:
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Server is overloaded. Please try again later.'})}\n\n"
            return

        _state.llm_inflight += 1
        try:
            # If the model is busy, tell the client they're queued — then WAIT
            if llm_semaphore.locked():
                yield f"data: {json.dumps({'token': '', 'done': False, 'queued': True})}\n\n"

            async with llm_semaphore:
                threading.Thread(target=_run, daemon=True).start()
                while True:
                    if await request.is_disconnected():
                        stop_event.set()
                        return
                    try:
                        kind, data, extra = q.get_nowait()
                    except _queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    if kind == "done":
                        cited_sources = extra
                        yield f"data: {json.dumps({'token': '', 'done': True, 'sources': cited_sources})}\n\n"
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'token': '', 'done': True, 'error': data})}\n\n"
                        break
                    else:
                        full_response += data
                        yield f"data: {json.dumps({'token': data, 'done': False})}\n\n"
        finally:
            _state.llm_inflight -= 1
            if full_response and not stop_event.is_set():
                add_message(conv_id, "assistant", full_response, sources=cited_sources)
                append_exchange(conv_id, body.message, full_response)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── General Chat — no RAG (streaming) ─────────────────────────────────────
@router.post("/general-chat/stream")
async def api_general_chat_stream(
    request: Request,
    body: ChatRequest,
    _user: dict | None = Depends(get_optional_user),
):
    """Stream pure LLM chat (no RAG) via SSE. Cancels when client disconnects."""
    body.message = sanitize_user_input(body.message)
    add_message(body.conversation_id, "user", body.message)
    conv_id = body.conversation_id
    user_id = _user["sub"] if _user else None

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        full = ""
        try:
            for token in run_general_chat_stream(conv_id, body.message, stop_event, user_id=user_id):
                if stop_event.is_set():
                    break
                full += token
                q.put(("token", token))
            q.put(("done", full))
        except Exception as e:
            q.put(("error", str(e)))

    async def event_stream():
        full_response = ""

        if _state.llm_inflight >= _state.LLM_QUEUE_MAX:
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Server is overloaded. Please try again later.'})}\n\n"
            return

        _state.llm_inflight += 1
        try:
            if llm_semaphore.locked():
                yield f"data: {json.dumps({'token': '', 'done': False, 'queued': True})}\n\n"

            async with llm_semaphore:
                threading.Thread(target=_run, daemon=True).start()
                while True:
                    if await request.is_disconnected():
                        stop_event.set()
                        return
                    try:
                        item = q.get_nowait()
                    except _queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    kind = item[0]
                    if kind == "done":
                        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'token': '', 'done': True, 'error': item[1]})}\n\n"
                        break
                    else:
                        full_response += item[1]
                        yield f"data: {json.dumps({'token': item[1], 'done': False})}\n\n"
        finally:
            _state.llm_inflight -= 1
            if full_response and not stop_event.is_set():
                add_message(conv_id, "assistant", full_response)
                append_exchange(conv_id, body.message, full_response)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Agentic RAG Chat (non-streaming) ──────────────────────────────────────
@router.post("/agentic-chat")
def api_agentic_chat(body: ChatRequest, _user: dict | None = Depends(get_optional_user)):
    """Agentic tool-calling loop: LLM decides when/how to search documents."""
    body.message = sanitize_user_input(body.message)
    add_message(body.conversation_id, "user", body.message)
    user_id = _user["sub"] if _user else None
    log.info("Agentic chat request conv_id=%s", body.conversation_id)
    try:
        response = run_agentic_chat(body.conversation_id, body.message, user_id=user_id)
    except Exception as e:
        log.error("Agentic chat error conv_id=%s: %s", body.conversation_id, e, exc_info=True)
        raise HTTPException(500, f"LLM error: {e}")
    add_message(body.conversation_id, "assistant", response)
    return {"conversation_id": body.conversation_id, "response": response}


# ── Agentic RAG Chat (streaming) ───────────────────────────────────────────
@router.post("/agentic-chat/stream")
async def api_agentic_chat_stream(
    request: Request,
    body: ChatRequest,
    _user: dict | None = Depends(get_optional_user),
):
    """Streaming agentic tool-calling loop via SSE.

    SSE event shapes:
      {"thinking": "<tool>(<args>)", "done": false}   — tool invocation step
      {"token": "<text>",           "done": false}   — streamed answer chunk
      {"token": "",                 "done": true, "sources": [...]}
      {"token": "",                 "done": true, "error": "..."}
      {"token": "",                 "done": false, "queued": true}
    """
    body.message = sanitize_user_input(body.message)
    add_message(body.conversation_id, "user", body.message)
    conv_id = body.conversation_id
    user_id = _user["sub"] if _user else None

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        full = ""
        all_sources: list = []
        try:
            for kind, data, sources in run_agentic_chat_stream(
                conv_id, body.message, stop_event, user_id=user_id
            ):
                if stop_event.is_set():
                    break
                if kind == "thinking":
                    q.put(("thinking", data, []))
                elif kind == "token":
                    full += data
                    if sources:
                        all_sources = sources
                    q.put(("token", data, sources))
            # Pass all retrieved sources — they are authentic (came from actual tool calls).
            # Do not filter by filename-in-text: smaller local LLMs often paraphrase
            # citations rather than writing the exact filename, which would silently
            # drop every source reference shown to the user.
            q.put(("done", full, all_sources))
        except Exception as exc:
            q.put(("error", str(exc), []))

    async def event_stream():
        full_response = ""
        cited_sources: list = []

        if _state.llm_inflight >= _state.LLM_QUEUE_MAX:
            yield f"data: {json.dumps({'token': '', 'done': True, 'error': 'Server is overloaded. Please try again later.'})}\n\n"
            return

        _state.llm_inflight += 1
        try:
            if llm_semaphore.locked():
                yield f"data: {json.dumps({'token': '', 'done': False, 'queued': True})}\n\n"

            async with llm_semaphore:
                threading.Thread(target=_run, daemon=True).start()
                while True:
                    if await request.is_disconnected():
                        stop_event.set()
                        return
                    try:
                        kind, data, extra = q.get_nowait()
                    except _queue.Empty:
                        await asyncio.sleep(0.01)
                        continue

                    if kind == "done":
                        cited_sources = extra
                        yield f"data: {json.dumps({'token': '', 'done': True, 'sources': cited_sources})}\n\n"
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'token': '', 'done': True, 'error': data})}\n\n"
                        break
                    elif kind == "thinking":
                        yield f"data: {json.dumps({'thinking': data, 'done': False})}\n\n"
                    else:
                        full_response += data
                        yield f"data: {json.dumps({'token': data, 'done': False})}\n\n"
        finally:
            _state.llm_inflight -= 1
            if full_response and not stop_event.is_set():
                add_message(conv_id, "assistant", full_response, sources=cited_sources)
                append_exchange(conv_id, body.message, full_response)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
