"""
Webhook handler — receives new_message events from Messenger and processes them.

Payload shape (from Messenger/server/src/services/webhook.ts):
{
  "event": "new_message",
  "roomId": 1,
  "timestamp": "...",
  "data": {
    "id": 42,
    "content": "Hello",
    "type": "text",
    "senderName": "Lee",
    "senderId": 3,
    ...
  }
}
"""
import asyncio
import json
import logging
import re

from fastapi import APIRouter, HTTPException, Request

import config
from core import history as hist_store
from core import llm
from core import memory as mem_store
from core import messenger
from core import scheduled as sched_store
from core import status_file
from core import context_file
from core import skills as skills_mod
from core import daily_log
from core import notify
from core import tools as tools_mod
from core import memory_file as mem_file

logger = logging.getLogger(__name__)
router = APIRouter()

# Per-room debounce: tracks pending tasks and last message timestamp
_room_debounce: dict = {}  # room_id -> {"task": asyncio.Task | None, "content": str, "sender": str}
_DEBOUNCE_SECONDS = 1.5  # Wait this long after last message before processing


@router.post("/webhook")
async def handle_webhook(request: Request):
    payload = await request.json()
    event = payload.get("event")

    if event != "new_message":
        return {"ok": True}

    data = payload.get("data", {})
    room_id = payload.get("roomId")
    content = data.get("content", "").strip()
    msg_type = data.get("type", "text")
    sender_name = data.get("senderName") or data.get("sender_name", "")
    is_bot = data.get("isBot") or data.get("is_bot", False)

    # Ignore non-text messages (images, files)
    if msg_type != "text":
        return {"ok": True}

    # Ignore empty messages
    if not content:
        return {"ok": True}

    # Ignore own messages and other bots
    if sender_name == config.MESSENGER_BOT_NAME or is_bot:
        return {"ok": True}

    # In non-home rooms (group chats), only respond when @mentioned
    is_home = room_id == config.MESSENGER_HOME_ROOM_ID
    mention_tag = f"@{config.MESSENGER_BOT_NAME}"
    if not is_home and mention_tag.lower() not in content.lower():
        return {"ok": True}

    # Strip the @mention from content before processing
    clean_content = content
    if not is_home:
        clean_content = re.sub(
            rf"@{re.escape(config.MESSENGER_BOT_NAME)}", "", content, flags=re.IGNORECASE
        ).strip()
        if not clean_content:
            return {"ok": True}

    # Debounce: if multiple messages arrive rapidly, wait and combine
    _schedule_debounced(room_id, clean_content, sender_name)
    return {"ok": True}


def _schedule_debounced(room_id: int, content: str, sender_name: str) -> None:
    """Cancel any pending debounce for this room and schedule a new one.
    Multiple messages within the debounce window are concatenated."""
    entry = _room_debounce.get(room_id)
    if entry and entry["task"] and not entry["task"].done():
        entry["task"].cancel()
        combined = entry["content"] + "\n" + content
    else:
        combined = content

    async def _debounce():
        await asyncio.sleep(_DEBOUNCE_SECONDS)
        final = _room_debounce.pop(room_id, None)
        if final:
            await process_message(room_id, final["content"], final["sender"])

    _room_debounce[room_id] = {
        "content": combined,
        "sender": sender_name,
        "task": asyncio.create_task(_debounce()),
    }


