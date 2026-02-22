"""Persistent key-value memory store backed by SQLite FTS5."""
import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import aiosqlite
import config

logger = logging.getLogger(__name__)


async def init_memory(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT    NOT NULL UNIQUE,
            value      TEXT    NOT NULL,
            tags       TEXT    NOT NULL DEFAULT '',
            created_at TEXT    NOT NULL,
            updated_at TEXT    NOT NULL
        )
    """)
    # FTS5 virtual table for full-text search over key + value + tags
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            key, value, tags,
            content='memory', content_rowid='id'
        )
    """)
    # Keep FTS in sync via triggers
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
            INSERT INTO memory_fts(rowid, key, value, tags)
            VALUES (new.id, new.key, new.value, new.tags);
        END
    """)
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, key, value, tags)
            VALUES ('delete', old.id, old.key, old.value, old.tags);
            INSERT INTO memory_fts(rowid, key, value, tags)
            VALUES (new.id, new.key, new.value, new.tags);
        END
    """)
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
            INSERT INTO memory_fts(memory_fts, rowid, key, value, tags)
            VALUES ('delete', old.id, old.key, old.value, old.tags);
        END
    """)
    await db.commit()


async def save(db: aiosqlite.Connection, key: str, value: str, tags: List[str] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    tags_str = ",".join(tags or [])
    await db.execute(
        """INSERT INTO memory (key, value, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               tags = excluded.tags,
               updated_at = excluded.updated_at""",
        (key, value, tags_str, now, now),
    )
    await db.commit()


async def delete(db: aiosqlite.Connection, key: str) -> bool:
    """Delete a memory by key. Returns True if a row was deleted."""
    cursor = await db.execute("DELETE FROM memory WHERE key = ?", (key,))
    await db.commit()
    return cursor.rowcount > 0


async def clear_all(db: aiosqlite.Connection) -> int:
    """Delete all memories. Returns count of deleted rows."""
    cursor = await db.execute("DELETE FROM memory")
    await db.commit()
    return cursor.rowcount


async def recall(db: aiosqlite.Connection, key: str) -> Optional[str]:
    async with db.execute("SELECT value FROM memory WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def search(db: aiosqlite.Connection, query: str, limit: int = 10) -> List[Dict]:
    async with db.execute(
        """SELECT m.key, m.value, m.tags, m.updated_at
           FROM memory_fts f JOIN memory m ON f.rowid = m.id
           WHERE memory_fts MATCH ?
           ORDER BY rank LIMIT ?""",
        (query, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [{"key": r[0], "value": r[1], "tags": r[2], "updated_at": r[3]} for r in rows]


async def list_all(db: aiosqlite.Connection, tag: Optional[str] = None) -> List[Dict]:
    # Order by updated_at DESC — most recently updated memories first (temporal relevance)
    if tag:
        async with db.execute(
            "SELECT key, value, tags, updated_at FROM memory WHERE tags LIKE ? ORDER BY updated_at DESC",
            (f"%{tag}%",),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT key, value, tags, updated_at FROM memory ORDER BY updated_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [{"key": r[0], "value": r[1], "tags": r[2], "updated_at": r[3]} for r in rows]


async def format_for_prompt(db: aiosqlite.Connection) -> str:
    """Return all memories + extra reference docs as a string for the system prompt.

    Memories are ordered by recency (most recently updated first) so the LLM
    naturally gives more weight to fresh information.
    """
    parts = []

    # --- SQLite memories (temporal order, skip internal _system entries) ---
    rows = await list_all(db)
    user_rows = [r for r in rows if "_system" not in r["tags"]]
    if user_rows:
        lines = ["## Persistent Memory\n"]
        for r in user_rows:
            tag_suffix = f" [{r['tags']}]" if r["tags"] else ""
            age = _format_age(r["updated_at"])
            lines.append(f"- {r['key']}: {r['value']}{tag_suffix}  _({age})_")
        parts.append("\n".join(lines))

    # --- Extra reference paths ---
    extra = _load_extra_paths()
    if extra:
        parts.append(extra)

    return "\n\n".join(parts)


def _format_age(updated_at: str) -> str:
    """Convert ISO timestamp to human-readable age string."""
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = (now - dt).days
        if days == 0:
            return "today"
        elif days == 1:
            return "yesterday"
        else:
            return f"{days}d ago"
    except Exception:
        return updated_at[:10]


def _load_extra_paths() -> str:
    """Synchronously load Markdown files from configured extra memory paths."""
    if not config.MEMORY_EXTRA_PATHS:
        return ""

    sections = []
    for raw_path in config.MEMORY_EXTRA_PATHS:
        path = os.path.expanduser(raw_path)
        if os.path.isfile(path) and path.endswith(".md"):
            _try_load_file(path, sections)
        elif os.path.isdir(path):
            for fname in sorted(os.listdir(path)):
                if fname.endswith(".md"):
                    _try_load_file(os.path.join(path, fname), sections)

    if not sections:
        return ""
    return "## Reference Documents\n\n" + "\n\n".join(sections)


def _try_load_file(path: str, sections: list) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            sections.append(f"### {os.path.basename(path)}\n\n{content}")
    except Exception as e:
        logger.warning(f"[Memory] Extra path load failed {path}: {e}")


def parse_memory_commands(text: str) -> List[Dict]:
    """
    Extract [MEMORY_SAVE: key=..., value=..., tags=...] commands from LLM output.
    Returns list of dicts with keys: key, value, tags (list).
    Value may contain commas — the regex uses lookahead for ', tags=' or ']'.
    """
    pattern = r'\[MEMORY_SAVE:\s*key=([^,\]]+),\s*value=(.*?)(?:,\s*tags=([^\]]*))?\]'
    commands = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        key = m.group(1).strip()
        value = m.group(2).strip()
        tags = [t.strip() for t in m.group(3).split(",") if t.strip()] if m.group(3) else []
        if key and value:
            commands.append({"key": key, "value": value, "tags": tags})
    return commands


def strip_memory_commands(text: str) -> str:
    """Remove [MEMORY_SAVE: ...] commands from text before sending to user."""
    pattern = r'\[MEMORY_SAVE:[^\]]*\]\n?'
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()


def parse_memory_delete_commands(text: str) -> List[str]:
    """Extract [MEMORY_DELETE: key=...] commands from LLM output. Returns list of keys."""
    pattern = r'\[MEMORY_DELETE:\s*key=([^\]]+)\]'
    return [m.group(1).strip() for m in re.finditer(pattern, text, re.IGNORECASE)]


def strip_memory_delete_commands(text: str) -> str:
    """Remove [MEMORY_DELETE: ...] commands from text."""
    pattern = r'\[MEMORY_DELETE:[^\]]*\]\n?'
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
