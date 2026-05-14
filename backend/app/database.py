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


def create_user(username: str, password_hash: str, role: str = "user", agents: list[str] | None = None) -> dict:
    conn = _connect()
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    agents_json = json.dumps(agents or ["chat"])
    conn.execute(
        "INSERT INTO users (id, username, password, role, agents, is_active, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, username, password_hash, role, agents_json, 1, now, now),
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

