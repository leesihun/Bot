"""
Live context snapshot: data/context.md

Regenerated on every LLM call. Contains only ephemeral / health-check data:
  - Current datetime (local + UTC)
  - System status (CPU, RAM, disk, battery)
  - HEARTBEAT.md checklist

Persistent information (memories, daily logs, schedules) lives in memory.md
and is loaded separately via mem_store.format_for_prompt().
"""
import logging
import os
from datetime import datetime, timezone

import config
from core import sysinfo

logger = logging.getLogger(__name__)

_DATA_DIR = config.DATA_DIR
CONTEXT_PATH = os.path.join(_DATA_DIR, "context.md")
_HEARTBEAT_PATH = os.path.join(os.path.dirname(config.SOUL_PATH), "HEARTBEAT.md")


def _load_checklist() -> str:
    try:
        with open(_HEARTBEAT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


async def refresh() -> str:
    """Rebuild data/context.md and return its contents."""
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = [f"## Current Context\n\n_Updated: {now_local} (local) / {now_utc}_\n"]

    info = sysinfo.get_system_info()
    if info:
        sections.append(info)

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
    """Read the last written context.md without rebuilding."""
    try:
        with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
