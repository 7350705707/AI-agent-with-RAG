"""Exam Paper Generator agent — sends raw files to multimodal LLM (Gemma 4)."""

import base64
import logging
import mimetypes
from pathlib import Path

import httpx
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.llm import get_llm, get_llm_streaming, get_active_model
from app.utils.prompts import EXAM_PROMPT, EXAM_PROMPT_NO_DOCS
from app.database import get_messages
from app.config import UPLOAD_DIR, LM_STUDIO_BASE_URL
from app.utils.document_loader import load_and_split

log = logging.getLogger(__name__)

# Map extensions to MIME types the OpenAI vision/multimodal API accepts
_MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _collect_files_text(file_ids: list[str]) -> list[dict]:
    """Return a list of {'path': Path, 'text': str} for uploaded files, extracting text."""
    files = []
    for fid in (file_ids or []):
        fdir = UPLOAD_DIR / fid
        if not fdir.is_dir():
            continue
        for fp in fdir.iterdir():
            if not fp.is_file():
                continue
            try:
                # Try to extract text using document_loader
                chunks = load_and_split(fp)
                text = "\n".join([c.page_content for c in chunks])
                files.append({"path": fp, "text": text})
                log.info("Extracted text from %s (%d chars)", fp.name, len(text))
            except Exception as e:
                log.warning("Failed to extract text from %s: %s", fp.name, e)
    return files


def _build_history(conversation_id: str, limit: int = 2) -> list:
    rows = get_messages(conversation_id)
    history = []
    for r in rows:
        if r["role"] == "user":
            history.append(HumanMessage(content=r["content"]))
        else:
            history.append(AIMessage(content=r["content"]))
    # Only keep last N exchanges
    return history[-(limit * 2):] if history else []


