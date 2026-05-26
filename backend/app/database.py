"""SQLite helper for persisting chat history and user accounts."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import SQLITE_DB


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SQLITE_DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            agent_type  TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT 'New Chat',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id              TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            username    TEXT NOT NULL UNIQUE,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user',
            agents      TEXT NOT NULL DEFAULT '["chat"]',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id          TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            file_size   INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            uploaded_by TEXT,
            created_at  TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # ── Schema migrations (add columns safely) ──────────────────────────────
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    try:
        conn.execute("ALTER TABLE knowledge_documents ADD COLUMN file_path TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Track uploaded files per conversation (for cleanup on delete)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversation_files (
                id          TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                file_id     TEXT NOT NULL,
                file_path   TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cf_conv ON conversation_files(conversation_id);
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add sources column to messages for RAG source persistence
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN sources TEXT DEFAULT '[]'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already exists

    # Add SHA-256 content hash for duplicate detection
    try:
        conn.execute("ALTER TABLE knowledge_documents ADD COLUMN file_hash TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already exists

    # Analytics events table
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id          TEXT PRIMARY KEY,
                user_id     TEXT,
                agent_type  TEXT NOT NULL DEFAULT 'chat',
                message_len INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ae_user ON analytics_events(user_id);
            CREATE INDEX IF NOT EXISTS idx_ae_day  ON analytics_events(created_at);
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Backfill file_hash for documents uploaded before hash tracking was added
    try:
        import hashlib as _hashlib
        rows_needing_hash = conn.execute(
            "SELECT id, file_path FROM knowledge_documents WHERE (file_hash IS NULL OR file_hash = '') AND file_path != ''"
        ).fetchall()
        for row in rows_needing_hash:
            doc_id, file_path = row["id"], row["file_path"]
            try:
                p = Path(file_path)
                if p.is_file():
                    h = _hashlib.sha256(p.read_bytes()).hexdigest()
                    conn.execute(
                        "UPDATE knowledge_documents SET file_hash=? WHERE id=?",
                        (h, doc_id),
                    )
            except Exception:
                pass  # skip files that can't be read
        conn.commit()
    except Exception:
        pass  # non-critical

    # pending_approval column for users awaiting admin approval
    try:
        conn.execute("ALTER TABLE users ADD COLUMN pending_approval INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # already exists

    # AI-managed user memory (flexible key-value store, written by LLM tool calls)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_memory (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'note',
                source      TEXT NOT NULL DEFAULT 'ai',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE(user_id, key)
            );
            CREATE INDEX IF NOT EXISTS idx_um_user ON user_memory(user_id);
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Exam approval workflow tables
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS exam_submissions (
                id              TEXT PRIMARY KEY,
                created_by      TEXT NOT NULL,
                conversation_id TEXT NOT NULL DEFAULT '',
                title           TEXT NOT NULL DEFAULT 'Exam Paper',
                questions_json  TEXT NOT NULL DEFAULT '[]',
                header_json     TEXT NOT NULL DEFAULT '{}',
                raw_text        TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'pending',
                total_stages    INTEGER NOT NULL DEFAULT 1,
                current_stage   INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_es_user   ON exam_submissions(created_by);
            CREATE INDEX IF NOT EXISTS idx_es_status ON exam_submissions(status);

            CREATE TABLE IF NOT EXISTS approval_stages (
                id            TEXT PRIMARY KEY,
                submission_id TEXT NOT NULL REFERENCES exam_submissions(id) ON DELETE CASCADE,
                stage_number  INTEGER NOT NULL,
                officer_id    TEXT NOT NULL,
                officer_name  TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'pending',
                remark        TEXT NOT NULL DEFAULT '',
                actioned_at   TEXT,
                created_at    TEXT NOT NULL,
                UNIQUE(submission_id, stage_number)
            );
            CREATE INDEX IF NOT EXISTS idx_as_sub    ON approval_stages(submission_id);
            CREATE INDEX IF NOT EXISTS idx_as_officer ON approval_stages(officer_id);
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Exam structured questions table (persists parsed questions per conversation)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS exam_structured_questions (
                conversation_id TEXT PRIMARY KEY,
                questions_json  TEXT NOT NULL DEFAULT '[]',
                updated_at      TEXT NOT NULL
            );
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Ensure a default admin account exists
    # existing = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    # if not existing:
    #     from app.auth import hash_password
    #     now = datetime.now(timezone.utc).isoformat()
    #     conn.execute(
    #         "INSERT INTO users (id, username, password, role, agents, is_active, created_at, updated_at) "
    #         "VALUES (?,?,?,?,?,?,?,?)",
    #         (
    #             str(uuid.uuid4()),
    #             "admin",
    #             hash_password("admin123"),
    #             "admin",
    #             json.dumps(["chat", "general", "exam", "knowledge"]),
    #             1,
    #             now,
    #             now,
    #         ),
    #     )
    #     conn.commit()

    # conn.close()


# ── CRUD helpers ───────────────────────────────────────────────────────────

def create_conversation(agent_type: str, title: str = "New Chat", user_id: str | None = None) -> dict:
    conn = _connect()
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO conversations (id, agent_type, title, created_at, updated_at, user_id) VALUES (?,?,?,?,?,?)",
        (conv_id, agent_type, title, now, now, user_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
    conn.close()
    return dict(row)


def list_conversations(agent_type: str | None = None, user_id: str | None = "__unset__") -> list[dict]:
    conn = _connect()
    conditions = []
    params = []
    if agent_type:
        conditions.append("agent_type=?")
        params.append(agent_type)
    if user_id == "__unset__":
        pass  # no user filter
    elif user_id is not None:
        conditions.append("user_id=?")
        params.append(user_id)
    else:
        conditions.append("user_id IS NULL")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM conversations {where} ORDER BY updated_at DESC",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation_ids_by_user(user_id: str) -> list[str]:
    """Return all conversation IDs owned by *user_id*."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id FROM conversations WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def delete_conversation(conv_id: str) -> bool:
    conn = _connect()
    # Collect file paths registered for this conversation before deleting
    file_rows = conn.execute(
        "SELECT file_path FROM conversation_files WHERE conversation_id=?", (conv_id,)
    ).fetchall()
    conn.execute("DELETE FROM conversation_files WHERE conversation_id=?", (conv_id,))
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    cur = conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    # Delete uploaded files from disk
    if deleted:
        import shutil
        for row in file_rows:
            fp = Path(row["file_path"])
            if fp.exists():
                try:
                    shutil.rmtree(fp.parent, ignore_errors=True)
                except Exception:
                    pass
    return deleted


