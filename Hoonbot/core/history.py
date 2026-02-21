"""Per-room conversation history backed by SQLite."""
import json
from datetime import datetime, timezone
from typing import List, Dict

import aiosqlite
import config


async def init_history(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS room_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id   INTEGER NOT NULL,
            role      TEXT    NOT NULL,
            content   TEXT    NOT NULL,
            timestamp TEXT    NOT NULL
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_history_room ON room_history(room_id, id)")
    await db.commit()


async def add_message(db: aiosqlite.Connection, room_id: int, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO room_history (room_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (room_id, role, content, now),
    )
    await db.commit()
    await _trim(db, room_id)


async def get_history(db: aiosqlite.Connection, room_id: int) -> List[Dict[str, str]]:
    limit = config.MAX_HISTORY_MESSAGES
    async with db.execute(
        """SELECT role, content FROM room_history
           WHERE room_id = ?
           ORDER BY id DESC LIMIT ?""",
        (room_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    # Return in chronological order (oldest first)
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


async def clear_history(db: aiosqlite.Connection, room_id: int) -> None:
    await db.execute("DELETE FROM room_history WHERE room_id = ?", (room_id,))
    await db.commit()


async def _trim(db: aiosqlite.Connection, room_id: int) -> None:
    """Keep only the most recent MAX_HISTORY_MESSAGES rows per room."""
    limit = config.MAX_HISTORY_MESSAGES
    await db.execute(
        """DELETE FROM room_history WHERE room_id = ? AND id NOT IN (
               SELECT id FROM room_history WHERE room_id = ? ORDER BY id DESC LIMIT ?
           )""",
        (room_id, room_id, limit),
    )
    await db.commit()
