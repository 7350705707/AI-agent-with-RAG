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

# Patterns that signal the user wants more / deeper details — likely about
# content that was already retrieved from the knowledge base in a prior turn.
# When matched we inject the force-search override so the LLM re-queries the DB.
_FOLLOWUP_DETAIL_PATTERNS = re.compile(
    r"\b("
    r"(more|further|additional|extra|deeper|detailed?)\s+(details?|information|info|explanation|context|data|content)"
    r"|tell me more"
    r"|explain (more|further|in (more |greater )?detail|it|this|that|them)"
    r"|give (me )?(more|details?|more details?|more information|more info)"
    r"|what else (does|do|is|are|can)"
    r"|any (other|more|additional) (information|info|details?|facts?|points?)"
    r"|can you (elaborate|expand|explain more|go deeper|give more)"
    r"|more (about|on|regarding) (this|that|it|them)"
    r"|elaborate (on|about)"
    r"|expand (on|about)"
    r"|specific(ally)? (about|on|regarding)"
    r"|in (more |greater )?(depth|detail)"
    r")",
    re.IGNORECASE,
)

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
)
from app.utils.user_memory import format_user_facts

log = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 3
MAX_SEARCH_CHARS = 3000
_MAX_HIST_CHARS = 800

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
                "search_knowledge_base already calls this automatically, so you "
                "only need to call it explicitly when you want to inspect the "
                "expanded terms yourself before deciding how to search."
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
    {
        "type": "function",
        "function": {
            "name": "search_conversation_history",
            "description": (
                "Search the user's past conversation history for relevant exchanges. "
                "Call this when the user refers to a previous discussion: "
                "'last time', 'before', 'remind me', 'what did I learn about X', "
                "'previously', 'we discussed', 'you explained', 'we covered'. "
                "Returns matching past Q&A pairs so you can recall and build on them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic or keywords from the past conversation to search for (3-8 words).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save an important fact about the user for permanent recall in future conversations. "
                "Call this when the user explicitly shares: their name, job, employer, location, age, "
                "a preference (favourite language, tool, framework), a goal they are working toward, "
                "or a project they mention wanting help with. "
                "Do NOT call this for general knowledge, trivia, or temporary conversational context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Short snake_case label, e.g. user_name, job_role, employer, current_project, favorite_language, learning_goal.",
                    },
                    "value": {
                        "type": "string",
                        "description": "The concise fact to remember (max 120 chars).",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["personal", "preference", "goal", "note", "task"],
                        "description": "Category for the fact.",
                    },
                },
                "required": ["key", "value", "category"],
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
    """Execute a hybrid knowledge-base search and return formatted results.

    Automatically expands the query with synonyms/related terms before searching
    so that small models (which rarely chain expand_search_keywords → search)
    still benefit from broader retrieval on every call.
    """
    limit = min(max(1, int(limit)), 10)
    if get_knowledge_chunk_count() == 0:
        return "No documents have been uploaded to the knowledge base yet."

    # --- automatic server-side query expansion ---
    expanded_terms = _tool_expand_search_keywords(query)
    # expanded_terms may be the original query (on failure) or a comma/newline
    # separated list of related keywords returned by the LLM.
    # Build a combined search query: original + expanded keywords.
    if expanded_terms and expanded_terms.strip() != query.strip():
        combined_query = f"{query} {expanded_terms}"
        log.debug("Auto-expanded query: %r → %r", query, combined_query)
    else:
        combined_query = query

    # Search with the combined (expanded) query first for broader recall.
    results = search_knowledge(combined_query, limit=limit)

    # If the expanded query found nothing, fall back to the original bare query.
    if not results and combined_query != query:
        log.debug("Expanded search found nothing; retrying with original query.")
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


def _tool_search_conversation_history(
    query: str,
    user_id: str | None,
    conversation_id: str,
) -> str:
    """Search past conversation history for relevant exchanges on a topic.

    Dispatched inline (not via _dispatch_tool) because it requires runtime
    context values user_id and conversation_id that the LLM cannot supply.
    """
    if not query.strip():
        return "No query provided for history search."

    results = (
        search_history_for_user(user_id, query, top_k=3)
        if user_id
        else search_history(conversation_id, query, top_k=3)
    )

    if not results:
        return f"No past conversations found about '{query}'."

    parts: list[str] = []
    for i, ex in enumerate(results, 1):
        u = ex["user"][:400]
        a = ex["assistant"][:600]
        parts.append(
            f"[Past exchange {i}]\nUser asked: {u}\nAssistant answered: {a}"
        )
    return "\n\n---\n\n".join(parts)


def _tool_save_memory(key: str, value: str, category: str, user_id: str | None) -> str:
    """Persist a user fact via the user_memory module and return a confirmation string."""
    if not user_id:
        return "Memory not saved: no authenticated user in this session."
    try:
        from app.utils.user_memory import save_memory_fact
        save_memory_fact(user_id, key, value, category, source="ai_tool")
        return f"Memory saved: {key} = '{value}' (category: {category})"
    except Exception as exc:
        log.warning("save_memory tool failed: %s", exc)
        return f"Failed to save memory: {exc}"


def _dispatch_tool(name: str, args: dict) -> str:
    """Route a tool call to its implementation and return a string result.

    Note: search_conversation_history and save_memory require runtime context
    (user_id, conversation_id) and are dispatched inline in the run_ functions.
    """
    if name == "search_knowledge_base":
        return _tool_search_knowledge_base(**args)
    if name == "expand_search_keywords":
        return _tool_expand_search_keywords(**args)
    return f"Unknown tool: '{name}'"


# ── Conversation history helpers ─────────────────────────────────────────

def _build_history(conversation_id: str) -> list:
    """Layer 1 of the hybrid history architecture.

    Injects the last 4 turns so follow-up questions and short-range recall
    ('explain more', 'what did I just ask?') always have adequate context.
    Fast: reads a single markdown file, no extra LLM call required.

    Layer 2 — cross-session relevance recall — is handled by the
    search_conversation_history tool, which the LLM calls autonomously
    when the user explicitly references past discussions.
    """
    exchanges = get_recent_exchanges(conversation_id, n=4)
    messages: list = []
    for ex in exchanges:
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
    "- If the question is about general knowledge you are already confident about, "
    "answer DIRECTLY from your own knowledge WITHOUT calling any tool.\n"
    "- If the user refers to a past discussion ('last time', 'before', 'remind me', "
    "'what did I learn about X', 'previously', 'you explained', 'we covered'), "
    "call search_conversation_history FIRST to retrieve relevant past exchanges.\n"
    "- If the question is about specific uploaded documents, technical details you are "
    "uncertain about, or information that is likely in the knowledge base, "
    "call search_knowledge_base FIRST, then answer.\n"
    "- FOLLOW-UP DETAIL RULE: If the user asks for 'more details', 'explain further', "
    "'give me more information', 'elaborate', 'what else', or any follow-up requesting "
    "deeper or additional specifics about a topic — look at the conversation history to "
    "identify the original topic, then call search_knowledge_base with a FOCUSED, SPECIFIC "
    "query on that topic. Do NOT rely solely on the previous answer already in history; "
    "the documents may contain additional relevant content not yet shown.\n"
    "- search_knowledge_base automatically expands your query with related terms before "
    "searching, so a single focused call is usually sufficient. Only call "
    "expand_search_keywords explicitly if you want to review the expanded terms first.\n"
    "- If search_knowledge_base still returns no useful results after automatic expansion, "
    "try one more search with a rephrased query before concluding the documents "
    "don't cover the topic.\n"
    "- Never call tools for greetings, simple math, or questions clearly about the "
    "ongoing conversation (unless they ask for more detail about a document topic).\n\n"
    "MANDATORY TOPIC VERIFICATION (critical — follow without exception):\n"
    "When search_knowledge_base returns results, you MUST verify that each result chunk "
    "is genuinely about the EXACT topic, operation, event, or entity the user asked about. "
    "If the chunks discuss a DIFFERENT operation, event, law, or subject than what was asked "
    "(e.g. 'Operation Sindoor' chunks returned for a 'Kargil War' query, or 'Assam Rifles Act' "
    "chunks returned for a 'BSF Act' query), those chunks are NOT relevant and must NOT be used "
    "to answer the question. In that case, tell the user: "
    "'The uploaded documents do not contain information about [user's exact topic].' "
    "then answer from your own general knowledge.\n\n"
    "TEMPORAL / RECENCY RULE: When the user asks for the 'latest', 'most recent', 'current', "
    "'newest', or 'last' occurrence of something, scan ALL retrieved chunks for explicit or implied "
    "dates (years, months, named events with known dates). Identify the chunk with the MOST RECENT "
    "date and use THAT as your primary answer. Do NOT default to whichever chunk appears first or "
    "uses the word 'latest' in its own text — that word in a document refers to that document's "
    "own context, not to the current date. "
    "CRITICAL: The most recent event found in the retrieved documents IS the correct answer. "
    "Do NOT say 'the documents do not contain this information' just because you believe something "
    "newer might exist outside the documents. If a document mentions an attack from April 2025 and "
    "another from 2008, the April 2025 event IS the latest in the documents — present it as such. "
    "Never use your training cut-off date as a reason to dismiss or override document content.\n\n"
    "CITATION RULES:\n"
    "- Cite [filename] ONLY for facts retrieved from that document and confirmed to be about the user's topic.\n"
    "- Never fabricate citations. Label your own knowledge as 'From general knowledge:' "
    "with no citation.\n\n"
    "PERSONAL INFO: When the user asks about their own name, job, location, or other "
    "personal details, check the KNOWN USER FACTS injected below (if any) BEFORE "
    "searching history or documents.\n\n"
    "MEMORY: If the user shares personal info (name, job, preferences, current project, "
    "goals, or anything they want the assistant to remember), call save_memory ONCE with "
    "the relevant fact. Do NOT call save_memory for general knowledge.\n\n"
    "CONVERSATION MEMORY: Answer questions about previous messages from history provided.\n"
    "For general knowledge, use an Indian perspective where applicable "
    "(geography, laws, currency ₹, current events)."
)