def register_conversation_file(conversation_id: str, file_id: str, file_path: str) -> None:
    """Record an uploaded file as belonging to a conversation for cleanup on deletion."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    entry_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO conversation_files (id, conversation_id, file_id, file_path, created_at) VALUES (?,?,?,?,?)",
        (entry_id, conversation_id, file_id, file_path, now),
    )
    conn.commit()
    conn.close()


def rename_conversation(conv_id: str, title: str) -> bool:
    conn = _connect()
    cur = conn.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def add_message(conversation_id: str, role: str, content: str, sources: list | None = None) -> dict:
    conn = _connect()
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources or [])
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content, sources, created_at) VALUES (?,?,?,?,?,?)",
        (msg_id, conversation_id, role, content, sources_json, now),
    )
    conn.execute(
        "UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    return dict(row)


def get_messages(conversation_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["sources"] = json.loads(d.get("sources") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["sources"] = []
        result.append(d)
    return result


# ── User CRUD ──────────────────────────────────────────────────────────────

def _user_row_to_dict(row) -> dict:
    d = dict(row)
    d["agents"] = json.loads(d["agents"])
    d["pending_approval"] = bool(d.get("pending_approval", 0))
    return d


def get_user_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return _user_row_to_dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return _user_row_to_dict(row) if row else None


def create_user(
    username: str,
    password_hash: str,
    role: str = "user",
    agents: list[str] | None = None,
    is_active: int = 1,
    pending_approval: bool = False,
) -> dict:
    conn = _connect()
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    agents_json = json.dumps(agents or ["chat"])
    conn.execute(
        "INSERT INTO users (id, username, password, role, agents, is_active, pending_approval, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, username, password_hash, role, agents_json, is_active, int(pending_approval), now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return _user_row_to_dict(row)


def list_users() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_user_row_to_dict(r) for r in rows]


def list_pending_users() -> list[dict]:
    """Return users awaiting admin approval (pending_approval=1, is_active=0)."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM users WHERE pending_approval=1 AND is_active=0 ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [_user_row_to_dict(r) for r in rows]


