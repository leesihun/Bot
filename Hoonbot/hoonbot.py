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
from handlers.health import router as health_router
from handlers.webhook import router as webhook_router, set_db

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db

    # --- Database ---
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    _db = await aiosqlite.connect(config.DB_PATH)
    await _db.execute("PRAGMA journal_mode=WAL")
    await hist_store.init_history(_db)
    await mem_store.init_memory(_db)
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

    logger.info(f"[Hoonbot] Ready on port {config.HOONBOT_PORT}")
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
