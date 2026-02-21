"""Async client for the Huni Messenger bot API."""
import logging
from typing import List, Optional

import httpx
import config

logger = logging.getLogger(__name__)

# Runtime state — populated during startup
_api_key: str = ""
_bot_id: Optional[int] = None


def set_api_key(key: str) -> None:
    global _api_key
    _api_key = key
    config.MESSENGER_API_KEY = key


def get_api_key() -> str:
    return _api_key


def _headers() -> dict:
    return {"x-api-key": _api_key, "Content-Type": "application/json"}


async def register_bot(name: str) -> str:
    """
    Register Hoonbot with Messenger and return its API key.
    If a bot with this name already exists, Messenger returns its existing key.
    """
    global _bot_id
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{config.MESSENGER_URL}/api/bots",
            json={"name": name},
        )
        resp.raise_for_status()
        data = resp.json()
        key = data.get("apiKey") or data.get("key") or data.get("api_key", "")
        _bot_id = data.get("bot", {}).get("id") or data.get("id")
        logger.info(f"[Messenger] Bot registered: {name} (id={_bot_id})")
        return key


async def register_webhook(url: str, events: List[str]) -> None:
    """Subscribe to Messenger events. Idempotent — existing webhooks with same URL are reused."""
    async with httpx.AsyncClient(timeout=10) as client:
        # Check existing webhooks first
        resp = await client.get(
            f"{config.MESSENGER_URL}/api/webhooks",
            headers=_headers(),
        )
        if resp.status_code == 200:
            existing = resp.json()
            for wh in existing:
                if wh.get("url") == url:
                    logger.info(f"[Messenger] Webhook already registered: {url}")
                    return

        # Register new webhook (room_id omitted = all rooms)
        resp = await client.post(
            f"{config.MESSENGER_URL}/api/webhooks",
            headers=_headers(),
            json={"url": url, "events": events},
        )
        resp.raise_for_status()
        logger.info(f"[Messenger] Webhook registered: {url} for events={events}")


async def send_message(room_id: int, content: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{config.MESSENGER_URL}/api/send-message",
            headers=_headers(),
            json={"roomId": room_id, "content": content, "type": "text"},
        )
        resp.raise_for_status()


async def send_typing(room_id: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{config.MESSENGER_URL}/api/typing",
                headers=_headers(),
                json={"roomId": room_id},
            )
    except Exception:
        pass  # Typing indicators are best-effort


async def stop_typing(room_id: int) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{config.MESSENGER_URL}/api/stop-typing",
                headers=_headers(),
                json={"roomId": room_id},
            )
    except Exception:
        pass


async def get_bot_info() -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{config.MESSENGER_URL}/api/bots/me",
                headers=_headers(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None
