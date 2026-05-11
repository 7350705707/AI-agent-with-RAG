"""Agentic Tool-Calling Loop for RAG AI Chat.

Implements a ReAct-style loop where the LLM autonomously decides which tools
to call, executes them, observes results, and iterates until it can produce a
grounded final answer.

Available tools the agent may call:
  - search_knowledge_base  : Hybrid vector + BM25 search over uploaded docs
  - expand_search_keywords : Generate synonyms / related terms for a query

Loop flow:
  1. Build messages = [system_prompt] + history + [user_message]
  2. Call LLM with tools bound; if it returns tool_calls → execute each
  3. Append ToolMessage results; repeat up to MAX_AGENT_ITERATIONS
  4. When LLM returns plain text (no tool calls), stream that as final answer
  5. Yield ("thinking", ...) events during tool calls so the frontend can
     display live progress, then yield ("token", ...) for the streamed reply
"""

import logging
import re
from typing import Generator, Optional

# Keywords that signal the user explicitly wants a database / document search
_EXPLICIT_SEARCH_PATTERNS = re.compile(
    r"\b("
    r"search (in|the|your|my|our|this)?\s*(database|db|document|docs?|file|knowledge|kb|upload|store)"
    r"|look (in|into|through|at) (the|your|my)?\s*(database|db|document|docs?|file|knowledge|kb|upload)"
    r"|find (in|from|inside|within) (the|your|my)?\s*(database|db|document|docs?|file|knowledge|upload)"
    r"|check (the|your|my)?\s*(database|db|document|docs?|file|knowledge|upload)"
    r"|from (the|your|my)?\s*(database|db|document|docs?|file|knowledge|upload|pdf|pptx|docx)"
    r"|in (the|your|my)?\s*(database|db|document|docs?|file|knowledge|upload|pdf|pptx|docx)"
    r"|search (for|about|on)\b"
    r"|tell me from (the|your|my)?\s*(database|db|document|docs?|file|knowledge|upload)"
    r"|based on (the|your|my)?\s*(document|docs?|file|knowledge|upload|pdf|pptx|docx)"
    r"|according to (the|my|your)?\s*(document|docs?|file|knowledge|upload|pdf|pptx|docx)"
    r")",
    re.IGNORECASE,
)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.chroma_store import get_knowledge_chunk_count, search_knowledge
from app.config import LM_STUDIO_BASE_URL
from app.llm import (
    ensure_model_loaded,
    get_active_model,
    is_context_size_error,
    is_no_model_error,
)
from app.utils.history_store import (
    get_recent_exchanges,
    search_history,
    search_history_for_user,
    tokenize,
)

log = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5
MAX_SEARCH_CHARS = 3000
_MAX_HIST_CHARS = 800

# Stop-words that indicate vague follow-ups — not substantive enough for cross-turn search
_FOLLOWUP_STOP = frozenset({
    "give", "more", "tell", "explain", "describe", "elaborate", "continue",
    "please", "further", "expand", "summarize", "brief", "details", "detail",
    "about", "again", "show", "write", "list", "provide", "share", "yes",
    "okay", "sure", "thanks", "thank", "got", "understand", "understood",
    "need", "use", "using", "used", "way", "ways", "thing", "things",
    "help", "helpful", "good", "better", "best", "different", "same",
})

