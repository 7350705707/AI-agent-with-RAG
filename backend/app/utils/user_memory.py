"""Per-user persistent memory — stores personal facts and important context.

Two extraction paths:
  1. Regex (fast, zero-latency) — runs synchronously on every user message
     to catch explicit personal statements ("my name is …", "I work at …").
  2. AI (LLM-based) — runs in a background thread after each response to catch
     nuanced facts the regex misses (preferences, goals, projects, etc.).

Storage backend: SQLite via ``database.upsert_user_memory`` / ``get_user_memories``.
Legacy JSON files (``history/user_facts/``) are read once as a migration fallback.
"""

import json
import re
import logging
from pathlib import Path

from app.config import BASE_DIR

log = logging.getLogger(__name__)

# Keep the legacy directory for backward-compat reads only (no new writes)
_FACTS_DIR = BASE_DIR / "history" / "user_facts"
_FACTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Regex extraction patterns ──────────────────────────────────────────────
_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (pattern, key, category)
    (re.compile(r"\bmy name is ([A-Za-z][A-Za-z .'\-]{1,39})", re.I),            "user_name",   "personal"),
    (re.compile(r"\bcall me ([A-Za-z][A-Za-z .'\-]{1,29})(?:\b|$)", re.I),       "user_name",   "personal"),
    (re.compile(r"\beveryone calls me ([A-Za-z][A-Za-z .'\-]{1,29})\b", re.I),   "user_name",   "personal"),
    (re.compile(r"\bmy (?:job|profession|occupation|role|designation|position) is ([A-Za-z][A-Za-z ]{2,49})", re.I), "job_role", "personal"),
    (re.compile(r"\bi work as (?:a |an )?([A-Za-z][A-Za-z ]{2,49})", re.I),      "job_role",    "personal"),
    (re.compile(r"\bi(?:'m| am) (?:a |an )?([A-Za-z][A-Za-z ]{2,39}) (?:by profession|by trade|professionally)\b", re.I), "job_role", "personal"),
    (re.compile(r"\bi work (?:at|for) ([A-Za-z0-9][A-Za-z0-9 &.,'\-]{1,59})(?:\.|,|$|\s+and\b)", re.I), "employer", "personal"),
    (re.compile(r"\bmy (?:company|organization|employer|firm|office) is ([A-Za-z0-9][A-Za-z0-9 &.,'\-]{1,59})", re.I), "employer", "personal"),
    (re.compile(r"\bi(?:'m| am) from ([A-Za-z][A-Za-z ,]{2,49})(?:\.|,|$|\s+and\b)", re.I),  "location", "personal"),
    (re.compile(r"\bi live in ([A-Za-z][A-Za-z ,]{2,49})(?:\.|,|$|\s+and\b)", re.I),         "location", "personal"),
    (re.compile(r"\bmy (?:hometown|city|state|country) is ([A-Za-z][A-Za-z ,]{2,49})", re.I),"location", "personal"),
    (re.compile(r"\bi(?:'m| am) (\d{1,3}) years old\b", re.I),                   "age",         "personal"),
    (re.compile(r"\bmy age is (\d{1,3})\b", re.I),                               "age",         "personal"),
    (re.compile(r"\bi (?:prefer|like|love|use|enjoy) ([A-Za-z][A-Za-z0-9 +#.\-]{1,39}) (?:over|more than|instead of|rather than)", re.I), "preferred_tool", "preference"),
    (re.compile(r"\bmy (?:favourite|favorite|preferred) (?:language|tool|framework|stack) is ([A-Za-z][A-Za-z0-9 +#.\-]{1,39})", re.I), "preferred_tool", "preference"),
]

_FALSE_POSITIVES = frozenset({
    "confused", "sorry", "not sure", "okay", "fine", "good", "here", "happy",
    "glad", "ready", "able", "using", "trying", "looking", "new", "interested",
    "busy", "tired", "excited", "back", "not able", "not familiar",
})
_MIN_LEN = 2


# ── Regex extractor ────────────────────────────────────────────────────────

def _extract_facts(text: str) -> list[tuple[str, str, str]]:
    """Return list of (key, value, category) found via regex in *text*."""
    found: list[tuple[str, str, str]] = []
    seen_keys: set[str] = set()
    for pattern, key, category in _PATTERNS:
        if key in seen_keys:
            continue
        m = pattern.search(text)
        if not m:
            continue
        value = m.group(1).strip().rstrip(".,!? ")
        value = re.split(r"[.!?]", value)[0].strip()
        if len(value) < _MIN_LEN or value.lower() in _FALSE_POSITIVES:
            continue
        found.append((key, value, category))
        seen_keys.add(key)
    return found


# ── Core save helper ───────────────────────────────────────────────────────

