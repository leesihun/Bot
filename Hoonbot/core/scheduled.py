"""Scheduled messages / reminders backed by SQLite.

Users can ask Hoonbot to remind them or send periodic messages.
The LLM emits [SCHEDULE: ...] commands that are parsed and stored here.
On each heartbeat tick, due jobs are checked and executed.
"""
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import aiosqlite

logger = logging.getLogger(__name__)


async def init_scheduled(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            cron        TEXT    NOT NULL DEFAULT '',
            once_at     TEXT    NOT NULL DEFAULT '',
            room_id     INTEGER NOT NULL,
            prompt      TEXT    NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            last_run    TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL
        )
    """)
    await db.commit()


async def add_job(
    db: aiosqlite.Connection,
    name: str,
    room_id: int,
    prompt: str,
    cron: str = "",
    once_at: str = "",
) -> int:
    """Create a scheduled job. Returns the job ID."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        """INSERT INTO scheduled_jobs (name, cron, once_at, room_id, prompt, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, cron, once_at, room_id, prompt, now),
    )
    await db.commit()
    return cursor.lastrowid


async def remove_job(db: aiosqlite.Connection, job_id: int) -> bool:
    cursor = await db.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
    await db.commit()
    return cursor.rowcount > 0


async def list_jobs(db: aiosqlite.Connection, room_id: Optional[int] = None) -> List[Dict]:
    if room_id is not None:
        async with db.execute(
            "SELECT id, name, cron, once_at, room_id, prompt, enabled, last_run FROM scheduled_jobs WHERE room_id = ? AND enabled = 1 ORDER BY id",
            (room_id,),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT id, name, cron, once_at, room_id, prompt, enabled, last_run FROM scheduled_jobs WHERE enabled = 1 ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "cron": r[2], "once_at": r[3], "room_id": r[4],
         "prompt": r[5], "enabled": r[6], "last_run": r[7]}
        for r in rows
    ]


async def get_due_jobs(db: aiosqlite.Connection, now: datetime) -> List[Dict]:
    """Return jobs that are due to run based on current time.

    For cron jobs: checks if the current hour:minute matches and last_run is not today.
    For one-time jobs: checks if once_at <= now and hasn't been run yet.
    """
    jobs = await list_jobs(db)
    due = []
    now_str = now.strftime("%Y-%m-%d %H:%M")
    now_hm = now.strftime("%H:%M")
    now_date = now.strftime("%Y-%m-%d")

    for job in jobs:
        if job["cron"]:
            # Simple cron: "HH:MM" daily, or full 5-field (we support HH:MM shorthand)
            cron = job["cron"].strip()
            if _cron_matches(cron, now):
                # Don't run if already ran today
                if job["last_run"] and job["last_run"][:10] == now_date:
                    continue
                due.append(job)

        elif job["once_at"]:
            # One-time: ISO datetime string
            if job["once_at"] <= now_str and not job["last_run"]:
                due.append(job)

    return due


async def mark_run(db: aiosqlite.Connection, job_id: int, disable_if_once: bool = False) -> None:
    """Mark a job as having been run. For one-time jobs, disable them."""
    now = datetime.now(timezone.utc).isoformat()
    if disable_if_once:
        await db.execute(
            "UPDATE scheduled_jobs SET last_run = ?, enabled = 0 WHERE id = ?", (now, job_id)
        )
    else:
        await db.execute(
            "UPDATE scheduled_jobs SET last_run = ? WHERE id = ?", (now, job_id)
        )
    await db.commit()


def _cron_matches(cron: str, now: datetime) -> bool:
    """Check if a cron expression matches the current time.

    Supports:
    - "HH:MM" shorthand for daily at that time
    - "minute hour * * *" (5-field, only minute and hour checked for now)
    """
    cron = cron.strip()

    # HH:MM shorthand
    if re.match(r"^\d{1,2}:\d{2}$", cron):
        parts = cron.split(":")
        return now.hour == int(parts[0]) and now.minute == int(parts[1])

    # 5-field cron
    fields = cron.split()
    if len(fields) == 5:
        minute, hour, day, month, dow = fields
        if minute != "*" and now.minute != int(minute):
            return False
        if hour != "*" and now.hour != int(hour):
            return False
        if day != "*" and now.day != int(day):
            return False
        if month != "*" and now.month != int(month):
            return False
        if dow != "*" and now.isoweekday() % 7 != int(dow):
            return False
        return True

    return False


def parse_schedule_commands(text: str) -> List[Dict]:
    """Extract [SCHEDULE: ...] commands from LLM output.

    Format: [SCHEDULE: name=<name>, cron=<cron_or_time>, prompt=<what to do>]
    Or:     [SCHEDULE: name=<name>, at=<ISO datetime>, prompt=<what to do>]
    """
    pattern = r'\[SCHEDULE:\s*name=([^,\]]+),\s*(?:cron=([^,\]]+),\s*)?(?:at=([^,\]]+),\s*)?prompt=([^\]]+)\]'
    commands = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        name = m.group(1).strip()
        cron = (m.group(2) or "").strip()
        once_at = (m.group(3) or "").strip()
        prompt = m.group(4).strip()
        if name and prompt and (cron or once_at):
            commands.append({"name": name, "cron": cron, "once_at": once_at, "prompt": prompt})
    return commands


def strip_schedule_commands(text: str) -> str:
    """Remove [SCHEDULE: ...] commands from text before sending to user."""
    pattern = r'\[SCHEDULE:[^\]]*\]\n?'
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