def _build_system_messages(user_facts: str = "") -> list:
    """Build the list of system messages, optionally prepending known user facts."""
    msgs: list = [SystemMessage(content=_SYSTEM_PROMPT)]
    if user_facts:
        msgs.append(SystemMessage(content=user_facts))
    return msgs

# Injected as an extra SystemMessage when the user explicitly asks to search documents
# or requests more details about a previously discussed topic.
_FORCE_SEARCH_OVERRIDE = (
    "OVERRIDE: The user has explicitly asked you to search the knowledge base / database, "
    "OR is requesting more details about a topic that may have prior content in the documents. "
    "You MUST call search_knowledge_base at least once before answering. "
    "If this is a follow-up for more details, look at the conversation history to identify "
    "the original topic and search with a SPECIFIC, FOCUSED query on that topic — "
    "do NOT search for 'more details' literally; search for the actual subject matter."
)


def _detect_explicit_search_intent(query: str) -> bool:
    """Return True when the user explicitly asks to search documents/database."""
    return bool(_EXPLICIT_SEARCH_PATTERNS.search(query))


def _is_followup_detail_request(query: str) -> bool:
    """Return True when the user is asking for more detail/elaboration.

    Unlike _detect_explicit_search_intent, this does NOT hard-force a KB search.
    Instead it triggers a soft hint so the LLM can decide whether its own
    knowledge is sufficient before calling a tool.
    """
    return bool(_FOLLOWUP_DETAIL_PATTERNS.search(query))


