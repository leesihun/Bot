"""Persistent key-value memory store backed by SQLite FTS5."""
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional

import aiosqlite


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
    if tag:
        async with db.execute(
            "SELECT key, value, tags, updated_at FROM memory WHERE tags LIKE ? ORDER BY key",
            (f"%{tag}%",),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT key, value, tags, updated_at FROM memory ORDER BY key"
        ) as cur:
            rows = await cur.fetchall()
    return [{"key": r[0], "value": r[1], "tags": r[2], "updated_at": r[3]} for r in rows]


async def format_for_prompt(db: aiosqlite.Connection) -> str:
    """Return all memories as a compact string for injection into a system prompt."""
    rows = await list_all(db)
    if not rows:
        return ""
    lines = ["## Persistent Memory\n"]
    for r in rows:
        tag_suffix = f" [{r['tags']}]" if r["tags"] else ""
        lines.append(f"- {r['key']}: {r['value']}{tag_suffix}")
    return "\n".join(lines)


def parse_memory_commands(text: str) -> List[Dict]:
    """
    Extract [MEMORY_SAVE: key=..., value=..., tags=...] commands from LLM output.
    Returns list of dicts with keys: key, value, tags (list).
    """
    pattern = r'\[MEMORY_SAVE:\s*key=([^,\]]+),\s*value=([^,\]]+)(?:,\s*tags=([^\]]*))?\]'
    commands = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        key = m.group(1).strip()
        value = m.group(2).strip()
        tags = [t.strip() for t in m.group(3).split(",")] if m.group(3) else []
        commands.append({"key": key, "value": value, "tags": tags})
    return commands


def strip_memory_commands(text: str) -> str:
    """Remove [MEMORY_SAVE: ...] commands from text before sending to user."""
    pattern = r'\[MEMORY_SAVE:[^\]]*\]\n?'
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
