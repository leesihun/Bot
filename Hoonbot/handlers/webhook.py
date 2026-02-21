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
import logging

import aiosqlite
from fastapi import APIRouter, Request

import config
from core import history as hist_store
from core import llm
from core import memory as mem_store
from core import messenger

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared DB connection injected from hoonbot.py at startup
_db: aiosqlite.Connection = None


def set_db(db: aiosqlite.Connection) -> None:
    global _db
    _db = db


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

    # Process asynchronously — respond immediately to the webhook
    asyncio.create_task(process_message(room_id, content, sender_name))
    return {"ok": True}


async def process_message(room_id: int, content: str, sender_name: str) -> None:
    """Core message processing pipeline."""
    db = _db
    if db is None:
        logger.error("[Webhook] Database not initialized")
        return

    # 1. Typing indicator
    await messenger.send_typing(room_id)

    try:
        # 2. Load context
        soul = llm.load_soul()
        history = await hist_store.get_history(db, room_id)
        memory_ctx = await mem_store.format_for_prompt(db)

        # 3. Build message list and call LLM
        messages = llm.build_messages(soul, history, content, memory_ctx)
        raw_reply = await llm.chat(messages)

        # 4. Parse and execute memory commands embedded in the reply
        commands = mem_store.parse_memory_commands(raw_reply)
        for cmd in commands:
            await mem_store.save(db, cmd["key"], cmd["value"], cmd["tags"])
            logger.info(f"[Memory] Saved: {cmd['key']} = {cmd['value']}")

        # 5. Strip memory commands from the visible reply
        reply = mem_store.strip_memory_commands(raw_reply)
        if not reply:
            reply = "..."

        # 6. Persist the exchange
        await hist_store.add_message(db, room_id, "user", content)
        await hist_store.add_message(db, room_id, "assistant", reply)

        # 7. Send reply
        await messenger.send_message(room_id, reply)

    except Exception as exc:
        logger.error(f"[Webhook] process_message failed: {exc}", exc_info=True)
        try:
            await messenger.send_message(room_id, f"⚠️ Error: {exc}")
        except Exception:
            pass
    finally:
        await messenger.stop_typing(room_id)