# ── KB-grounded conversation detection ────────────────────────────────────

# Stop-words used to check whether a query has meaningful topic content
_TOPIC_STOP = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "could",
    "should", "may", "might", "shall", "can", "i", "me", "my", "we", "our",
    "you", "your", "it", "its", "this", "that", "these", "those",
    "what", "how", "why", "where", "when", "who", "which",
    "and", "or", "but", "so", "yet", "for", "nor", "with", "in", "on",
    "at", "to", "of", "about", "from", "by", "into", "than", "then",
    "please", "tell", "give", "show", "explain", "describe", "list",
    "hi", "hello", "hey", "ok", "okay", "yes", "no", "sure", "thanks",
})


def _has_topic_words(text: str, min_words: int = 2) -> bool:
    """Return True when *text* contains ≥ min_words non-trivial content words.

    Filters out stop-words and very short tokens so greetings and meta-phrases
    ("ok", "yes please", "hi") do not trigger unnecessary KB searches.
    """
    words = {
        w for w in re.findall(r"\w+", text.lower())
        if w not in _TOPIC_STOP and len(w) > 2
    }
    return len(words) >= min_words


def _conversation_has_kb_sources(conversation_id: str, lookback: int = 4) -> bool:
    """Return True when any of the last *lookback* assistant messages in this
    conversation have associated knowledge-base sources stored in the DB.

    The sources field is populated by the router whenever the agentic loop
    or RAG pipeline retrieves content from uploaded documents.  This is more
    reliable than scanning assistant text for inline citations, since smaller
    local LLMs often paraphrase rather than copy the exact filename.

    When this returns True the conversation is KB-grounded, meaning follow-up
    questions about the same topic should re-search the knowledge base even if
    the LLM believes it already knows the answer from general knowledge.
    """
    try:
        from app.database import get_messages
        msgs = get_messages(conversation_id)
        recent_asst = [m for m in msgs if m["role"] == "assistant"][-lookback:]
        return any(m.get("sources") for m in recent_asst)
    except Exception as exc:
        log.debug("_conversation_has_kb_sources: %s", exc)
        return False