def extract_topics_from_files(file_ids: list[str]) -> list[str]:
    """Use the LLM to extract main topics / chapters from uploaded documents.

    Returns a list of topic name strings (5-15 items) or an empty list on failure.
    """
    import json as _json
    import re as _re

    files = _collect_files_text(file_ids)
    if not files:
        return []

    _MAX_DOC_CHARS = 3000
    combined = ""
    for f in files:
        doc_text = f["text"][:_MAX_DOC_CHARS]
        if len(f["text"]) > _MAX_DOC_CHARS:
            doc_text += "\n[...document truncated...]"
        combined += f"--- Document: {f['path'].name} ---\n{doc_text}\n\n"

    base = LM_STUDIO_BASE_URL.rstrip("/")
    payload = {
        "model": get_active_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a document topic extractor. Analyze the document content provided "
                    "and identify the main topics, chapters, or subject areas it covers. "
                    "Return ONLY a valid JSON array of topic name strings — no explanation, "
                    "no markdown fences, just the raw JSON array. "
                    'Example: ["Introduction", "OSI Model", "TCP/IP Protocol", "Network Security"] '
                    "Return between 5 and 15 topics."
                ),
            },
            {"role": "user", "content": combined},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
        "stream": False,
    }

    try:
        resp = httpx.post(f"{base}/chat/completions", json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON array even if the model adds prose around it
        match = _re.search(r"\[.*?\]", content, _re.DOTALL)
        if match:
            raw = _json.loads(match.group())
            return [str(t).strip() for t in raw if str(t).strip()]
        return []
    except Exception as e:
        log.warning("Topic extraction failed: %s", e)
        return []


def run_exam_generator(
    conversation_id: str, user_instructions: str, file_ids: list[str],
    mcq_count: int = 10, tf_count: int = 10, fitb_count: int = 10,
) -> str:
    """Generate an exam paper by reading uploaded docs directly."""
    # Consume the streaming generator and return final result
    result = ""
    for _step, _label, content in run_exam_generator_steps(
        conversation_id, user_instructions, file_ids,
        mcq_count=mcq_count, tf_count=tf_count, fitb_count=fitb_count,
    ):
        result = content
    return result


def parse_exam_to_json(text: str) -> list[dict]:
    """Parse LLM exam output into a list of question dicts.

    Each dict has: number, type (mcq/true_false/fill_blank), text, options (MCQ only), answer.
    Returns empty list on parse failure.
    """
    import re
    questions = []
    current_section = None  # 'mcq' | 'true_false' | 'fill_blank' | 'answer_key'
    current_q: dict | None = None

    # Parse answer key first so we can attach answers to questions
    answers: dict[int, str] = {}
    answer_key_match = re.search(
        r"## Answer Key(.*?)(?:##|$)", text, re.DOTALL | re.IGNORECASE
    )
    if answer_key_match:
        ak_text = answer_key_match.group(1)
        # MCQ answers: "1. B | 2. C | ..."
        for m in re.finditer(r"(\d+)\.\s*([A-Da-d])\s*\|?", ak_text):
            answers[int(m.group(1))] = m.group(2).upper()
        # True/False answers: "11. True | 12. False | ..."
        for m in re.finditer(r"(\d+)\.\s*(True|False)\s*\|?", ak_text, re.IGNORECASE):
            answers[int(m.group(1))] = m.group(2).capitalize()
        # Fill in blanks answers: "21. word | 22. phrase | ..."
        for m in re.finditer(r"(\d+)\.\s*([^|\n]+?)(?:\s*\||\s*$)", ak_text):
            num = int(m.group(1))
            if num not in answers:  # don't overwrite MCQ/TF
                answers[num] = m.group(2).strip()

    def _save_current():
        if current_q and current_q.get("text"):
            qnum = current_q.get("number", 0)
            current_q["answer"] = answers.get(qnum, "")
            questions.append(current_q)

    for line in text.splitlines():
        stripped = line.strip()

        # Section headers
        if re.search(r"Section A|MCQ|Multiple.Choice", stripped, re.IGNORECASE):
            _save_current()
            current_q = None
            current_section = "mcq"
            continue
        if re.search(r"Section B|True.?/?False", stripped, re.IGNORECASE):
            _save_current()
            current_q = None
            current_section = "true_false"
            continue
        if re.search(r"Section C|Fill.?in.?the?.?Blank", stripped, re.IGNORECASE):
            _save_current()
            current_q = None
            current_section = "fill_blank"
            continue
        if re.search(r"Answer Key", stripped, re.IGNORECASE):
            _save_current()
            current_q = None
            current_section = "answer_key"
            continue

        if current_section == "answer_key" or current_section is None:
            continue

        # Question line: "Q1." or "1." or "Q 1."
        q_match = re.match(r"^Q?\s*(\d+)[.)]\s+(.+)", stripped)
        if q_match:
            _save_current()
            current_q = {
                "number": int(q_match.group(1)),
                "type": current_section,
                "text": q_match.group(2).strip(),
                "options": [],
                "answer": "",
            }
            continue

        # MCQ option lines: "A) text" or "A. text" or "(A) text"
        if current_section == "mcq" and current_q:
            opt_match = re.match(r"^\(?([A-Da-d])[.)]\s+(.+)", stripped)
            if opt_match:
                current_q["options"].append(
                    f"{opt_match.group(1).upper()}) {opt_match.group(2).strip()}"
                )
                continue

        # Continuation lines for current question
        if current_q and stripped and not stripped.startswith("#"):
            current_q["text"] += " " + stripped

    _save_current()

    # Post-process fill_blank questions: ensure every one contains the blank placeholder
    for q in questions:
        if q.get("type") == "fill_blank" and "______" not in q.get("text", ""):
            text = q["text"].rstrip(".").rstrip()
            q["text"] = text + " ______."
            log.debug("Added blank placeholder to fill_blank Q%s", q.get("number"))

    return questions


def run_exam_generator_steps(
    conversation_id: str, user_instructions: str, file_ids: list[str],
    mcq_count: int = 10, tf_count: int = 10, fitb_count: int = 10,
    stop_event=None,
):
    """Yield (step, label, accumulated_content) tuples as each token is generated."""
    log.info("file_ids received: %s", file_ids)

    files = _collect_files_text(file_ids)
    has_docs = bool(files)
    log.info("has_docs=%s, %d files collected", has_docs, len(files))

    history = _build_history(conversation_id, limit=2)

    if has_docs:
        tf_start = mcq_count + 1
        tf_end = mcq_count + tf_count
        fitb_start = tf_end + 1
        fitb_end = tf_end + fitb_count

        # Build the system prompt from template
        system_text = EXAM_PROMPT.messages[0].prompt.format(
            mcq_count=mcq_count,
            tf_start=tf_start,
            tf_end=tf_end,
            fitb_start=fitb_start,
            fitb_end=fitb_end,
        )

        # FIXED: Serialize user input and file content into a single string
        # Cap each document at 2000 chars to stay within the model's context window
        _MAX_DOC_CHARS = 2000
        combined_user_content = f"Instructions: {user_instructions or 'Generate the exam paper from the attached content.'}\n\n"
        for f in files:
            doc_text = f['text'][:_MAX_DOC_CHARS]
            if len(f['text']) > _MAX_DOC_CHARS:
                doc_text += "\n[...document truncated to fit context window...]"
            combined_user_content += f"--- Document: {f['path'].name} ---\n{doc_text}\n\n"

        yield ("generating", "Generating exam paper…", "")
        base = LM_STUDIO_BASE_URL.rstrip("/")
        payload = {
            "model": get_active_model(),
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": combined_user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 3000,
            "stream": True,
        }
        try:
            accumulated = ""
            with httpx.stream(
                "POST",
                f"{base}/chat/completions",
                json=payload,
                timeout=600,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if stop_event and stop_event.is_set():
                        resp.close()
                        return
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            accumulated += token
                            yield ("streaming", "Generating…", accumulated)
                    except Exception:
                        continue
        except Exception as e:
            log.exception("LLM call failed: %s", e)
            yield ("done", "Error", f"Failed to generate exam: {e}")
            return

        log.info("Exam paper generated (%d chars)", len(accumulated))
        yield ("done", "Exam paper complete ✓", accumulated.strip())
    else:
        yield ("generating", "Generating response…", "")
        llm = get_llm_streaming(temperature=0.2, num_predict=3000)
        chain = EXAM_PROMPT_NO_DOCS | llm
        accumulated = ""
        for token in chain.stream({
            "history": history,
            "input": user_instructions,
        }):
            if stop_event and stop_event.is_set():
                return
            accumulated += token
            yield ("streaming", "Generating…", accumulated)
        yield ("done", "Done", accumulated)