# ── Tool JSON schemas exposed to the LLM ──────────────────────────────────

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the uploaded knowledge base documents for relevant information. "
                "Use this when the user's question may be answered by uploaded documents. "
                "Returns relevant text chunks with source filenames. "
                "Call multiple times with different focused queries to gather comprehensive info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Focused keywords or short phrase to search for (3-10 words).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of result chunks to return (1-10, default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_search_keywords",
            "description": (
                "Generate synonyms and related domain terms for a search query. "
                "Use this when search_knowledge_base returns no useful results, "
                "to discover alternate terminology the documents might use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The original query to expand with related terms.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────

def _format_search_results(results: list) -> str:
    """Format raw search_knowledge() results into a string for the LLM ToolMessage."""
    parts: list[str] = []
    total = 0
    for r in results:
        meta = r.get("metadata", {})
        fname = r.get("filename", "unknown")
        position = meta.get("position", "")
        heading = meta.get("heading_hint", "")

        header = f"[{fname}" + (f", {position}]" if position else "]")
        if heading:
            header += f"\nSection: {heading}"
        chunk = f"{header}\n{r['content']}"

        if total + len(chunk) > MAX_SEARCH_CHARS:
            remaining = MAX_SEARCH_CHARS - total
            if remaining > 200:
                chunk = chunk[:remaining] + "…"
            else:
                break
        parts.append(chunk)
        total += len(chunk)
        if total >= MAX_SEARCH_CHARS:
            break

    return "\n\n---\n\n".join(parts)


def _tool_search_knowledge_base(query: str, limit: int = 5) -> str:
    """Execute a hybrid knowledge-base search and return formatted results."""
    limit = min(max(1, int(limit)), 10)
    if get_knowledge_chunk_count() == 0:
        return "No documents have been uploaded to the knowledge base yet."

    results = search_knowledge(query, limit=limit)
    if not results:
        return f"No relevant content found for query: '{query}'"

    return _format_search_results(results)


def _tool_expand_search_keywords(query: str) -> str:
    """Use the LLM to expand a query into related synonyms and domain terms."""
    try:
        from app.llm import get_llm
        from app.utils.prompts import KEYWORD_EXPANSION_PROMPT

        llm = get_llm(temperature=0.1, num_predict=60)
        result = (KEYWORD_EXPANSION_PROMPT | llm).invoke({"input": query})
        return result.strip()
    except Exception as exc:
        log.warning("expand_search_keywords failed: %s", exc)
        return query


def _dispatch_tool(name: str, args: dict) -> str:
    """Route a tool call to its implementation and return a string result."""
    if name == "search_knowledge_base":
        return _tool_search_knowledge_base(**args)
    if name == "expand_search_keywords":
        return _tool_expand_search_keywords(**args)
    return f"Unknown tool: '{name}'"


# ── Conversation history helpers ─────────────────────────────────────────

def _is_substantive_query(query: str, min_tokens: int = 2) -> bool:
    """Return True when the query has enough unique topic words for cross-turn search.

    Vague follow-ups like 'explain more', 'give details', 'tell me again' produce
    0-1 content words after stop-word removal → return False → only recent turns used.
    """
    words = tokenize(query) - _FOLLOWUP_STOP
    return len(words) >= min_tokens


def _build_history(
    conversation_id: str,
    query: str = "",
    user_id: str | None = None,
    max_pairs: int = 4,
) -> list:
    """Build LangChain message history by combining two sources:

    1. **Recent exchanges** (always included) — the last 2 turns of THIS conversation
       so that follow-up questions always have immediate context.
    2. **Relevant past exchanges** (when query is substantive) — searched by
       Jaccard word-overlap across the current conversation (or all conversations
       of the user when user_id is provided), so topic-relevant prior answers
       are injected even if they happened many turns ago.

    Deduplication ensures the same exchange is not injected twice.
    """
    # Step 1: anchor on the most recent turns (guaranteed context)
    recent = get_recent_exchanges(conversation_id, n=2)
    recent_keys = {(e["user"], e["assistant"]) for e in recent}

    # Step 2: relevance search only for substantive queries
    extra: list = []
    if query and _is_substantive_query(query):
        if user_id:
            # Search across ALL this user's conversations
            scored = search_history_for_user(user_id, query, top_k=max_pairs)
        else:
            # Search within this conversation only
            scored = search_history(conversation_id, query, top_k=max_pairs)
        extra = [e for e in scored if (e["user"], e["assistant"]) not in recent_keys]

    # Step 3: merge (recent first), deduplicate, cap
    combined = (recent + extra)[:max_pairs]

    messages: list = []
    for ex in combined:
        u = ex["user"]
        a = ex["assistant"]
        if len(u) > _MAX_HIST_CHARS:
            u = u[:_MAX_HIST_CHARS] + "…"
        if len(a) > _MAX_HIST_CHARS:
            a = a[:_MAX_HIST_CHARS] + "…"
        messages.append(HumanMessage(content=u))
        messages.append(AIMessage(content=a))
    return messages


# ── Raw LLM factory (no StrOutputParser — needed for tool_calls) ───────────

def _raw_llm(temperature: float = 0.5, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=get_active_model(),
        base_url=LM_STUDIO_BASE_URL,
        api_key="lm-studio",
        temperature=temperature,
        max_tokens=1024,
        streaming=streaming,
    )


# ── Agent system prompts ──────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to a knowledge base of uploaded documents.\n\n"
    "DECISION RULE — use your own judgment each time:\n"
    "- If the question is about general knowledge you are already confident. "
    "answer DIRECTLY from your own knowledge WITHOUT calling any tool.\n"
    "- If the question is about specific uploaded documents, technical details you are "
    "uncertain about, or information that is likely in the knowledge base, "
    "call search_knowledge_base FIRST, then answer.\n"
    "- If search_knowledge_base returns no useful results, call expand_search_keywords "
    "and try one more search with the expanded terms before concluding the documents "
    "don't cover the topic.\n"
    "- Never call tools for greetings, simple math, or questions clearly about the "
    "ongoing conversation.\n\n"
    "CITATION RULES:\n"
    "- Cite [filename] ONLY for facts retrieved from that document.\n"
    "- Never fabricate citations. Label your own knowledge as 'From general knowledge:' "
    "with no citation.\n\n"
    "CONVERSATION MEMORY: Answer questions about previous messages from history provided.\n"
    "For general knowledge, use an Indian perspective where applicable "
    "(geography, laws, currency ₹, current events)."
)

