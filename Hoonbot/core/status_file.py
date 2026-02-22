"""
Generate a human-readable Markdown snapshot of all DB state.

Called after any memory or schedule change so data/status.md
stays in sync with SQLite without replacing the DB.
"""
import os
import logging
from datetime import datetime, timezone

import aiosqlite
import config

logger = logging.getLogger(__name__)

STATUS_PATH = os.path.join(os.path.dirname(config.DB_PATH), "status.md")


async def refresh(db: aiosqlite.Connection) -> None:
    """Rewrite data/status.md with current memories and schedules."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [f"# Hoonbot Status\n\n_Auto-generated at {now} — do not edit, changes will be overwritten._\n"]

    # --- Memories (skip internal _system entries) ---
    sections.append("## Memories\n")
    async with db.execute(
        "SELECT key, value, tags, updated_at FROM memory ORDER BY updated_at DESC"
    ) as cur:
        rows = await cur.fetchall()
    user_rows = [(k, v, t, u) for k, v, t, u in rows if "_system" not in (t or "")]
    if user_rows:
        for key, value, tags, updated in user_rows:
            tag_part = f" `[{tags}]`" if tags else ""
            sections.append(f"- **{key}**: {value}{tag_part}  _(updated {updated[:10]})_")
    else:
        sections.append("_No memories stored._")

    sections.append("")

    # --- Scheduled Jobs ---
    sections.append("## Scheduled Jobs\n")
    async with db.execute(
        "SELECT id, name, cron, once_at, room_id, prompt, enabled, last_run FROM scheduled_jobs ORDER BY id"
    ) as cur:
        rows = await cur.fetchall()
    if rows:
        sections.append("| ID | Name | Type | Schedule | Room | Prompt | Enabled | Last Run |")
        sections.append("|---|---|---|---|---|---|---|---|")
        for id_, name, cron, once_at, room_id, prompt, enabled, last_run in rows:
            stype = "recurring" if cron else "one-time"
            schedule = cron if cron else once_at
            status = "yes" if enabled else "no"
            lr = last_run[:16] if last_run else "never"
            sections.append(f"| {id_} | {name} | {stype} | `{schedule}` | {room_id} | {prompt} | {status} | {lr} |")
    else:
        sections.append("_No scheduled jobs._")

    sections.append("")

    # --- Room History Stats ---
    sections.append("## Conversation History\n")
    async with db.execute(
        "SELECT room_id, COUNT(*) as cnt, MAX(timestamp) as latest FROM room_history GROUP BY room_id ORDER BY room_id"
    ) as cur:
        rows = await cur.fetchall()
    if rows:
        for room_id, count, latest in rows:
            latest_short = latest[:16] if latest else "?"
            sections.append(f"- Room {room_id}: {count} messages (latest: {latest_short})")
    else:
        sections.append("_No conversation history._")

    # --- Skills ---
    sections.append("## Skills\n")
    from core import skills as skills_mod
    skill_names = skills_mod.list_skills()
    if skill_names:
        for name in skill_names:
            sections.append(f"- {name}")
    else:
        sections.append("_No skills installed._")

    sections.append("")

    # Write
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(sections) + "\n")
    logger.debug(f"[Status] Refreshed {STATUS_PATH}")
