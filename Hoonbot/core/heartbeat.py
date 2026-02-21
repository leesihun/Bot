"""
Heartbeat: periodic proactive reasoning loop.

On each tick, Hoonbot loads its memory and recent history, asks the LLM
"what should I proactively do right now?", and acts on the response.
"""
import json
import logging
from datetime import datetime, timezone

import aiosqlite
import config
from core import llm, messenger, memory as mem_store, history as hist_store

logger = logging.getLogger(__name__)

_HEARTBEAT_SYSTEM = """\
You are Hoonbot running an autonomous background tick. It is now {datetime}.

Below is everything you know about the user (persistent memory) and recent conversation context.
Decide if there is anything genuinely useful to do proactively RIGHT NOW.

Consider:
- Are there any reminders or time-sensitive things you know about?
- Is there a helpful check-in, update, or piece of information worth sending?
- Is there a background task that should be started?
- Or is nothing needed (most common case)?

Respond ONLY with a single JSON object — no prose before or after:
  {{"action": "none"}}
  {{"action": "message", "content": "<message to send>"}}
  {{"action": "task", "content": "<description of task to run>"}}

Be conservative — only act when there is genuine value. Prefer "none".
"""

_TASK_EXECUTOR_SYSTEM = """\
You are Hoonbot executing a background task. Complete the following task and return a concise
summary of the result. Use your tools (web search, code execution, etc.) as needed.

Task: {task}
"""


async def tick(db: aiosqlite.Connection) -> None:
    """Single heartbeat tick: reason over memory → decide → execute."""
    if not config.HEARTBEAT_ENABLED:
        return

    room_id = config.MESSENGER_HOME_ROOM_ID
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"[Heartbeat] Tick at {now}")

    try:
        # Build context
        memory_ctx = await mem_store.format_for_prompt(db)
        history = await hist_store.get_history(db, room_id)

        # Build reasoning prompt
        system = _HEARTBEAT_SYSTEM.format(datetime=now)
        system_with_memory = f"{system}\n\n{memory_ctx}" if memory_ctx else system

        messages = [{"role": "system", "content": system_with_memory}]
        if history:
            # Include last few exchanges as context
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": "What should you do right now?"})

        raw = await llm.chat(messages, agent_type="chat")  # Use simple chat for the decision

        # Parse the JSON action
        action = _parse_action(raw)
        logger.info(f"[Heartbeat] Action: {action}")

        if action["action"] == "none":
            return

        elif action["action"] == "message":
            content = action.get("content", "").strip()
            if content:
                await messenger.send_message(room_id, content)
                await hist_store.add_message(db, room_id, "assistant", content)

        elif action["action"] == "task":
            task_desc = action.get("content", "").strip()
            if task_desc:
                await _run_background_task(db, room_id, task_desc)

    except Exception as exc:
        logger.error(f"[Heartbeat] Tick failed: {exc}", exc_info=True)


async def _run_background_task(db: aiosqlite.Connection, room_id: int, task_desc: str) -> None:
    """Execute a background task and report the result to the home room."""
    logger.info(f"[Heartbeat] Running background task: {task_desc}")
    await messenger.send_message(room_id, f"🔄 Starting background task: {task_desc}")

    try:
        system = _TASK_EXECUTOR_SYSTEM.format(task=task_desc)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_desc},
        ]
        result = await llm.chat(messages, agent_type="auto")
        reply = f"✅ Task complete: {task_desc}\n\n{result}"
    except Exception as exc:
        reply = f"❌ Task failed: {task_desc}\n\nError: {exc}"
        logger.error(f"[Heartbeat] Task failed: {exc}", exc_info=True)

    await messenger.send_message(room_id, reply)
    await hist_store.add_message(db, room_id, "assistant", reply)


def _parse_action(raw: str) -> dict:
    """Extract the JSON action from the LLM response."""
    raw = raw.strip()
    # Find first JSON object in the response
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    logger.warning(f"[Heartbeat] Could not parse action from: {raw!r}")
    return {"action": "none"}
