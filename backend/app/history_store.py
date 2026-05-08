"""Backward-compatibility shim — import from app.utils.history_store instead."""
from app.utils.history_store import *  # noqa: F401,F403
from app.utils.history_store import (  # noqa: F401
    append_exchange, search_history, search_history_for_user,
    get_recent_exchanges, tokenize,
)
and returns the top-K most relevant exchanges so the LLM gets focused,
trimmed context instead of a raw sliding window.
"""

import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR
from app.database import get_conversation_ids_by_user

log = logging.getLogger(__name__)

HISTORY_DIR = BASE_DIR / "history"
HISTORY_DIR.mkdir(exist_ok=True)

# Maximum characters kept from each side of an exchange when injecting context
_MAX_SIDE_CHARS = 600

_STOP = frozenset({
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "and", "or",
    "for", "with", "what", "how", "why", "when", "where", "who", "do", "does",
    "did", "i", "you", "we", "they", "he", "she", "that", "this", "be", "was",
    "are", "were", "has", "have", "had", "will", "would", "can", "could",
    "should", "may", "might", "shall", "just", "also", "so", "but", "if",
    "then", "my", "your", "its", "our", "their",
})


# ── Path helpers ──────────────────────────────────────────────────────────

def _history_path(conversation_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9\-]", "_", conversation_id)
    return HISTORY_DIR / f"{safe}.md"


# ── Write ─────────────────────────────────────────────────────────────────

def append_exchange(conversation_id: str, user_msg: str, assistant_msg: str) -> None:
    """Append one Q&A pair to the conversation's markdown history file."""
    path = _history_path(conversation_id)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    needs_header = not path.exists() or path.stat().st_size == 0
    entry = (
        f"\n## [{ts}]\n"
        f"**User:** {user_msg.strip()}\n\n"
        f"**Assistant:** {assistant_msg.strip()}\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as f:
            if needs_header:
                f.write("# Conversation History\n")
            f.write(entry)
    except OSError as exc:
        log.warning("history_store: could not write %s: %s", path, exc)


# ── Parse ─────────────────────────────────────────────────────────────────

def _parse_exchanges(text: str) -> list[dict]:
    """Parse a markdown history file into a list of {user, assistant} dicts."""
    exchanges: list[dict] = []
    blocks = re.split(r"(?m)^## \[.*?\]", text)
    for block in blocks:
        u = re.search(r"\*\*User:\*\*\s*(.+?)(?=\n\n\*\*Assistant:\*\*)", block, re.DOTALL)
        a = re.search(r"\*\*Assistant:\*\*\s*(.+?)$", block, re.DOTALL)
        if u and a:
            exchanges.append({
                "user": u.group(1).strip()[:_MAX_SIDE_CHARS],
                "assistant": a.group(1).strip()[:_MAX_SIDE_CHARS],
            })
    return exchanges


# ── Relevance scoring ─────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if w not in _STOP and len(w) > 2}


def tokenize(text: str) -> set[str]:
    """Public wrapper around _tokens — returns filtered content words for a text string."""
    return _tokens(text)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Search ────────────────────────────────────────────────────────────────

def search_history(conversation_id: str, query: str, top_k: int = 3) -> list[dict]:
    """Return the top_k most relevant past Q&A exchanges for *query*.

    Falls back to the last ``top_k`` exchanges when no word overlap is found,
    so the LLM always has at least minimal conversational context.
    """
    path = _history_path(conversation_id)
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        exchanges = _parse_exchanges(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    if not exchanges:
        return []

    q_tok = _tokens(query)
    if not q_tok:
        return exchanges[-top_k:]

    scored = sorted(
        exchanges,
        key=lambda e: _jaccard(q_tok, _tokens(e["user"] + " " + e["assistant"])),
        reverse=True,
    )
    relevant = [
        e for e in scored[:top_k]
        if _jaccard(q_tok, _tokens(e["user"] + " " + e["assistant"])) > 0.0
    ]
    return relevant if relevant else exchanges[-top_k:]


def get_recent_exchanges(conversation_id: str, n: int = 2) -> list[dict]:
    """Return the last *n* exchanges from *conversation_id* in chronological order.

    Used to guarantee that immediate follow-up questions ("give me in details",
    "explain more") always see the most recent turn regardless of Jaccard score.
    """
    path = _history_path(conversation_id)
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        exchanges = _parse_exchanges(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    return exchanges[-n:] if exchanges else []


def search_history_for_user(user_id: str, query: str, top_k: int = 3) -> list[dict]:
    """Search history across ALL conversations belonging to *user_id*.

    Reads every markdown history file for the user's conversations, scores all
    exchanges with Jaccard similarity against *query*, and returns the top_k
    most relevant ones. Falls back to the most recent *top_k* exchanges when
    no word overlap is found.
    """
    conv_ids = get_conversation_ids_by_user(user_id)
    if not conv_ids:
        return []

    all_exchanges: list[dict] = []
    for cid in conv_ids:
        path = _history_path(cid)
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            all_exchanges.extend(_parse_exchanges(path.read_text(encoding="utf-8")))
        except OSError:
            continue

    if not all_exchanges:
        return []

    q_tok = _tokens(query)
    if not q_tok:
        return all_exchanges[-top_k:]

    scored = sorted(
        all_exchanges,
        key=lambda e: _jaccard(q_tok, _tokens(e["user"] + " " + e["assistant"])),
        reverse=True,
    )
    relevant = [
        e for e in scored[:top_k]
        if _jaccard(q_tok, _tokens(e["user"] + " " + e["assistant"])) > 0.0
    ]
    return relevant if relevant else all_exchanges[-top_k:]