def approve_pending_user(user_id: str) -> bool:
    """Activate a pending user (pending_approval -> 0, is_active -> 1)."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE users SET is_active=1, pending_approval=0, updated_at=? WHERE id=? AND pending_approval=1",
        (now, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def update_user(user_id: str, role: str | None = None, agents: list[str] | None = None, is_active: int | None = None) -> bool:
    conn = _connect()
    sets = []
    params = []
    if role is not None:
        sets.append("role=?")
        params.append(role)
    if agents is not None:
        sets.append("agents=?")
        params.append(json.dumps(agents))
    if is_active is not None:
        sets.append("is_active=?")
        params.append(is_active)
    if not sets:
        conn.close()
        return False
    now = datetime.now(timezone.utc).isoformat()
    sets.append("updated_at=?")
    params.append(now)
    params.append(user_id)
    cur = conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_user(user_id: str) -> bool:
    conn = _connect()
    cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_user_password(user_id: str, password_hash: str) -> bool:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute("UPDATE users SET password=?, updated_at=? WHERE id=?", (password_hash, now, user_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


# ── Knowledge Documents CRUD ───────────────────────────────────────────────

def find_duplicate_document(filename: str, file_hash: str) -> dict | None:
    """Return the first existing document that matches by content hash OR filename.

    Returns a dict with keys 'match_type' ('hash' or 'filename') and the document
    fields, or None if no duplicate is found.
    """
    conn = _connect()
    # Check content hash first (strongest signal — same bytes, possibly renamed)
    if file_hash:
        row = conn.execute(
            "SELECT * FROM knowledge_documents WHERE file_hash=? AND file_hash != ''",
            (file_hash,),
        ).fetchone()
        if row:
            conn.close()
            return {**dict(row), "match_type": "hash"}
    # Fall back to case-insensitive filename match
    row = conn.execute(
        "SELECT * FROM knowledge_documents WHERE LOWER(filename)=LOWER(?)",
        (filename,),
    ).fetchone()
    conn.close()
    if row:
        return {**dict(row), "match_type": "filename"}
    return None


def add_knowledge_document(doc_id: str, filename: str, file_size: int, chunk_count: int, uploaded_by: str | None = None, file_path: str = "", file_hash: str = "") -> dict:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO knowledge_documents (id, filename, file_size, chunk_count, uploaded_by, created_at, file_path, file_hash) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (doc_id, filename, file_size, chunk_count, uploaded_by, now, file_path, file_hash),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM knowledge_documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    return dict(row)


def update_knowledge_document_chunks(doc_id: str, chunk_count: int) -> None:
    """Update chunk_count after background indexing finishes."""
    conn = _connect()
    conn.execute(
        "UPDATE knowledge_documents SET chunk_count=? WHERE id=?",
        (chunk_count, doc_id),
    )
    conn.commit()
    conn.close()


def get_knowledge_document(doc_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM knowledge_documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_knowledge_documents() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM knowledge_documents ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_knowledge_document(doc_id: str) -> bool:
    conn = _connect()
    # Get file path before deleting
    row = conn.execute("SELECT file_path FROM knowledge_documents WHERE id=?", (doc_id,)).fetchone()
    cur = conn.execute("DELETE FROM knowledge_documents WHERE id=?", (doc_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    # Clean up file on disk
    if deleted and row and row["file_path"]:
        import shutil
        fp = Path(row["file_path"])
        if fp.exists():
            shutil.rmtree(fp.parent, ignore_errors=True)
    conn.close()
    return deleted


# ── User Memory CRUD ───────────────────────────────────────────────────────

def upsert_user_memory(user_id: str, key: str, value: str, category: str = "note", source: str = "ai") -> None:
    """Insert or update a memory entry for *user_id*. Uses upsert on (user_id, key)."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO user_memory (id, user_id, key, value, category, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value      = excluded.value,
            category   = excluded.category,
            source     = excluded.source,
            updated_at = excluded.updated_at
        """,
        (str(uuid.uuid4()), user_id, key.strip()[:80], value.strip()[:500], category, source, now, now),
    )
    conn.commit()
    conn.close()


def get_user_memories(user_id: str) -> list[dict]:
    """Return all memory entries for *user_id* ordered by category then key."""
    conn = _connect()
    rows = conn.execute(
        "SELECT key, value, category, source, updated_at "
        "FROM user_memory WHERE user_id=? ORDER BY category, key",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user_memory(user_id: str, key: str) -> bool:
    """Delete a single memory entry. Returns True if a row was deleted."""
    conn = _connect()
    cur = conn.execute(
        "DELETE FROM user_memory WHERE user_id=? AND key=?", (user_id, key)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def clear_knowledge_documents() -> None:
    conn = _connect()
    conn.execute("DELETE FROM knowledge_documents")
    conn.commit()
    conn.close()


def rename_knowledge_document(doc_id: str, new_filename: str) -> bool:
    """Rename a knowledge document's display filename."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE knowledge_documents SET filename=? WHERE id=?",
        (new_filename, doc_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


# ── Knowledge Chunks — now handled by app.chroma_store ────────────────────
# (FTS5 tables removed; use app.chroma_store for vector search)


# ── Analytics CRUD ─────────────────────────────────────────────────────────

def log_analytics_event(user_id: str | None, agent_type: str, message_len: int = 0) -> None:
    """Insert one analytics row. Called fire-and-forget from routers."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO analytics_events (id, user_id, agent_type, message_len, created_at) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, agent_type, message_len, now),
    )
    conn.commit()
    conn.close()


def get_analytics_summary() -> dict:
    """Return overall platform statistics for the admin dashboard."""
    conn = _connect()

    total_messages = conn.execute("SELECT COUNT(*) FROM analytics_events").fetchone()[0]
    total_users    = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    total_docs     = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
    total_convs    = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

    # Messages per agent type
    by_agent = {}
    for row in conn.execute(
        "SELECT agent_type, COUNT(*) as cnt FROM analytics_events GROUP BY agent_type"
    ).fetchall():
        by_agent[row["agent_type"]] = row["cnt"]

    # Daily message counts for the last 14 days
    daily = []
    for row in conn.execute(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt "
        "FROM analytics_events "
        "WHERE created_at >= DATE('now','-14 days') "
        "GROUP BY day ORDER BY day"
    ).fetchall():
        daily.append({"date": row["day"], "count": row["cnt"]})

    # Top 10 most active users
    top_users = []
    for row in conn.execute(
        "SELECT u.username, COUNT(a.id) as msg_count "
        "FROM analytics_events a "
        "LEFT JOIN users u ON a.user_id = u.id "
        "GROUP BY a.user_id ORDER BY msg_count DESC LIMIT 10"
    ).fetchall():
        top_users.append({"username": row["username"] or "guest", "messages": row["msg_count"]})

    conn.close()
    return {
        "total_messages": total_messages,
        "total_users": total_users,
        "total_documents": total_docs,
        "total_conversations": total_convs,
        "by_agent": by_agent,
        "daily_messages": daily,
        "top_users": top_users,
    }


def get_user_analytics(user_id: str) -> dict:
    """Return analytics specific to one user."""
    conn = _connect()
    total = conn.execute(
        "SELECT COUNT(*) FROM analytics_events WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    by_agent = {}
    for row in conn.execute(
        "SELECT agent_type, COUNT(*) as cnt FROM analytics_events WHERE user_id=? GROUP BY agent_type",
        (user_id,),
    ).fetchall():
        by_agent[row["agent_type"]] = row["cnt"]
    daily = []
    for row in conn.execute(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt "
        "FROM analytics_events WHERE user_id=? AND created_at >= DATE('now','-14 days') "
        "GROUP BY day ORDER BY day",
        (user_id,),
    ).fetchall():
        daily.append({"date": row["day"], "count": row["cnt"]})
    conn.close()
    return {"total_messages": total, "by_agent": by_agent, "daily_messages": daily}


# ── Exam Approval Workflow CRUD ────────────────────────────────────────────

def _row_to_submission(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """Convert a raw exam_submissions row to a dict, adding parsed questions/header and stages."""
    d = dict(row)
    try:
        d["questions"] = json.loads(d.pop("questions_json", "[]"))
    except Exception:
        d["questions"] = []
    try:
        d["header"] = json.loads(d.pop("header_json", "{}"))
    except Exception:
        d["header"] = {}
    stages = conn.execute(
        "SELECT * FROM approval_stages WHERE submission_id=? ORDER BY stage_number ASC",
        (d["id"],),
    ).fetchall()
    d["stages"] = [dict(s) for s in stages]
    return d


def submit_exam_for_approval(
    created_by: str,
    conversation_id: str,
    title: str,
    questions: list,
    header: dict,
    raw_text: str,
    stages: list[dict],  # [{"officer_id": str, "officer_name": str}, ...]
) -> dict:
    """Create an exam_submission with its approval_stages and return the full dict."""
    conn = _connect()
    sub_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    total_stages = len(stages)
    conn.execute(
        """INSERT INTO exam_submissions
           (id, created_by, conversation_id, title, questions_json, header_json, raw_text,
            status, total_stages, current_stage, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            sub_id, created_by, conversation_id, title,
            json.dumps(questions), json.dumps(header), raw_text,
            "pending", total_stages, 1, now, now,
        ),
    )
    for i, stage in enumerate(stages, start=1):
        conn.execute(
            """INSERT INTO approval_stages
               (id, submission_id, stage_number, officer_id, officer_name,
                status, remark, actioned_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), sub_id, i,
                stage["officer_id"], stage.get("officer_name", ""),
                "pending", "", None, now,
            ),
        )
    conn.commit()
    result = _row_to_submission(conn, conn.execute("SELECT * FROM exam_submissions WHERE id=?", (sub_id,)).fetchone())
    conn.close()
    return result


def get_submission_full(submission_id: str) -> dict | None:
    """Return full submission dict with nested stages, or None if not found."""
    conn = _connect()
    row = conn.execute("SELECT * FROM exam_submissions WHERE id=?", (submission_id,)).fetchone()
    if not row:
        conn.close()
        return None
    result = _row_to_submission(conn, row)
    conn.close()
    return result


def list_my_submissions(user_id: str) -> list[dict]:
    """Return all exam submissions created by a user, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM exam_submissions WHERE created_by=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    result = [_row_to_submission(conn, r) for r in rows]
    conn.close()
    return result


def delete_submission(submission_id: str, user_id: str) -> bool:
    """Delete a pending submission created by user_id. Returns True if deleted."""
    conn = _connect()
    row = conn.execute(
        "SELECT status, created_by FROM exam_submissions WHERE id=?", (submission_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row["created_by"] != user_id:
        conn.close()
        raise ValueError("Not authorized to delete this submission")
    if row["status"] != "pending":
        conn.close()
        raise ValueError("Only pending submissions can be deleted")
    conn.execute("DELETE FROM approval_stages WHERE submission_id=?", (submission_id,))
    conn.execute("DELETE FROM exam_submissions WHERE id=?", (submission_id,))
    conn.commit()
    conn.close()
    return True


def list_pending_for_officer(officer_id: str) -> list[dict]:
    """Return submissions where this officer is assigned to the current pending stage."""
    conn = _connect()
    rows = conn.execute(
        """SELECT es.* FROM exam_submissions es
           JOIN approval_stages ast ON ast.submission_id = es.id
           WHERE es.status = 'pending'
             AND ast.officer_id = ?
             AND ast.stage_number = es.current_stage
             AND ast.status = 'pending'
           ORDER BY es.created_at DESC""",
        (officer_id,),
    ).fetchall()
    result = [_row_to_submission(conn, r) for r in rows]
    conn.close()
    return result


def list_processed_by_officer(officer_id: str) -> list[dict]:
    """Return submissions where this officer has already taken action (newest action first)."""
    conn = _connect()
    rows = conn.execute(
        """SELECT DISTINCT es.* FROM exam_submissions es
           JOIN approval_stages ast ON ast.submission_id = es.id
           WHERE ast.officer_id = ?
             AND ast.status != 'pending'
           ORDER BY es.updated_at DESC""",
        (officer_id,),
    ).fetchall()
    result = [_row_to_submission(conn, r) for r in rows]
    conn.close()
    return result


def process_approval_action(
    submission_id: str,
    officer_id: str,
    action: str,   # "approve" | "send_back"
    remark: str,
) -> dict:
    """Officer takes action on a pending stage.  Raises ValueError on invalid state."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()

    sub = conn.execute(
        "SELECT * FROM exam_submissions WHERE id=?", (submission_id,)
    ).fetchone()
    if not sub:
        conn.close()
        raise ValueError("Submission not found")
    sub = dict(sub)

    if sub["status"] != "pending":
        conn.close()
        raise ValueError("Submission is not in pending state")

    stage = conn.execute(
        """SELECT * FROM approval_stages
           WHERE submission_id=? AND stage_number=? AND officer_id=?""",
        (submission_id, sub["current_stage"], officer_id),
    ).fetchone()
    if not stage:
        conn.close()
        raise ValueError("You are not assigned to this approval stage")
    stage = dict(stage)
    if stage["status"] != "pending":
        conn.close()
        raise ValueError("You have already acted on this stage")

    # Record the stage action
    conn.execute(
        "UPDATE approval_stages SET status=?, remark=?, actioned_at=? WHERE id=?",
        (action, remark, now, stage["id"]),
    )

    if action == "approve":
        if sub["current_stage"] >= sub["total_stages"]:
            # All stages approved — mark fully approved
            conn.execute(
                "UPDATE exam_submissions SET status='approved', updated_at=? WHERE id=?",
                (now, submission_id),
            )
        else:
            # Advance to next stage
            conn.execute(
                "UPDATE exam_submissions SET current_stage=?, updated_at=? WHERE id=?",
                (sub["current_stage"] + 1, now, submission_id),
            )
    elif action == "send_back":
        conn.execute(
            "UPDATE exam_submissions SET status='sent_back', updated_at=? WHERE id=?",
            (now, submission_id),
        )

    conn.commit()
    row = conn.execute("SELECT * FROM exam_submissions WHERE id=?", (submission_id,)).fetchone()
    result = _row_to_submission(conn, row)
    conn.close()
    return result


def list_approval_officers() -> list[dict]:
    """Return active users who have 'approval' in their agents list."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, username FROM users WHERE is_active=1 AND agents LIKE '%\"approval\"%'",
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "username": r["username"]} for r in rows]


# ── Structured exam questions (per conversation) ───────────────────────────

def save_exam_structured_questions(conversation_id: str, questions: list) -> None:
    """Persist parsed structured questions for a conversation (upsert)."""
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO exam_structured_questions (conversation_id, questions_json, updated_at)
           VALUES (?,?,?)
           ON CONFLICT(conversation_id) DO UPDATE SET questions_json=excluded.questions_json, updated_at=excluded.updated_at""",
        (conversation_id, json.dumps(questions), now),
    )
    conn.commit()
    conn.close()


def get_exam_structured_questions(conversation_id: str) -> list:
    """Retrieve stored structured questions for a conversation. Returns [] if none."""
    conn = _connect()
    row = conn.execute(
        "SELECT questions_json FROM exam_structured_questions WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["questions_json"])
        except Exception:
            return []
    return []


# ── Update submission questions (owner/approver editing) ──────────────────

def update_submission_questions(
    submission_id: str,
    user_id: str,
    questions: list,
    user_role: str = "user",
) -> dict:
    """Allow owner or an assigned officer to update the questions of a submission.

    Owner can edit only their own pending/sent_back submissions.
    Officers can edit only pending submissions assigned to them.
    Admins can edit any.
    """
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM exam_submissions WHERE id=?", (submission_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("Submission not found")
    sub = dict(row)

    is_admin = user_role == "admin"
    is_owner = sub["created_by"] == user_id
    # Check if user is an assigned officer for this submission
    officer_stage = conn.execute(
        "SELECT id FROM approval_stages WHERE submission_id=? AND officer_id=?",
        (submission_id, user_id),
    ).fetchone()
    is_officer = officer_stage is not None

    if not is_admin and not is_owner and not is_officer:
        conn.close()
        raise ValueError("Not authorized to edit this submission")

    # Owner may only edit pending or sent_back submissions
    if is_owner and not is_admin and sub["status"] not in ("pending", "sent_back"):
        conn.close()
        raise ValueError("Approved submissions cannot be edited")

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE exam_submissions SET questions_json=?, updated_at=? WHERE id=?",
        (json.dumps(questions), now, submission_id),
    )
    conn.commit()
    result = _row_to_submission(conn, conn.execute("SELECT * FROM exam_submissions WHERE id=?", (submission_id,)).fetchone())
    conn.close()
    return result

