"""Daily memory logs — append-only narrative logs by date.

Inspired by OpenClaw's memory/YYYY-MM-DD.md approach.
The LLM appends notes via [DAILY_LOG: ...] commands.
Recent logs (today + yesterday) are injected into LLM context so Hoonbot
has a narrative of "what happened" without relying on chat history alone.

Files live at: data/memory/YYYY-MM-DD.md
"""
import os
import re
import logging
from datetime import datetime, timedelta
from typing import List

import config

logger = logging.getLogger(__name__)

LOGS_DIR = os.path.join(os.path.dirname(config.DB_PATH), "memory")


def _log_path(date: datetime) -> str:
    return os.path.join(LOGS_DIR, date.strftime("%Y-%m-%d") + ".md")


def load_recent_logs(days: int = 2) -> str:
    """Load the last N days of log files and return as a context string.
    Returns empty string if no logs exist yet.
    """
    today = datetime.now()
    sections = []

    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        path = _log_path(date)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                sections.append(content)
        except Exception as e:
            logger.warning(f"[DailyLog] Failed to read {path}: {e}")

    if not sections:
        return ""
    return "## Daily Log\n\n" + "\n\n---\n\n".join(sections)


def append_entry(entry: str) -> None:
    """Append a timestamped entry to today's log file."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    today = datetime.now()
    path = _log_path(today)

    timestamp = today.strftime("%H:%M")
    line = f"- {timestamp}: {entry.strip()}"

    is_new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {today.strftime('%Y-%m-%d')}\n\n")
        f.write(line + "\n")

    logger.debug(f"[DailyLog] Appended: {line}")


def parse_daily_log_commands(text: str) -> List[str]:
    """Extract [DAILY_LOG: ...] commands from LLM output. Returns list of entries."""
    pattern = r"\[DAILY_LOG:\s*([^\]]+)\]"
    return [m.group(1).strip() for m in re.finditer(pattern, text, re.IGNORECASE)]


def strip_daily_log_commands(text: str) -> str:
    """Remove [DAILY_LOG: ...] commands from text before sending to user."""
    pattern = r"\[DAILY_LOG:[^\]]*\]\n?"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