# Injected when the user asks for more detail but the conversation has NO prior
# KB sources — soft guidance only, LLM decides based on its own knowledge.
_DETAIL_SOFT_HINT = (
    "GUIDANCE: The user is asking for more details or elaboration. "
    "If you have comprehensive, complete knowledge to fully answer this question, "
    "answer directly from your own knowledge. "
    "However, if you are uncertain, lack specific details, or the topic might be "
    "covered in the uploaded documents, call search_knowledge_base FIRST with a "
    "focused query on the topic before answering."
)

# Injected when the conversation is KB-grounded and the user asks a substantive
# follow-up question that the LLM might otherwise answer from general knowledge.
_KB_GROUNDED_FOLLOWUP_OVERRIDE = (
    "CONTEXT RULE — DOCUMENT-GROUNDED CONVERSATION: The conversation history shows "
    "that previous answers in this chat were retrieved from uploaded knowledge base "
    "documents (sources are attached to prior messages). This is an ongoing discussion "
    "about content from those documents.\n"
    "MANDATORY: You MUST call search_knowledge_base FIRST with a focused, specific query "
    "about the topic being asked before answering. The uploaded documents likely contain "
    "more detailed or precise information than your general knowledge on this subject. "
    "Do NOT answer from general knowledge alone — always search the documents first in "
    "this conversation."
)


# ── Sync agentic chat ──────────────────────────────────────────────────────

