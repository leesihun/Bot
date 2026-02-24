"""
Heartbeat: periodic proactive reasoning loop.

On each tick, Hoonbot:
1. Checks active hours — skips if outside configured window
2. Runs any due scheduled jobs
3. Loads memory + history + schedule context + system status + HEARTBEAT.md checklist
4. Asks LLM what to do proactively
5. Acts: send message, run background task (non-blocking), or create a scheduled job

Edit HEARTBEAT.md to customize what the heartbeat checks each tick.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

import aiosqlite
import config
from core import (
    llm,
    messenger,
    memory as mem_store,
    history as hist_store,
    scheduled as sched_store,
    status_file,
    sysinfo,
)

logger = logging.getLogger(__name__)

_HEARTBEAT_PATH = os.path.join(os.path.dirname(config.SOUL_PATH), "HEARTBEAT.md")

_HEARTBEAT_SYSTEM = """\
You are Hoonbot running an autonomous background tick. It is now {datetime}.

Below is your full context: persistent memory, recent conversation, current scheduled jobs,
and system status. Read the checklist below for what to check each tick.

Respond ONLY with a single JSON object — no prose before or after:
  {{"action": "none"}}
  {{"action": "message", "content": "<message to send to user>"}}
  {{"action": "task", "content": "<description of background task to run>"}}
  {{"action": "schedule", "name": "<short_name>", "cron": "<HH:MM or 5-field cron>", "prompt": "<what to do>"}}
  {{"action": "schedule", "name": "<short_name>", "at": "<YYYY-MM-DD HH:MM>", "prompt": "<what to do>"}}

Be conservative. Most ticks should return {{"action": "none"}}.
Never return the internal probe token as a user-visible message.
"""

_TASK_EXECUTOR_SYSTEM = """\
You are Hoonbot executing a background task. Complete the following task and return a concise
summary of the result. Use your tools (web search, code execution, etc.) as needed.