async def process_message(room_id: int, content: str, sender_name: str) -> None:
    """Core message processing pipeline."""
    # 1. Typing indicator
    await messenger.send_typing(room_id)

    try:
        # 2. Load context — memory.md (memories + daily logs) + context.md (time + sysinfo)
        soul = llm.load_soul()
        history = await hist_store.get_history(room_id)
        mem_ctx = await mem_store.format_for_prompt()
        live_ctx = await context_file.refresh()
        memory_ctx = "\n\n".join(p for p in [mem_ctx, live_ctx] if p)

        # 3. Build message list and call LLM with tool calling enabled
        messages = llm.build_messages(soul, history, content, memory_ctx)

        async def _tool_executor(tool_name: str, args: dict) -> str:
            return await tools_mod.execute(tool_name, args, room_id=room_id)

        raw_reply = await llm.chat(
            messages,
            tools=tools_mod.HOONBOT_TOOLS,
            tool_executor=_tool_executor,
        )

        # 4. Fallback: parse command tags in case LLM doesn't support tool calling.
        # Also handles skills/daily_log/notify which are not yet tools.
        mem_commands = mem_store.parse_memory_commands(raw_reply)
        for cmd in mem_commands:
            mem_file.save(cmd["key"], cmd["value"], cmd["tags"])
            logger.info(f"[Memory] Saved: {cmd['key']} = {cmd['value']}")

        # 4b. Parse and execute memory delete commands
        del_commands = mem_store.parse_memory_delete_commands(raw_reply)
        for key in del_commands:
            mem_file.delete(key)
            logger.info(f"[Memory] Deleted: {key}")

        # 4c. Parse and create scheduled jobs
        sched_commands = sched_store.parse_schedule_commands(raw_reply)
        for cmd in sched_commands:
            job_id = await sched_store.add_job(
                cmd["name"], room_id, cmd["prompt"],
                cron=cmd["cron"], once_at=cmd["once_at"],
            )
            logger.info(f"[Schedule] Created job #{job_id}: {cmd['name']}")

        # 4d. Parse and create new skills
        skill_commands = skills_mod.parse_skill_create_commands(raw_reply)
        for cmd in skill_commands:
            path = skills_mod.create_skill(cmd["name"], cmd["description"], cmd["instructions"])
            logger.info(f"[Skills] Created skill '{cmd['name']}' at {path}")

        # 4e. Parse and append daily log entries
        log_entries = daily_log.parse_daily_log_commands(raw_reply)
        for entry in log_entries:
            daily_log.append_entry(entry)

        # 4f. Parse and send desktop notifications
        notify_commands = notify.parse_notify_commands(raw_reply)
        for cmd in notify_commands:
            notify.send(cmd["title"], cmd["message"])

        # 4g. Refresh human-readable status file if anything changed
        if mem_commands or del_commands or sched_commands or skill_commands:
            await status_file.refresh()

        # 5. Strip all command tags from the visible reply
        reply = mem_store.strip_memory_commands(raw_reply)
        reply = mem_store.strip_memory_delete_commands(reply)
        reply = sched_store.strip_schedule_commands(reply)
        reply = skills_mod.strip_skill_create_commands(reply)
        reply = daily_log.strip_daily_log_commands(reply)
        reply = notify.strip_notify_commands(reply)
        if not reply:
            reply = "..."

        # 6. Persist the exchange
        await hist_store.add_message(room_id, "user", content)
        await hist_store.add_message(room_id, "assistant", reply)

        # 7. Send reply
        await messenger.send_message(room_id, reply)

    except Exception as exc:
        logger.error(f"[Webhook] process_message failed: {exc}", exc_info=True)
        logger.error(f"[Webhook] LLM endpoint in use: {config.LLM_API_URL}/v1/chat/completions")
        try:
            if "Connect" in type(exc).__name__ or "Timeout" in type(exc).__name__:
                user_msg = "⚠️ LLM 서버에 연결할 수 없어요. 잠시 후 다시 시도해주세요."
            else:
                user_msg = "⚠️ 응답을 생성하는 중 오류가 발생했어요. 잠시 후 다시 시도해주세요."
            await messenger.send_message(room_id, user_msg)
        except Exception:
            pass
    finally:
        await messenger.stop_typing(room_id)


@router.post("/webhook/incoming/{path:path}")
async def handle_incoming_webhook(path: str, request: Request):
    """Accept POST triggers from external services (GitHub, calendar, etc.)."""
    if config.WEBHOOK_INCOMING_SECRET:
        secret = request.headers.get("x-webhook-secret", "")
        if secret != config.WEBHOOK_INCOMING_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    source = path.strip("/") or "external"
    if "message" in payload:
        content = f"[Webhook from {source}] {payload['message']}"
    else:
        content = f"[Webhook from {source}] {json.dumps(payload, ensure_ascii=False, indent=2)}"

    room_id = config.MESSENGER_HOME_ROOM_ID
    logger.info(f"[Webhook] Incoming webhook from '{source}' → room {room_id}")
    _schedule_debounced(room_id, content, f"webhook:{source}")
    return {"ok": True}
