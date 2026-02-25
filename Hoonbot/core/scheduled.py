"""Scheduled messages / reminders backed by a JSON file (data/schedules.json).

Users can ask Hoonbot to remind them or send periodic messages.
The LLM emits [SCHEDULE: ...] commands (or calls create_schedule tool) that
are stored here. On each heartbeat tick, due jobs are checked and executed.
"""
import json
import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)

_SCHEDULES_FILE = os.path.join(config.DATA_DIR, "schedules.json")


# ---------------------------------------------------------------------------
# Internal file helpers
# ---------------------------------------------------------------------------

def _read_jobs() -> List[Dict]:
    try:
        with open(_SCHEDULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_jobs(jobs: List[Dict]) -> None:
    os.makedirs(os.path.dirname(_SCHEDULES_FILE), exist_ok=True)
    with open(_SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def _next_id(jobs: List[Dict]) -> int:
    return max((j["id"] for j in jobs), default=0) + 1


# ---------------------------------------------------------------------------
# Public API (async for compatibility with existing callers)
# ---------------------------------------------------------------------------

async def add_job(
    name: str,
    room_id: int,
    prompt: str,
    cron: str = "",
    once_at: str = "",
) -> int:
    """Create a scheduled job. Returns the job ID."""
    jobs = _read_jobs()
    job_id = _next_id(jobs)
    now = datetime.now(timezone.utc).isoformat()
    jobs.append({
        "id": job_id,
        "name": name,
        "cron": cron or "",
        "once_at": once_at or "",
        "room_id": room_id,
        "prompt": prompt,
        "enabled": True,
        "last_run": "",
        "created_at": now,
    })
    _write_jobs(jobs)
    logger.info(f"[Schedule] Created job #{job_id}: {name!r}")
    return job_id


async def remove_job(job_id: int) -> bool:
    jobs = _read_jobs()
    new_jobs = [j for j in jobs if j["id"] != job_id]
    if len(new_jobs) == len(jobs):
        return False
    _write_jobs(new_jobs)
    return True


async def list_jobs(room_id: Optional[int] = None) -> List[Dict]:
    jobs = _read_jobs()
    enabled = [j for j in jobs if j.get("enabled", True)]
    if room_id is not None:
        enabled = [j for j in enabled if j["room_id"] == room_id]
    return sorted(enabled, key=lambda j: j["id"])


async def get_due_jobs(now: datetime) -> List[Dict]:
    """Return jobs that are due to run based on current time."""
    jobs = await list_jobs()
    due = []
    now_str = now.strftime("%Y-%m-%d %H:%M")
    now_date = now.strftime("%Y-%m-%d")

    for job in jobs:
        if job["cron"]:
            if _cron_matches(job["cron"].strip(), now):
                if job["last_run"] and job["last_run"][:10] == now_date:
                    continue
                due.append(job)
        elif job["once_at"]:
            if job["once_at"] <= now_str and not job["last_run"]:
                due.append(job)

    return due


async def mark_run(job_id: int, disable_if_once: bool = False) -> None:
    """Mark a job as having been run. For one-time jobs, disable them."""
    jobs = _read_jobs()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for j in jobs:
        if j["id"] == job_id:
            j["last_run"] = now
            if disable_if_once:
                j["enabled"] = False
            break
    _write_jobs(jobs)


# ---------------------------------------------------------------------------
# Cron matching (unchanged from original)
# ---------------------------------------------------------------------------

def _cron_matches(cron: str, now: datetime) -> bool:
    """Check if a cron expression matches or is overdue at the current time.

    Uses "at or past" semantics: fires if the current time >= scheduled time.
    Combined with the per-day last_run guard in get_due_jobs, this ensures a
    daily job fires even when the heartbeat interval is coarser than one minute.

    Supports:
    - "HH:MM" shorthand for daily at that time
    - "minute hour day month dow" (5-field standard cron)
    """
    cron = cron.strip()

    if re.match(r"^\d{1,2}:\d{2}$", cron):
        parts = cron.split(":")
        sched_mins = int(parts[0]) * 60 + int(parts[1])
        now_mins = now.hour * 60 + now.minute
        return now_mins >= sched_mins

    fields = cron.split()
    if len(fields) == 5:
        minute, hour, day, month, dow = fields
        if month != "*" and now.month != int(month):
            return False
        if day != "*" and now.day != int(day):
            return False
        if dow != "*" and now.isoweekday() % 7 != int(dow):
            return False
        if hour != "*":
            sched_mins = int(hour) * 60 + (int(minute) if minute != "*" else 0)
            now_mins = now.hour * 60 + now.minute
            if now_mins < sched_mins:
                return False
        elif minute != "*" and now.minute < int(minute):
            return False
        return True

    return False


# ---------------------------------------------------------------------------
# Command tag parsing (unchanged — fallback for LLMs without tool calling)
# ---------------------------------------------------------------------------

def parse_schedule_commands(text: str) -> List[Dict]:
    """Extract [SCHEDULE: ...] commands from LLM output."""
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