Task: {task}
"""

_HEARTBEAT_PROBE_MESSAGE = "[HEARTBEAT_INTERNAL_DECISION_PROBE]"
_LEGACY_HEARTBEAT_PROBE_MESSAGE = "What should you do right now?"


def _load_heartbeat_checklist() -> str:
    """Load HEARTBEAT.md. Returns empty string if not found."""
    try:
        with open(_HEARTBEAT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _is_active_hours() -> bool:
    """Check if current local time is within the configured active hours window."""
    start = config.HEARTBEAT_ACTIVE_START
    end = config.HEARTBEAT_ACTIVE_END
    if not start or not end or (start == "00:00" and end == "23:59"):
        return True
    current = datetime.now().strftime("%H:%M")
    if start <= end:
        return start <= current <= end
    else:  # spans midnight
        return current >= start or current <= end


async def _run_scheduled_jobs(db: aiosqlite.Connection, local_now: datetime = None) -> None:
    """Check for due scheduled jobs and execute them using local time."""
    now = local_now or datetime.now()
    due_jobs = await sched_store.get_due_jobs(db, now)

    for job in due_jobs:
        room_id = job["room_id"]
        logger.info(f"[Schedule] Executing job #{job['id']}: {job['name']}")
        try:
            soul = llm.load_soul()
            messages = [
                {"role": "system", "content": soul},
                {"role": "user", "content": f"Execute this scheduled task: {job['prompt']}"},
            ]
            result = await llm.chat(messages, agent_type="chat")
            await messenger.send_message(room_id, result)
            await hist_store.add_message(db, room_id, "assistant", result)
            is_once = bool(job["once_at"])
            await sched_store.mark_run(db, job["id"], disable_if_once=is_once)
        except Exception as exc:
            logger.error(f"[Schedule] Job failed: {exc}", exc_info=True)

    if due_jobs:
        await status_file.refresh(db)


async def tick(db: aiosqlite.Connection) -> None:
    """Single heartbeat tick."""
    if not config.HEARTBEAT_ENABLED:
        return

    if not _is_active_hours():
        logger.debug(
            f"[Heartbeat] Skipping — outside active hours "
            f"({config.HEARTBEAT_ACTIVE_START}–{config.HEARTBEAT_ACTIVE_END})"
        )
        return

    room_id = config.MESSENGER_HOME_ROOM_ID
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"[Heartbeat] Tick at {now}")

    local_now = datetime.now()
    await _run_scheduled_jobs(db, local_now)
    await _maybe_compaction_flushes(db)

    try:
        memory_ctx = await mem_store.format_for_prompt(db)
        history = await hist_store.get_history(db, room_id)
        schedule_ctx = await _format_schedules(db)
        sysinfo_ctx = sysinfo.get_system_info()
        checklist = _load_heartbeat_checklist()

        system = _HEARTBEAT_SYSTEM.format(datetime=now)
        context_parts = [system]
        if checklist:
            context_parts.append(checklist)
        if memory_ctx:
            context_parts.append(memory_ctx)
        if schedule_ctx:
            context_parts.append(schedule_ctx)
        if sysinfo_ctx:
            context_parts.append(sysinfo_ctx)
        system_with_ctx = "\n\n".join(context_parts)

        messages = [{"role": "system", "content": system_with_ctx}]
        if history:
            filtered_history = _filter_internal_probe_history(history)
            messages.extend(filtered_history[-10:])
        messages.append({"role": "user", "content": _HEARTBEAT_PROBE_MESSAGE})

        raw = await llm.chat(messages, agent_type="chat")
        action, parsed = _parse_action(raw)
        logger.info(f"[Heartbeat] Action: {action}")

        if not parsed:
            await _report_unstructured_heartbeat_output(db, room_id, raw)
            return

        if action["action"] == "none":
            return
        elif action["action"] == "message":
            content = action.get("content", "").strip()
            if content and not _is_internal_probe_echo(content):
                await messenger.send_message(room_id, content)
                await hist_store.add_message(db, room_id, "assistant", content)
            elif content:
                logger.warning("[Heartbeat] Ignoring leaked internal probe echo from model output.")
                notice = "🫀 Heartbeat 보고: 내부 프로브 문구가 감지되어 해당 출력은 차단했어요."
                await messenger.send_message(room_id, notice)
                await hist_store.add_message(db, room_id, "assistant", notice)
        elif action["action"] == "task":
            task_desc = action.get("content", "").strip()
            if task_desc:
                asyncio.create_task(_run_background_task(db, room_id, task_desc))
        elif action["action"] == "schedule":
            await _create_schedule(db, room_id, action)

    except Exception as exc:
        logger.error(f"[Heartbeat] Tick failed: {exc}", exc_info=True)


async def _create_schedule(db: aiosqlite.Connection, room_id: int, action: dict) -> None:
    """Create a scheduled job from an autonomous heartbeat decision."""
    name = action.get("name", "").strip()
    prompt = action.get("prompt", "").strip()
    cron = action.get("cron", "").strip()
    once_at = action.get("at", "").strip()

    if not name or not prompt or not (cron or once_at):
        logger.warning(f"[Heartbeat] Invalid schedule action: {action}")
        return

    job_id = await sched_store.add_job(db, name, room_id, prompt, cron=cron, once_at=once_at)
    logger.info(f"[Heartbeat] Autonomously created job #{job_id}: {name}")

    schedule_desc = f"cron={cron}" if cron else f"at={once_at}"
    await messenger.send_message(
        room_id,
        f"📋 새 예약 작업을 설정했어요: **{name}** ({schedule_desc})\n→ {prompt}",
    )
    await hist_store.add_message(
        db, room_id, "assistant", f"[Auto-scheduled] {name} ({schedule_desc}): {prompt}"
    )
    await status_file.refresh(db)


async def _run_background_task(db: aiosqlite.Connection, room_id: int, task_desc: str) -> None:
    """Execute a background task and report the result. Runs non-blocking via asyncio.create_task."""
    logger.info(f"[Heartbeat] Running background task: {task_desc}")
    await messenger.send_message(room_id, f"🔄 백그라운드 작업 시작: {task_desc}")

    try:
        system = _TASK_EXECUTOR_SYSTEM.format(task=task_desc)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_desc},
        ]
        result = await llm.chat(messages, agent_type="auto")
        reply = f"✅ 작업 완료: {task_desc}\n\n{result}"
    except Exception as exc:
        reply = f"❌ 작업 실패: {task_desc}\n\nError: {exc}"
        logger.error(f"[Heartbeat] Task failed: {exc}", exc_info=True)

    await messenger.send_message(room_id, reply)
    await hist_store.add_message(db, room_id, "assistant", reply)


async def _format_schedules(db: aiosqlite.Connection) -> str:
    """Format current scheduled jobs for heartbeat context."""
    jobs = await sched_store.list_jobs(db)
    if not jobs:
        return ""
    lines = ["## Current Scheduled Jobs\n"]
    for j in jobs:
        schedule = j["cron"] if j["cron"] else f"once at {j['once_at']}"
        lr = f", last ran {j['last_run'][:16]}" if j["last_run"] else ""
        lines.append(f"- #{j['id']} {j['name']}: {schedule} → {j['prompt']}{lr}")
    return "\n".join(lines)


async def _maybe_compaction_flushes(db: aiosqlite.Connection) -> None:
    """For rooms near history capacity, prompt LLM to save key memories before old messages are trimmed.

    Runs at most once per 4 hours per room (tracked via a _system memory entry).
    This prevents important context from being silently dropped when history overflows.
    """
    threshold = int(config.MAX_HISTORY_MESSAGES * config.COMPACTION_FLUSH_THRESHOLD)
    active_rooms = await hist_store.get_active_rooms(db)

    for room_id in active_rooms:
        count = await hist_store.get_count(db, room_id)
        if count < threshold:
            continue

        # Check if we flushed this room recently
        flush_key = f"_compaction_flush_{room_id}"
        last_ts = await mem_store.recall(db, flush_key)
        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)
                if datetime.now(timezone.utc) - last_dt < timedelta(hours=4):
                    continue  # Flushed within the last 4 hours
            except Exception:
                pass

        logger.info(f"[Heartbeat] Compaction flush for room {room_id} (history={count}/{config.MAX_HISTORY_MESSAGES})")
        history = await hist_store.get_history(db, room_id)
        soul = llm.load_soul()

        try:
            flush_messages = [
                {
                    "role": "system",
                    "content": (
                        soul + "\n\n"
                        "Your conversation history for this room is approaching its storage limit. "
                        "Older messages will soon be dropped. Review the recent conversation below "
                        "and save any important long-term facts, preferences, decisions, or context "
                        "using [MEMORY_SAVE: key=..., value=..., tags=...] commands. "
                        "Focus only on information worth keeping across sessions. "
                        "Do not save trivial or transient details."
                    ),
                },
                *history[-20:],
                {
                    "role": "user",
                    "content": "Save important memories before older messages are cleared.",
                },
            ]
            raw = await llm.chat(flush_messages, agent_type="chat")
            mem_commands = mem_store.parse_memory_commands(raw)
            for cmd in mem_commands:
                await mem_store.save(db, cmd["key"], cmd["value"], cmd["tags"])

            # Record flush timestamp as internal system memory
            now_iso = datetime.now(timezone.utc).isoformat()
            await mem_store.save(db, flush_key, now_iso, ["_system"])

            if mem_commands:
                logger.info(f"[Heartbeat] Compaction flush saved {len(mem_commands)} memories for room {room_id}")
                await status_file.refresh(db)
            else:
                logger.debug(f"[Heartbeat] Compaction flush for room {room_id}: nothing new to save")

        except Exception as exc:
            logger.error(f"[Heartbeat] Compaction flush failed for room {room_id}: {exc}", exc_info=True)


def _parse_action(raw: str) -> tuple[dict, bool]:
    """Extract the JSON action from the LLM response.

    Returns:
      (action, parsed_ok)
    """
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end]), True
        except json.JSONDecodeError:
            pass
    logger.warning(f"[Heartbeat] Could not parse action from: {raw!r}")
    return {"action": "none"}, False


def _normalize_text_for_compare(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _is_internal_probe_echo(content: str) -> bool:
    normalized = _normalize_text_for_compare(content)
    return normalized in {
        _normalize_text_for_compare(_HEARTBEAT_PROBE_MESSAGE),
        _normalize_text_for_compare(_LEGACY_HEARTBEAT_PROBE_MESSAGE),
    }


def _filter_internal_probe_history(history: list[dict]) -> list[dict]:
    """Remove leaked internal probe messages from context to prevent self-loops."""
    cleaned = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "assistant" and _is_internal_probe_echo(content):
            continue
        cleaned.append(msg)
    return cleaned


async def _report_unstructured_heartbeat_output(
    db: aiosqlite.Connection, room_id: int, raw_output: str
) -> None:
    """Report non-JSON heartbeat output to the user unless it is internal probe text."""
    content = raw_output.strip()
    if not content:
        return

    if _is_internal_probe_echo(content):
        notice = "🫀 Heartbeat 보고: 내부 프로브 응답만 감지되어 사용자 출력은 생략했어요."
        await messenger.send_message(room_id, notice)
        await hist_store.add_message(db, room_id, "assistant", notice)
        return

    max_len = max(200, config.MAX_MESSAGE_LENGTH - 100)
    if len(content) > max_len:
        content = content[:max_len].rstrip() + "\n...(truncated)"

    report = f"🫀 Heartbeat 보고:\n{content}"
    await messenger.send_message(room_id, report)
    await hist_store.add_message(db, room_id, "assistant", report)
