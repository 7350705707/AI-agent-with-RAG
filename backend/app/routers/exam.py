"""Exam paper generator controller — generation and streaming routes.

Model  : app.agents.exam_agent / app.database
View   : SSE (Server-Sent Events) streaming responses + JSON exam output
"""

import asyncio
import json
import logging
import queue as _queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agents.exam_agent import (
    extract_topics_from_files,
    parse_exam_to_json,
    run_exam_generator,
    run_exam_generator_steps,
)
from app.auth import get_current_user
from app.config import UPLOAD_DIR
from app.database import add_message, register_conversation_file, save_exam_structured_questions, get_exam_structured_questions
from app.llm import ensure_model_loaded, is_no_model_error
from app.models import ExamRequest, TopicsRequest
from app.utils.sanitizer import sanitize_user_input
import app.utils.state as _state
from app.utils.state import llm_semaphore

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exam", tags=["exam"])


# ── Structured questions (per-conversation persistence) ───────────────────
@router.get("/questions/{conversation_id}")
def api_get_questions(conversation_id: str, _user: dict = Depends(get_current_user)):
    """Return previously saved structured questions for a conversation."""
    questions = get_exam_structured_questions(conversation_id)
    return {"questions": questions}


@router.post("/questions/{conversation_id}", status_code=201)
def api_save_questions(conversation_id: str, body: dict, _user: dict = Depends(get_current_user)):
    """Persist structured questions for a conversation."""
    questions = body.get("questions", [])
    if not isinstance(questions, list):
        raise HTTPException(400, "questions must be a list")
    save_exam_structured_questions(conversation_id, questions)
    return {"saved": True}


# ── Topic extraction ───────────────────────────────────────────────────────
@router.post("/topics")
def api_exam_topics(body: TopicsRequest, _user: dict = Depends(get_current_user)):
    """Extract main topics from uploaded documents to pre-populate the exam config modal."""
    try:
        topics = extract_topics_from_files(body.file_ids)
    except Exception as e:
        log.warning("Topic extraction error: %s", e)
        raise HTTPException(500, f"Topic extraction failed: {e}")
    return {"topics": topics}


# ── Exam (non-streaming) ───────────────────────────────────────────────────
@router.post("")
def api_exam(body: ExamRequest, _user: dict = Depends(get_current_user)):
    body.instructions = sanitize_user_input(body.instructions, max_length=5000)
    add_message(body.conversation_id, "user", body.instructions)
    response = ""
    for attempt in range(2):
        try:
            response = run_exam_generator(
                body.conversation_id, body.instructions, body.file_ids,
                mcq_count=body.mcq_count, tf_count=body.tf_count, fitb_count=body.fitb_count,
            )
            break
        except Exception as e:
            if attempt == 0 and is_no_model_error(e):
                log.warning("No model loaded (exam); attempting auto-load...")
                ensure_model_loaded()
                continue
            raise HTTPException(500, f"LLM error: {e}")
    add_message(body.conversation_id, "assistant", response)
    return {"conversation_id": body.conversation_id, "response": response}


# ── Exam (streaming) ───────────────────────────────────────────────────────
@router.post("/stream")
async def api_exam_stream(
    request: Request,
    body: ExamRequest,
    _user: dict = Depends(get_current_user),
):
    body.instructions = sanitize_user_input(body.instructions, max_length=5000)
    add_message(body.conversation_id, "user", body.instructions)
    conv_id = body.conversation_id

    # Register uploaded files so they are deleted with the conversation
    for fid in (body.file_ids or []):
        fdir = UPLOAD_DIR / fid
        if fdir.is_dir():
            for fp in fdir.iterdir():
                if fp.is_file():
                    register_conversation_file(conv_id, fid, str(fp))
                    break

    stop_event = threading.Event()
    q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        final = ""

        def _do_run() -> None:
            nonlocal final
            for step, label, content in run_exam_generator_steps(
                conv_id, body.instructions, body.file_ids,
                mcq_count=body.mcq_count, tf_count=body.tf_count, fitb_count=body.fitb_count,
                stop_event=stop_event,
            ):
                if stop_event.is_set():
                    return
                final = content
                q.put(("event", step, label, content))
            q.put(("done", final))

        try:
            _do_run()
        except Exception as e:
            if is_no_model_error(e):
                log.warning("No model loaded (exam stream); attempting auto-load...")
                if ensure_model_loaded():
                    final = ""
                    try:
                        _do_run()
                        return
                    except Exception as e2:
                        q.put(("error", str(e2)))
                        return
            q.put(("error", str(e)))

    async def event_stream():
        # Queue-depth guard — reject only when the backlog is truly full
        if _state.llm_inflight >= _state.LLM_QUEUE_MAX:
            yield f"data: {json.dumps({'step': 'error', 'label': 'Server is overloaded. Please try again later.', 'content': ''})}\n\n"
            return

        _state.llm_inflight += 1
        final_content = ""
        try:
            # If the model is busy, tell the client they're queued — then WAIT
            if llm_semaphore.locked():
                yield f"data: {json.dumps({'step': 'queued', 'label': 'Waiting for model\u2026', 'content': '', 'queued': True})}\n\n"

            async with llm_semaphore:
                # Start the LLM thread only after acquiring the semaphore
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
                        final_content = item[1]
                        break
                    elif kind == "error":
                        yield f"data: {json.dumps({'step': 'error', 'label': item[1], 'content': ''})}\n\n"
                        return
                    else:
                        _, step, label, content = item
                        final_content = content
                        yield f"data: {json.dumps({'step': step, 'label': label, 'content': content})}\n\n"
        finally:
            _state.llm_inflight -= 1
            if final_content and not stop_event.is_set():
                add_message(conv_id, "assistant", final_content)
                try:
                    questions = parse_exam_to_json(final_content)
                    if questions:
                        save_exam_structured_questions(conv_id, questions)
                        yield f"data: {json.dumps({'step': 'structured', 'label': 'structured', 'content': '', 'questions': questions})}\n\n"
                except Exception as parse_err:
                    log.warning("Failed to parse exam to JSON: %s", parse_err)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
