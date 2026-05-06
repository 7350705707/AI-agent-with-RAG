"""General Chat agent — conversational chain with hybrid RAG retrieval."""

import logging
from langchain_core.messages import HumanMessage, AIMessage

from app.llm import get_llm, get_llm_streaming, is_no_model_error, is_context_size_error, ensure_model_loaded
from app.prompts import GENERAL_CHAT_PROMPT, GENERAL_CHAT_RAG_PROMPT
from app.database import get_messages
from app.chroma_store import search_knowledge, get_knowledge_chunk_count

log = logging.getLogger(__name__)


# Max chars per individual history message — long past messages are trimmed to save context space
_MAX_HIST_MSG_CHARS = 800


def _build_history(conversation_id: str, max_pairs: int = 3) -> list:
    """Return the last `max_pairs` conversation turns, each message capped at _MAX_HIST_MSG_CHARS."""
    rows = get_messages(conversation_id)
    history = []
    for r in rows:
        content = r["content"]
        if len(content) > _MAX_HIST_MSG_CHARS:
            content = content[:_MAX_HIST_MSG_CHARS] + "…"
        if r["role"] == "user":
            history.append(HumanMessage(content=content))
        else:
            history.append(AIMessage(content=content))
    if len(history) > max_pairs * 2:
        history = history[-(max_pairs * 2):]
    return history


def _get_rag_context(search_query: str) -> tuple[str, list[dict]]:
    """Search knowledge base and return (context_string, source_docs)."""
    if get_knowledge_chunk_count() == 0:
        return "", []
    results = search_knowledge(search_query, limit=6)
    if not results:
        return "", []
    sources = {}
    context_parts = []
    total_chars = 0
    MAX_CONTEXT_CHARS = 3500
    for r in results:
        meta = r.get("metadata", {})
        position = meta.get("position", "")
        heading = meta.get("heading_hint", "")
        position_note = f" [{position} of document]" if position else ""
        heading_note = f"\nSection: {heading}" if heading else ""
        chunk_text = f"[Source: {r.get('filename', 'unknown')}{position_note}]{heading_note}\n{r['content']}"
        if total_chars + len(chunk_text) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total_chars
            if remaining > 200:
                chunk_text = chunk_text[:remaining] + "…"
            else:
                break
        fname = r.get("filename", "unknown")
        doc_id = r.get("doc_id", "")
        sources[doc_id] = fname
        context_parts.append(chunk_text)
        total_chars += len(chunk_text)
        if total_chars >= MAX_CONTEXT_CHARS:
            break
    if not context_parts:
        return "", []
    context = "\n\n---\n\n".join(context_parts)
    source_docs = [{"doc_id": did, "filename": fn} for did, fn in sources.items()]
    return context, source_docs


def run_chat(conversation_id: str, user_input: str) -> str:
    """RAG pipeline: (1) hybrid retrieve, (2) answer. Retries with reduced context on overflow."""
    history = _build_history(conversation_id)
    context, _sources = _get_rag_context(user_input)
    for attempt in range(3):
        llm = get_llm(temperature=0.5)
        try:
            if context:
                chain = GENERAL_CHAT_RAG_PROMPT | llm
                return chain.invoke({"history": history, "input": user_input, "context": context})
            chain = GENERAL_CHAT_PROMPT | llm
            return chain.invoke({"history": history, "input": user_input})
        except Exception as e:
            if attempt == 0 and is_no_model_error(e):
                log.warning("No model loaded; attempting auto-load before retry...")
                ensure_model_loaded()
                continue
            if is_context_size_error(e):
                if attempt == 0:
                    log.warning("Context size exceeded; retrying with shorter history...")
                    history = _build_history(conversation_id, max_pairs=1)
                    context = context[:1500] if context else context
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history and no RAG...")
                    history = []
                    context = ""
                    continue
            raise


def run_chat_stream(conversation_id: str, user_input: str, stop_event=None):
    """RAG pipeline with streaming. Yields (token, sources) tuples. Retries on context overflow."""
    history = _build_history(conversation_id)
    context, source_docs = _get_rag_context(user_input)
    for attempt in range(3):
        llm = get_llm_streaming(temperature=0.5)
        tokens_yielded = 0
        try:
            if context:
                chain = GENERAL_CHAT_RAG_PROMPT | llm
                for token in chain.stream({"history": history, "input": user_input, "context": context}):
                    if stop_event and stop_event.is_set():
                        return
                    tokens_yielded += 1
                    yield token, source_docs
            else:
                chain = GENERAL_CHAT_PROMPT | llm
                for token in chain.stream({"history": history, "input": user_input}):
                    if stop_event and stop_event.is_set():
                        return
                    tokens_yielded += 1
                    yield token, []
            return
        except Exception as e:
            if attempt == 0 and tokens_yielded == 0 and is_no_model_error(e):
                log.warning("No model loaded; attempting auto-load before retry...")
                ensure_model_loaded()
                continue
            if tokens_yielded == 0 and is_context_size_error(e):
                if attempt == 0:
                    log.warning("Context size exceeded; retrying with shorter history...")
                    history = _build_history(conversation_id, max_pairs=1)
                    context = context[:1500] if context else context
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history and no RAG...")
                    history = []
                    context = ""
                    continue
            raise


def run_general_chat_stream(conversation_id: str, user_input: str, stop_event=None):
    """Pure LLM chat (no RAG). Yields tokens. Retries with less history on context overflow."""
    history = _build_history(conversation_id)
    for attempt in range(3):
        llm = get_llm_streaming(temperature=0.5)
        tokens_yielded = 0
        try:
            chain = GENERAL_CHAT_PROMPT | llm
            for token in chain.stream({"history": history, "input": user_input}):
                if stop_event and stop_event.is_set():
                    return
                tokens_yielded += 1
                yield token
            return
        except Exception as e:
            if attempt == 0 and tokens_yielded == 0 and is_no_model_error(e):
                log.warning("No model loaded; attempting auto-load before retry...")
                ensure_model_loaded()
                continue
            if tokens_yielded == 0 and is_context_size_error(e):
                if attempt == 0:
                    log.warning("Context size exceeded; retrying with shorter history...")
                    history = _build_history(conversation_id, max_pairs=1)
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history...")
                    history = []
                    continue
            raise
