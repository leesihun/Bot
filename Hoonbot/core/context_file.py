"""
Unified context snapshot: data/context.md

Rebuilt on every heartbeat tick. Contains all sections Hoonbot needs:
  1. Persistent memory   (data/memory.md)
  2. Daily logs          (data/memory/YYYY-MM-DD.md, last 3 days)
  3. Scheduled jobs      (data/schedules.json)
  4. System status       (psutil)
  5. Heartbeat checklist (HEARTBEAT.md)

Heartbeat writes this file then reads it back as a single block.
No other source is read during the tick.
"""
import logging
import os
from datetime import datetime, timezone

import config
from core import daily_log
from core import memory_file as mem_file
from core import scheduled as sched_store
from core import sysinfo

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.dirname(config.DB_PATH)
CONTEXT_PATH = os.path.join(_DATA_DIR, "context.md")
_HEARTBEAT_PATH = os.path.join(os.path.dirname(config.SOUL_PATH), "HEARTBEAT.md")


def _load_checklist() -> str:
    try:
        with open(_HEARTBEAT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


async def refresh() -> str:
    """Rebuild data/context.md and return its full contents."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [f"_Context snapshot at {now}_\n"]

    # 1. Persistent memory
    memory = mem_file.load()
    if memory:
        sections.append(memory)

    # 2. Daily logs (last 3 days)
    logs = daily_log.load_recent_logs(days=3)
    if logs:
        sections.append(logs)

    # 3. Scheduled jobs
    jobs = await sched_store.list_jobs()
    if jobs:
        lines = ["## Scheduled Jobs\n"]
        for j in jobs:
            schedule = j["cron"] if j["cron"] else f"once at {j['once_at']}"
            lr = f", last ran {j['last_run'][:16]}" if j["last_run"] else ""
            lines.append(f"- #{j['id']} **{j['name']}**: {schedule} → {j['prompt']}{lr}")
        sections.append("\n".join(lines))

    # 4. System status
    info = sysinfo.get_system_info()
    if info:
        sections.append(info)

    # 5. Heartbeat checklist
    checklist = _load_checklist()
    if checklist:
        sections.append(checklist)

    content = "\n\n".join(sections)
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(CONTEXT_PATH, "w", encoding="utf-8") as f:
        f.write(content + "\n")

    logger.debug(f"[Context] Refreshed {CONTEXT_PATH}")
    return content


def load() -> str:
    """Read the last written context.md (without rebuilding)."""
    try:
        with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
