"""Input sanitization — strips control characters and flags prompt injection.

Imported by chat/exam routers to clean user messages before they reach the LLM.
"""

import logging
import re
import unicodedata

log = logging.getLogger(__name__)

# ── Prompt-injection heuristics ───────────────────────────────────────────
# These patterns cover the most common jailbreak / system-override phrases.
# The goal is to log and neutralise (not silently allow) them.
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+(a\s+)?(?:DAN|unrestricted|jailbreak)",
    r"act\s+as\s+(?:a\s+)?(?:DAN|jailbreak|unrestricted|evil)",
    r"pretend\s+(you are|to be)\s+(?:a\s+)?(?:DAN|unrestricted)",
    r"system\s*prompt\s*:",
    r"<\|(?:im_start|im_end|system|user|assistant)\|>",
    r"\[INST\]",
    r"<<SYS>>",
    r"###\s*(?:System|Instruction)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Control characters that are never valid in a chat message
# (keeps \t \n \r which are legitimate whitespace)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_user_input(text: str, max_length: int = 10_000) -> str:
    """Sanitize a user-supplied chat message.

    Steps
    -----
    1. Unicode NFKC normalisation (resolves lookalike characters).
    2. Strip ASCII control characters.
    3. Truncate to *max_length* characters.
    4. Log a warning if injection patterns are detected (message still passes
       through so legitimate edge-case phrasing is not silently dropped).

    Returns the cleaned string.
    """
    # 1. Normalise
    text = unicodedata.normalize("NFKC", text)
    # 2. Strip control chars
    text = _CTRL_RE.sub("", text)
    # 3. Truncate
    text = text[:max_length]
    # 4. Detect injection attempts
    if _INJECTION_RE.search(text):
        log.warning("Possible prompt-injection pattern detected in user input (first 120 chars): %r", text[:120])
    return text.strip()
