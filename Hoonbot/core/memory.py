"""Memory utilities: prompt assembly, command-tag parsing, and extra-path loading.

This module assembles the 'memory side' of the LLM context (persistent memory,
daily logs, schedules, extra reference docs) and provides regex-based parsing
for [MEMORY_SAVE] / [MEMORY_DELETE] command tags (fallback for LLMs without
tool-calling support).

Actual memory storage is handled by memory_file.py (data/memory.md).
"""
import os
import re
import logging
from typing import List, Dict

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


async def format_for_prompt() -> str:
    """Return memories + daily logs + schedules + extra reference docs for the system prompt.

    This is the 'memory.md' side of context — everything persistent.
    The ephemeral side (current time, sysinfo) is in context_file.
    """
    from core import memory_file as mem_file
    from core import daily_log
    from core import scheduled as sched_store

    parts = []

    # --- Persistent memory (data/memory.md) ---
    file_mem = mem_file.load()
    if file_mem:
        parts.append(file_mem)

    # --- Daily logs (data/memory/YYYY-MM-DD.md, last 3 days) ---
    logs = daily_log.load_recent_logs(days=3)
    if logs:
        parts.append(logs)

    # --- Scheduled jobs (data/schedules.json) ---
    jobs = await sched_store.list_jobs()
    if jobs:
        lines = ["## Scheduled Jobs\n"]
        for j in jobs:
            schedule = j["cron"] if j["cron"] else f"once at {j['once_at']}"
            lr = f", last ran {j['last_run'][:16]}" if j["last_run"] else ""
            lines.append(f"- #{j['id']} **{j['name']}**: {schedule} → {j['prompt']}{lr}")
        parts.append("\n".join(lines))

    # --- Extra reference paths ---
    extra = _load_extra_paths()
    if extra:
        parts.append(extra)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Extra reference docs
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Command-tag parsing (fallback for LLMs without tool calling)
# ---------------------------------------------------------------------------


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