def run_agentic_chat(
    conversation_id: str,
    user_input: str,
    user_id: Optional[str] = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> str:
    """Run the full agentic tool-calling loop and return the final text response."""
    history = _build_history(conversation_id)
    user_facts = format_user_facts(user_id)
    system_msgs = _build_system_messages(user_facts)
    if _detect_explicit_search_intent(user_input):
        log.info("Explicit search intent detected — injecting force-search override.")
        system_msgs.append(SystemMessage(content=_FORCE_SEARCH_OVERRIDE))
    elif _has_topic_words(user_input) and _conversation_has_kb_sources(conversation_id):
        log.info("KB-grounded conversation — injecting follow-up search override.")
        system_msgs.append(SystemMessage(content=_KB_GROUNDED_FOLLOWUP_OVERRIDE))
    elif _is_followup_detail_request(user_input):
        log.info("Follow-up detail request (no KB context) — injecting soft search hint.")
        system_msgs.append(SystemMessage(content=_DETAIL_SOFT_HINT))
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
                    args = tc.get("args") or {}
                    if tc["name"] == "search_conversation_history":
                        result = _tool_search_conversation_history(
                            args.get("query", ""), user_id, conversation_id
                        )
                    elif tc["name"] == "save_memory":
                        result = _tool_save_memory(
                            args.get("key", ""), args.get("value", ""),
                            args.get("category", "note"), user_id
                        )
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

            # Max iterations reached: get a final answer without tools
            final = _raw_llm(temperature=0.5).invoke(messages)
            return final.content if hasattr(final, "content") else str(final)

        except Exception as exc:
            if attempt == 0 and is_no_model_error(exc):
                log.warning("No model loaded; auto-loading before retry…")
                ensure_model_loaded()
                continue
            raise


# ── Temp file context loader ───────────────────────────────────────────────

def _load_temp_file_context(file_ids: list) -> str:
    """Load and extract text from user-uploaded files by their file_ids."""
    from app.config import UPLOAD_DIR
    from app.utils.document_loader import load_and_split

    parts: list[str] = []
    for fid in file_ids or []:
        fid_dir = UPLOAD_DIR / str(fid)
        if not fid_dir.is_dir():
            continue
        for fp in fid_dir.iterdir():
            if fp.is_file():
                try:
                    docs = load_and_split(fp)
                    text = "\n".join(d.page_content for d in docs)[:3000]
                    parts.append(f"--- File: {fp.name} ---\n{text}")
                except Exception as e:
                    log.warning("Could not read temp file %s: %s", fp, e)
    return "\n\n".join(parts)


# ── Streaming agentic chat ─────────────────────────────────────────────────

def run_agentic_chat_stream(
    conversation_id: str,
    user_input: str,
    stop_event=None,
    user_id: Optional[str] = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
    temp_file_ids: list | None = None,
) -> Generator:
    """Agentic tool-calling loop with a streaming final answer.

    Yields 3-tuples:
      ("thinking", "<label>",  [])       — tool call in progress
      ("token",    "<text>",   sources)  — streamed answer token
      (other events are handled by the router, not yielded here)

    The caller (router) is responsible for saving history and sending SSE.
    """
    history = _build_history(conversation_id)
    user_facts = format_user_facts(user_id)
    system_msgs = _build_system_messages(user_facts)
    if _detect_explicit_search_intent(user_input):
        log.info("Explicit search intent detected — injecting force-search override.")
        system_msgs.append(SystemMessage(content=_FORCE_SEARCH_OVERRIDE))
    elif _has_topic_words(user_input) and _conversation_has_kb_sources(conversation_id):
        log.info("KB-grounded conversation — injecting follow-up search override.")
        system_msgs.append(SystemMessage(content=_KB_GROUNDED_FOLLOWUP_OVERRIDE))
    elif _is_followup_detail_request(user_input):
        log.info("Follow-up detail request (no KB context) — injecting soft search hint.")
        system_msgs.append(SystemMessage(content=_DETAIL_SOFT_HINT))

    # Combine uploaded file content directly into the user message for analysis
    combined_input = user_input
    if temp_file_ids:
        extra_ctx = _load_temp_file_context(temp_file_ids)
        if extra_ctx:
            combined_input = (
                f"[Attached file content for analysis]\n\n{extra_ctx}\n\n"
                f"[User query]\n{user_input}"
            )
            log.info("Injected %d temp file(s) into user message.", len(temp_file_ids))

    messages: list = system_msgs + history + [HumanMessage(content=combined_input)]
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

                    args = tc.get("args") or {}

                    # Build a friendly label for the UI — do NOT expose query text
                    tool_labels = {
                        "search_knowledge_base": "Searching database…",
                        "expand_search_keywords": "Expanding search keywords…",
                        "search_conversation_history": "Searching conversation history…",
                        "save_memory": "Saving to memory…",
                    }
                    yield ("thinking", tool_labels.get(tc["name"], f"Running {tc['name']}…"), [])

                    # search_conversation_history needs runtime context — dispatch inline
                    if tc["name"] == "search_conversation_history":
                        result = _tool_search_conversation_history(
                            args.get("query", ""), user_id, conversation_id
                        )
                    elif tc["name"] == "save_memory":
                        result = _tool_save_memory(
                            args.get("key", ""), args.get("value", ""),
                            args.get("category", "note"), user_id
                        )
                    # For search_knowledge_base: collect real doc_id + filename directly
                    # from raw results BEFORE formatting, so sources are accurate.
                    elif tc["name"] == "search_knowledge_base":
                        raw_results = search_knowledge(
                            args.get("query", ""),
                            limit=min(max(1, int(args.get("limit", 5))), 10),
                        )
                        seen_fnames = {s["filename"] for s in all_sources}
                        for r in raw_results:
                            fname = r.get("filename", "")
                            doc_id = r.get("doc_id", "")
                            snippet = r.get("content", "")[:400]
                            if fname and fname not in seen_fnames:
                                all_sources.append({"filename": fname, "doc_id": doc_id, "snippet": snippet})
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
