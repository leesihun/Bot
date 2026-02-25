"""
Generate a human-readable Markdown snapshot of all state.

Written to data/status.md after any memory or schedule change.
Reads from files (memory.md, schedules.json, history/) — no SQLite.
"""
import os
import logging
from datetime import datetime, timezone

import config
from core import memory_file as mem_file
from core import scheduled as sched_store
from core import skills as skills_mod

logger = logging.getLogger(__name__)

STATUS_PATH = os.path.join(os.path.dirname(config.DB_PATH), "status.md")


async def refresh() -> None:
    """Rewrite data/status.md with current memories, schedules, and skills."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [f"# Hoonbot Status\n\n_Auto-generated at {now} — do not edit, changes will be overwritten._\n"]

    # --- Memories (from data/memory.md) ---
    sections.append("## Memories\n")
    entries = mem_file.list_all()
    if entries:
        for entry in entries:
            ts_part = f" _({entry['ts']})_" if entry.get("ts") else ""
            tag_part = f" `[{entry['tags']}]`" if entry.get("tags") else ""
            sections.append(f"- **{entry['key']}**{ts_part}: {entry['value']}{tag_part}")
    else:
        sections.append("_No memories stored._")

    sections.append("")

    # --- Scheduled Jobs (from data/schedules.json) ---
    sections.append("## Scheduled Jobs\n")
    jobs = await sched_store.list_jobs()
    if jobs:
        sections.append("| ID | Name | Type | Schedule | Room | Prompt | Last Run |")
        sections.append("|---|---|---|---|---|---|---|")
        for j in jobs:
            stype = "recurring" if j["cron"] else "one-time"
            schedule = j["cron"] if j["cron"] else j["once_at"]
            lr = j["last_run"][:16] if j["last_run"] else "never"
            sections.append(f"| {j['id']} | {j['name']} | {stype} | `{schedule}` | {j['room_id']} | {j['prompt']} | {lr} |")
    else:
        sections.append("_No scheduled jobs._")

    sections.append("")

    # --- Conversation History Stats (from data/history/) ---
    sections.append("## Conversation History\n")
    from core import history as hist_store
    rooms = await hist_store.get_active_rooms()
    if rooms:
        for room_id in sorted(rooms):
            count = await hist_store.get_count(room_id)
            sections.append(f"- Room {room_id}: {count} messages")
    else:
        sections.append("_No conversation history._")

    # --- Skills ---
    sections.append("## Skills\n")
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