# Injected as an extra SystemMessage when the user explicitly asks to search documents
_FORCE_SEARCH_OVERRIDE = (
    "OVERRIDE: The user has explicitly asked you to search the knowledge base / database. "
    "You MUST call search_knowledge_base at least once before answering, "
    "regardless of whether you think you already know the answer."
)


def _detect_explicit_search_intent(query: str) -> bool:
    """Return True when the user explicitly asks to search documents/database."""
    return bool(_EXPLICIT_SEARCH_PATTERNS.search(query))


# ── Sync agentic chat ──────────────────────────────────────────────────────

def run_agentic_chat(
    conversation_id: str,
    user_input: str,
    user_id: Optional[str] = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> str:
    """Run the full agentic tool-calling loop and return the final text response."""
    history = _build_history(conversation_id, query=user_input, user_id=user_id)
    system_msgs: list = [SystemMessage(content=_SYSTEM_PROMPT)]
    if _detect_explicit_search_intent(user_input):
        log.info("Explicit search intent detected — injecting force-search override.")
        system_msgs.append(SystemMessage(content=_FORCE_SEARCH_OVERRIDE))
    messages: list = system_msgs + history + [HumanMessage(content=user_input)]

    for attempt in range(2):
        try:
            llm_with_tools = _raw_llm(temperature=0.5).bind_tools(AGENT_TOOLS)

            for iteration in range(max_iterations):
                response: AIMessage = llm_with_tools.invoke(messages)
                messages.append(response)

                tool_calls = getattr(response, "tool_calls", None) or []
                if not tool_calls:
                    return response.content or ""

                for tc in tool_calls:
                    result = _dispatch_tool(tc["name"], tc["args"])
                    log.info(
                        "Agent[iter=%d] tool=%s args=%s → %d chars",
                        iteration, tc["name"], tc["args"], len(result),
                    )
                    messages.append(
                        ToolMessage(
                            content=result,
                            tool_call_id=tc["id"],
                            name=tc["name"],
                        )
                    )

            # Max iterations reached: get a final answer without tools
            final = _raw_llm(temperature=0.5).invoke(messages)
            return final.content if hasattr(final, "content") else str(final)

        except Exception as exc:
            if attempt == 0 and is_no_model_error(exc):
                log.warning("No model loaded; auto-loading before retry…")
                ensure_model_loaded()
                continue
            raise


# ── Streaming agentic chat ─────────────────────────────────────────────────

def run_agentic_chat_stream(
    conversation_id: str,
    user_input: str,
    stop_event=None,
    user_id: Optional[str] = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> Generator:
    """Agentic tool-calling loop with a streaming final answer.

    Yields 3-tuples:
      ("thinking", "<label>",  [])       — tool call in progress
      ("token",    "<text>",   sources)  — streamed answer token
      (other events are handled by the router, not yielded here)

    The caller (router) is responsible for saving history and sending SSE.
    """
    history = _build_history(conversation_id, query=user_input, user_id=user_id)
    system_msgs: list = [SystemMessage(content=_SYSTEM_PROMPT)]
    if _detect_explicit_search_intent(user_input):
        log.info("Explicit search intent detected — injecting force-search override.")
        system_msgs.append(SystemMessage(content=_FORCE_SEARCH_OVERRIDE))
    messages: list = system_msgs + history + [HumanMessage(content=user_input)]
    all_sources: list[dict] = []

    for attempt in range(2):
        try:
            llm_with_tools = _raw_llm(temperature=0.5, streaming=False).bind_tools(AGENT_TOOLS)

            # ── Phase 1: Tool-calling loop (non-streaming) ─────────────────
            for iteration in range(max_iterations):
                if stop_event and stop_event.is_set():
                    return

                response: AIMessage = llm_with_tools.invoke(messages)
                tool_calls = getattr(response, "tool_calls", None) or []

                if not tool_calls:
                    # LLM is ready to answer — break so Phase 2 streams it properly
                    break

                # Only append to messages when there are actual tool calls
                messages.append(response)

                # Execute each requested tool call
                for tc in tool_calls:
                    if stop_event and stop_event.is_set():
                        return

                    # Build a human-readable label for the UI
                    args = tc.get("args", {})
                    args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
                    yield ("thinking", f"{tc['name']}({args_str})", [])

                    # For search_knowledge_base: collect real doc_id + filename directly
                    # from raw results BEFORE formatting, so sources are accurate.
                    if tc["name"] == "search_knowledge_base":
                        raw_results = search_knowledge(
                            args.get("query", ""),
                            limit=min(max(1, int(args.get("limit", 5))), 10),
                        )
                        seen_fnames = {s["filename"] for s in all_sources}
                        for r in raw_results:
                            fname = r.get("filename", "")
                            doc_id = r.get("doc_id", "")
                            if fname and fname not in seen_fnames:
                                all_sources.append({"filename": fname, "doc_id": doc_id})
                                seen_fnames.add(fname)
                        result = _format_search_results(raw_results) if raw_results else f"No relevant content found for query: '{args.get('query', '')}'" 
                    else:
                        result = _dispatch_tool(tc["name"], args)

                    log.info(
                        "Agent[iter=%d] tool=%s → %d chars",
                        iteration, tc["name"], len(result),
                    )

                    messages.append(
                        ToolMessage(
                            content=result,
                            tool_call_id=tc["id"],
                            name=tc["name"],
                        )
                    )

            # ── Phase 2: Always stream the final answer ────────────────────
            # messages = [system, history..., human] + optional [AIMessage(tools), ToolMessages...]
            # The streaming LLM generates a fresh, properly streamed response from this context.
            if stop_event and stop_event.is_set():
                return

            stream_llm = _raw_llm(temperature=0.5, streaming=True)
            for chunk in stream_llm.stream(messages):
                if stop_event and stop_event.is_set():
                    return
                token = chunk.content if hasattr(chunk, "content") else ""
                if token:
                    yield ("token", token, all_sources)
            return

        except Exception as exc:
            if attempt == 0 and is_no_model_error(exc):
                log.warning("No model loaded; auto-loading before retry…")
                ensure_model_loaded()
                continue
            raise
