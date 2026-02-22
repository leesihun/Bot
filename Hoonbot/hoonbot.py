"""
Hoonbot — entry point.

Startup sequence:
1. Initialize SQLite database (create tables)
2. Register bot with Messenger (get / restore API key)
3. Register webhook subscription
4. Start heartbeat scheduler
5. Serve FastAPI on HOONBOT_PORT
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

import aiosqlite
import uvicorn
from fastapi import FastAPI

import config
from core import history as hist_store
from core import memory as mem_store
from core import messenger
from core import scheduler
from core import heartbeat
from core import scheduled as sched_store
from core import status_file
from handlers.health import router as health_router
from handlers.webhook import router as webhook_router, set_db, process_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hoonbot")

# Shared DB — opened once and reused across all requests
_db: aiosqlite.Connection = None

# Key storage file so we survive restarts without re-registering
_KEY_FILE = os.path.join(os.path.dirname(__file__), "data", ".apikey")


def _load_saved_key() -> str:
    try:
        with open(_KEY_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _save_key(key: str) -> None:
    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    with open(_KEY_FILE, "w") as f:
        f.write(key)


async def _catch_up(db: aiosqlite.Connection) -> None:
    """
    On startup, find the last unanswered human message in each room Hoonbot
    belongs to and process it — handles messages sent while Hoonbot was offline.
    """
    bot_info = await messenger.get_bot_info()
    if not bot_info:
        logger.warning("[CatchUp] Could not get bot info, skipping")
        return

    bot_id = bot_info["id"]
    rooms = await messenger.get_rooms(bot_id)
    logger.info(f"[CatchUp] Scanning {len(rooms)} room(s) for missed messages")

    for room in rooms:
        room_id = room["id"]
        messages = await messenger.get_room_messages(room_id, limit=20)
        if not messages:
            continue

        # Find the last human message and whether Hoonbot replied after it
        last_human_idx = -1
        for i, msg in enumerate(messages):
            if (
                msg.get("senderName") != config.MESSENGER_BOT_NAME
                and not msg.get("isBot")
                and msg.get("type") == "text"
                and msg.get("content", "").strip()
            ):
                last_human_idx = i

        if last_human_idx == -1:
            continue  # No human messages

        # Did Hoonbot already reply after the last human message?
        hoonbot_replied = any(
            msg.get("senderName") == config.MESSENGER_BOT_NAME
            for msg in messages[last_human_idx + 1:]
        )
        if hoonbot_replied:
            continue

        missed = messages[last_human_idx]
        content = missed.get("content", "").strip()
        sender = missed.get("senderName", "unknown")
        logger.info(f"[CatchUp] Room {room_id}: missed msg from {sender!r}: {content[:50]!r}")
        await process_message(room_id, content, sender)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db

    # --- Database ---
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    _db = await aiosqlite.connect(config.DB_PATH)
    await _db.execute("PRAGMA journal_mode=WAL")
    await hist_store.init_history(_db)
    await mem_store.init_memory(_db)
    await sched_store.init_scheduled(_db)
    set_db(_db)
    logger.info(f"[DB] Opened: {config.DB_PATH}")

    # --- Bot registration ---
    saved_key = _load_saved_key()
    if saved_key:
        messenger.set_api_key(saved_key)
        logger.info("[Messenger] Restored API key from disk")
    else:
        key = await messenger.register_bot(config.MESSENGER_BOT_NAME)
        messenger.set_api_key(key)
        _save_key(key)
        logger.info("[Messenger] Bot registered and key saved")

    # --- Webhook subscription ---
    webhook_url = f"http://localhost:{config.HOONBOT_PORT}/webhook"
    await messenger.register_webhook(webhook_url, ["new_message"])

    # --- Heartbeat ---
    if config.HEARTBEAT_ENABLED:
        async def _tick():
            await heartbeat.tick(_db)

        scheduler.start()
        scheduler.add_interval_job(_tick, config.HEARTBEAT_INTERVAL_SECONDS, "heartbeat")
        logger.info(f"[Heartbeat] Enabled, interval={config.HEARTBEAT_INTERVAL_SECONDS}s")
    else:
        logger.info("[Heartbeat] Disabled")

    # --- Initial status snapshot ---
    await status_file.refresh(_db)

    logger.info(f"[Hoonbot] Ready on port {config.HOONBOT_PORT}")

    # --- Catch up on missed messages ---
    asyncio.create_task(_catch_up(_db))

    yield

    # --- Shutdown ---
    scheduler.shutdown()
    await _db.close()
    logger.info("[Hoonbot] Shutdown complete")


app = FastAPI(title="Hoonbot", lifespan=lifespan)
app.include_router(health_router)
app.include_router(webhook_router)


if __name__ == "__main__":
    uvicorn.run(
        "hoonbot:app",
        host=config.HOONBOT_HOST,
        port=config.HOONBOT_PORT,
        reload=False,
    )
