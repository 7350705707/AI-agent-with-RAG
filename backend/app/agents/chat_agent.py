"""General Chat agent — conversational chain with hybrid RAG retrieval."""

import logging
from langchain_core.messages import HumanMessage, AIMessage

from app.llm import get_llm, get_llm_streaming, is_no_model_error, is_context_size_error, ensure_model_loaded
from app.utils.prompts import GENERAL_CHAT_PROMPT, GENERAL_CHAT_RAG_PROMPT, QUERY_NORMALIZATION_PROMPT
from app.utils.history_store import search_history, search_history_for_user, get_recent_exchanges, tokenize
from app.chroma_store import search_knowledge, get_knowledge_chunk_count

log = logging.getLogger(__name__)

# Max chars per individual history message — long past messages are trimmed to save context space
_MAX_HIST_MSG_CHARS = 800

# Words that appear in vague follow-up queries ("give me in details", "explain more",
# "tell me about it") but carry zero information for cross-conversation matching.
_FOLLOWUP_STOP = frozenset({
    "give", "more", "tell", "explain", "describe", "elaborate", "continue",
    "please", "further", "expand", "summarize", "brief", "details", "detail",
    "about", "again", "show", "write", "list", "provide", "share", "yes",
    "okay", "sure", "thanks", "thank", "got", "understand", "understood",
    "need", "use", "using", "used", "way", "ways", "thing", "things",
    "help", "helpful", "good", "better", "best", "different", "same",
})


def _is_substantive_query(query: str, min_tokens: int = 2) -> bool:
    """Return True when the query has enough unique topic words to safely
    search across conversations without causing false-positive matches.

    Uses the same stop-word tokenizer as history_store (covering common
    auxiliary verbs, question words, pronouns) and additionally strips
    follow-up meta-words ("explain", "details", "need", "use", etc.).

    Threshold = 2: the query must survive with ≥ 2 genuine topic words
    (e.g. "iran conflict" → True) before cross-conversation search fires.
    Vague follow-ups like "why we need to use it", "give me in details",
    "explain more" produce 0–1 topic words → False → only recent turns used.
    """
    # tokenize() applies history_store's _STOP (includes why/how/what/need etc.)
    words = tokenize(query) - _FOLLOWUP_STOP
    return len(words) >= min_tokens


def _build_history(conversation_id: str, query: str = "", max_pairs: int = 3, user_id: str | None = None) -> list:
    """Return the most relevant past exchanges from the markdown history store.

    Always includes the most recent exchange(s) from the *current* conversation
    so that follow-up questions ("give me in details", "explain more") have the
    correct immediate context.

    Cross-conversation search is only performed when the query is substantive
    enough (≥ 3 content words) to avoid false-positive matches from generic
    follow-up phrases polluting the context.
    """
    # Step 1: always anchor on the last 2 turns of THIS conversation
    recent = get_recent_exchanges(conversation_id, n=2)
    recent_keys = {(e["user"], e["assistant"]) for e in recent}

    # Step 2: only do relevance search when query is substantive
    extra: list = []
    if _is_substantive_query(query):
        if user_id:
            scored = search_history_for_user(user_id, query, top_k=max_pairs)
        else:
            scored = search_history(conversation_id, query, top_k=max_pairs)
        extra = [e for e in scored if (e["user"], e["assistant"]) not in recent_keys]
    # For vague follow-ups: rely entirely on `recent` (current conversation only)

    # Step 3: merge — recent first, deduped, capped
    combined = recent + extra
    exchanges = combined[:max_pairs + 1]

    history: list = []
    for ex in exchanges:
        u = ex["user"]
        a = ex["assistant"]
        if len(u) > _MAX_HIST_MSG_CHARS:
            u = u[:_MAX_HIST_MSG_CHARS] + "…"
        if len(a) > _MAX_HIST_MSG_CHARS:
            a = a[:_MAX_HIST_MSG_CHARS] + "…"
        history.append(HumanMessage(content=u))
        history.append(AIMessage(content=a))
    return history


def _normalize_query(user_input: str) -> str:
    """Use the LLM to correct obvious spelling/typo mistakes in the query.

    Called only when the initial vector search returns empty, so there is no
    extra latency on correctly-spelled queries.
    """
    try:
        llm = get_llm(temperature=0.0)
        result = (QUERY_NORMALIZATION_PROMPT | llm).invoke({"input": user_input})
        normalized = result.content.strip() if hasattr(result, "content") else str(result).strip()
        # Sanity check: reject if the LLM returned something suspiciously long or empty
        if normalized and len(normalized) <= len(user_input) * 2:
            if normalized.lower() != user_input.lower():
                log.info("Query normalized: %r → %r", user_input, normalized)
            return normalized
    except Exception as exc:
        log.debug("Query normalization failed (non-fatal): %s", exc)
    return user_input


def _get_rag_context(search_query: str, original_query: str | None = None) -> tuple[str, list[dict]]:
    """Search knowledge base and return (context_string, source_docs).

    If the initial search returns no results AND *original_query* is provided,
    the query is spell-corrected via the LLM and the search is retried once.
    """
    if get_knowledge_chunk_count() == 0:
        return "", []
    results = search_knowledge(search_query, limit=6)

    # If nothing found, try once more with a spell-corrected query
    if not results and original_query is not None:
        corrected = _normalize_query(original_query)
        if corrected.lower() != search_query.lower():
            results = search_knowledge(corrected, limit=6)

    if not results:
        return "", []
    sources = {}
    context_parts = []
    total_chars = 0
    MAX_CONTEXT_CHARS = 2000
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


def run_chat(conversation_id: str, user_input: str, user_id: str | None = None) -> str:
    """RAG pipeline: (1) hybrid retrieve, (2) answer. Retries with reduced context on overflow."""
    history = _build_history(conversation_id, query=user_input, user_id=user_id)
    context, _sources = _get_rag_context(user_input, original_query=user_input)
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
                    history = _build_history(conversation_id, query=user_input, max_pairs=1, user_id=user_id)
                    context = context[:1500] if context else context
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history and no RAG...")
                    history = []
                    context = ""
                    continue
            raise


def run_chat_stream(conversation_id: str, user_input: str, stop_event=None, user_id: str | None = None):
    """RAG pipeline with streaming. Yields (token, sources) tuples. Retries on context overflow."""
    history = _build_history(conversation_id, query=user_input, user_id=user_id)
    context, source_docs = _get_rag_context(user_input, original_query=user_input)
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
                    history = _build_history(conversation_id, query=user_input, max_pairs=1, user_id=user_id)
                    context = context[:1500] if context else context
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history and no RAG...")
                    history = []
                    context = ""
                    continue
            raise


def run_general_chat_stream(conversation_id: str, user_input: str, stop_event=None, user_id: str | None = None):
    """Pure LLM chat (no RAG). Yields tokens. Retries with less history on context overflow."""
    history = _build_history(conversation_id, query=user_input, user_id=user_id)
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
                    history = _build_history(conversation_id, query=user_input, max_pairs=1, user_id=user_id)
                    continue
                if attempt == 1:
                    log.warning("Context still exceeded; retrying with no history...")
                    history = []
                    continue
            raise