def save_memory_fact(
    user_id: str,
    key: str,
    value: str,
    category: str = "note",
    source: str = "ai",
) -> None:
    """Persist a single memory fact to SQLite. Safe to call from any thread."""
    if not user_id or not key or not value:
        return
    key = key.strip()[:80]
    value = value.strip()[:500]
    category = category.strip().lower()
    if category not in ("personal", "preference", "goal", "note", "task"):
        category = "note"
    try:
        from app.database import upsert_user_memory
        upsert_user_memory(user_id, key, value, category, source)
        log.info("user_memory: saved key=%r cat=%s src=%s user=%s", key, category, source, user_id)
    except Exception as exc:
        log.warning("user_memory: save failed key=%r: %s", key, exc)


# ── Legacy JSON reader (migration fallback) ────────────────────────────────

def _load_legacy_json(user_id: str) -> dict:
    """Read the old JSON facts file if it exists (read-only, for migration)."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id)
    path = _FACTS_DIR / f"{safe}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Public API ─────────────────────────────────────────────────────────────

def update_user_facts(user_id: str, user_msg: str) -> None:
    """Fast regex pass: extract personal facts from *user_msg* and persist.

    Called synchronously on every incoming user message (zero LLM cost).
    The slower AI extraction runs in background via ``ai_extract_and_save``.
    """
    if not user_id:
        return
    facts = _extract_facts(user_msg)
    for key, value, category in facts:
        save_memory_fact(user_id, key, value, category, source="regex")


_LABEL_MAP = {
    "user_name":      "Name",
    "name":           "Name",          # legacy key compat
    "job_role":       "Job/Role",
    "job":            "Job/Role",      # legacy
    "employer":       "Works at",
    "workplace":      "Works at",      # legacy
    "location":       "Location",
    "age":            "Age",
    "preferred_tool": "Preferred tool/language",
}


def format_user_facts(user_id: str | None) -> str:
    """Return a formatted string of known user facts for system prompt injection.

    Reads from SQLite (primary) with a one-time migration from legacy JSON.
    Returns ``""`` when *user_id* is None or no facts are stored.
    """
    if not user_id:
        return ""

    try:
        from app.database import get_user_memories, upsert_user_memory
        memories = get_user_memories(user_id)

        # One-time migration: import JSON facts into SQLite if SQLite is empty
        if not memories:
            legacy = _load_legacy_json(user_id)
            if legacy:
                _CAT = {"name": "personal", "job": "personal", "workplace": "personal",
                        "location": "personal", "age": "personal"}
                for k, v in legacy.items():
                    cat = _CAT.get(k, "note")
                    upsert_user_memory(user_id, k, str(v), cat, "legacy")
                memories = get_user_memories(user_id)
    except Exception:
        memories = []

    if not memories:
        return ""

    lines = []
    for mem in memories:
        label = _LABEL_MAP.get(mem["key"], mem["key"].replace("_", " ").title())
        lines.append(f"- {label}: {mem['value']}")

    return (
        "KNOWN USER FACTS (always use these when the user asks about themselves):\n"
        + "\n".join(lines)
        + "\n\n"
    )


def ai_extract_and_save(user_id: str, user_msg: str, assistant_msg: str) -> None:
    """LLM-based memory extraction — call from a background thread.

    Sends the exchange to the LLM with a tightly scoped prompt that asks it to
    output ``SAVE|key|value|category`` lines for anything worth remembering, or
    ``NONE`` if nothing is notable.  Parses the output and persists each fact.
    """
    if not user_id:
        return
    try:
        from app.llm import get_llm
        from app.utils.prompts import MEMORY_EXTRACTION_PROMPT

        llm = get_llm(temperature=0.0)
        result = (MEMORY_EXTRACTION_PROMPT | llm).invoke({
            "user_msg": user_msg[:600],
            "assistant_msg": assistant_msg[:400],
        })
        text = result.content.strip() if hasattr(result, "content") else str(result).strip()

        if not text or text.upper().startswith("NONE"):
            return

        saved = 0
        for line in text.splitlines():
            line = line.strip()
            if not line.upper().startswith("SAVE"):
                continue
            # Accept "SAVE|key|value|category" or "SAVE: key|value|category"
            clean = re.sub(r"^SAVE[:\|]\s*", "", line, flags=re.I)
            parts = [p.strip() for p in clean.split("|")]
            if len(parts) < 3:
                continue
            key, value, category = parts[0], parts[1], parts[2]
            if key and value:
                save_memory_fact(user_id, key, value, category, source="ai")
                saved += 1

        if saved:
            log.info("user_memory: ai_extract saved %d fact(s) for user=%s", saved, user_id)

    except Exception as exc:
        log.debug("ai_extract_and_save failed (non-fatal): %s", exc)
