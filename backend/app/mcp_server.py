"""MCP (Model Context Protocol) server — exposes Servam AI tools for LM Studio and other MCP clients."""

import logging
from mcp.server.fastmcp import FastMCP

from app.database import (
    list_knowledge_documents,
    get_messages,
    list_conversations,
)
from app.chroma_store import search_knowledge, get_knowledge_chunk_count
from app.llm import get_active_model, list_available_models, get_llm

log = logging.getLogger(__name__)

# ── Create MCP Server ──────────────────────────────────────────────────────
mcp = FastMCP(
    "Sarvam AI",
    instructions=(
        "Sarvam AI MCP Server — provides tools to search the library (knowledge base), "
        "list available documents, browse conversation history, and check model status. "
        "Use search_library to find relevant information from uploaded reference documents."
    ),
)


# ── Tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_query_for_rag(user_input: str) -> str:
    """Analyze a user message and extract a focused search query for RAG retrieval.

    Converts a conversational user message into 3-8 focused keywords or a short
    phrase that can be used to search the knowledge base efficiently.

    Args:
        user_input: The raw user message to analyze.

    Returns:
        A focused search query string (3-8 keywords). Falls back to the
        original input if the knowledge base is empty or the call fails.
    """
    if get_knowledge_chunk_count() == 0:
        return user_input  # No KB to search — skip analysis
    try:
        from app.utils.prompts import QUERY_ANALYSIS_PROMPT
        llm = get_llm(temperature=0.0, num_predict=40)
        result = (QUERY_ANALYSIS_PROMPT | llm).invoke({"input": user_input})
        query = result.strip().split("\n")[0].strip()
        log.debug("MCP analyze_query_for_rag: %r -> %r", user_input, query)
        return query if len(query) > 2 else user_input
    except Exception as exc:
        log.warning("analyze_query_for_rag failed (%s), using original input", exc)
        return user_input


@mcp.tool()
def expand_query_keywords(user_input: str) -> list:
    """Generate related search keywords for a user query to improve hybrid retrieval.

    This is the second MCP call in the dual-MCP RAG pipeline. After the primary
    search query is extracted by analyze_query_for_rag, this tool generates
    additional synonyms and related domain keywords. Those keywords are then
    used to boost BM25 keyword matching during hybrid retrieval so rare or
    domain-specific terms that may be paraphrased in the document still surface.

    Args:
        user_input: The raw user message or the refined search query.

    Returns:
        List of 5-10 related keywords/phrases. Falls back to empty list on failure.
    """
    if get_knowledge_chunk_count() == 0:
        return []
    try:
        from app.utils.prompts import KEYWORD_EXPANSION_PROMPT
        llm = get_llm(temperature=0.1, num_predict=60)
        result = (KEYWORD_EXPANSION_PROMPT | llm).invoke({"input": user_input})
        raw = result.strip()
        # Parse comma-separated or newline-separated keywords
        import re
        keywords = [kw.strip().strip('"').strip("'") for kw in re.split(r"[,\n]+", raw) if kw.strip()]
        keywords = [k for k in keywords if 2 < len(k) < 60][:10]
        log.debug("MCP expand_query_keywords: %r -> %r", user_input[:60], keywords)
        return keywords
    except Exception as exc:
        log.warning("expand_query_keywords failed (%s)", exc)
        return []


@mcp.tool()
def search_library(query: str, limit: int = 5) -> str:
    """Search the library (knowledge base) for relevant document chunks.

    Use this tool when you need to find information from uploaded reference
    documents. Returns the most relevant text passages ranked by relevance.

    Args:
        query: The search query — keywords or a natural language question.
        limit: Maximum number of results to return (default 5).
    """
    if get_knowledge_chunk_count() == 0:
        return "The library is empty. No documents have been uploaded yet."

    results = search_knowledge(query, limit=limit)
    if not results:
        return f"No results found for: {query}"

    parts = []
    for i, r in enumerate(results, 1):
        filename = r.get("filename", "unknown")
        content = r.get("content", "")
        parts.append(f"[{i}] Source: {filename}\n{content}")

    return "\n\n---\n\n".join(parts)


@mcp.tool()
def list_library_documents() -> str:
    """List all documents currently in the library (knowledge base).

    Returns document names, sizes, and chunk counts.
    """
    docs = list_knowledge_documents()
    if not docs:
        return "The library is empty."

    lines = []
    for d in docs:
        size_kb = d.get("file_size", 0) / 1024
        lines.append(
            f"- {d['filename']} ({size_kb:.1f} KB, {d.get('chunk_count', 0)} chunks, "
            f"uploaded by {d.get('uploaded_by', 'unknown')})"
        )
    return f"Library contains {len(docs)} document(s):\n" + "\n".join(lines)


@mcp.tool()
def get_conversation_messages(conversation_id: str, last_n: int = 20) -> str:
    """Get recent messages from a conversation.

    Args:
        conversation_id: The UUID of the conversation.
        last_n: Number of recent messages to return (default 20).
    """
    messages = get_messages(conversation_id)
    if not messages:
        return "No messages found for this conversation."

    recent = messages[-last_n:] if len(messages) > last_n else messages
    parts = []
    for m in recent:
        role = m.get("role", "unknown").upper()
        content = m.get("content", "")
        parts.append(f"[{role}]: {content}")

    return "\n\n".join(parts)


@mcp.tool()
def list_active_conversations(agent_type: str = "") -> str:
    """List conversations, optionally filtered by agent type.

    Args:
        agent_type: Filter by type — 'chat', 'exam', or empty string for all.
    """
    convs = list_conversations(agent_type or None)
    if not convs:
        return "No conversations found."

    lines = []
    for c in convs[:30]:  # cap at 30
        lines.append(f"- [{c.get('agent_type', '?')}] {c.get('title', 'Untitled')} (id: {c['id']})")
    return f"{len(convs)} conversation(s):\n" + "\n".join(lines)


@mcp.tool()
def get_model_status() -> str:
    """Check the current LLM model status.

    Returns the active model name and list of available models in LM Studio.
    """
    active = get_active_model()
    models = list_available_models()
    model_ids = [m.get("id", "?") for m in models]
    return (
        f"Active model: {active}\n"
        f"Available models ({len(model_ids)}): {', '.join(model_ids) or 'none detected'}"
    )


# ── Resources ──────────────────────────────────────────────────────────────

@mcp.resource("servam://library/stats")
def library_stats() -> str:
    """Current library statistics."""
    docs = list_knowledge_documents()
    chunks = get_knowledge_chunk_count()
    total_size = sum(d.get("file_size", 0) for d in docs) / (1024 * 1024)
    return (
        f"Documents: {len(docs)}\n"
        f"Total chunks: {chunks}\n"
        f"Total size: {total_size:.2f} MB"
    )
