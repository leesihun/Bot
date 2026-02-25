"""Per-room conversation history backed by JSON files (data/history/room_{id}.json)."""
import json
import os
from datetime import datetime, timezone
from typing import Dict, List

import config

_HISTORY_DIR = os.path.join(os.path.dirname(config.DB_PATH), "history")


def _room_file(room_id: int) -> str:
    return os.path.join(_HISTORY_DIR, f"room_{room_id}.json")


def _read(room_id: int) -> List[Dict]:
    try:
        with open(_room_file(room_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(room_id: int, messages: List[Dict]) -> None:
    os.makedirs(_HISTORY_DIR, exist_ok=True)
    with open(_room_file(room_id), "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


async def add_message(room_id: int, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    messages = _read(room_id)
    messages.append({"role": role, "content": content, "timestamp": now})
    if len(messages) > config.MAX_HISTORY_MESSAGES:
        messages = messages[-config.MAX_HISTORY_MESSAGES:]
    _write(room_id, messages)


async def get_history(room_id: int) -> List[Dict[str, str]]:
    messages = _read(room_id)
    return [{"role": m["role"], "content": m["content"]} for m in messages[-config.MAX_HISTORY_MESSAGES:]]


async def clear_history(room_id: int) -> None:
    _write(room_id, [])


async def get_count(room_id: int) -> int:
    return len(_read(room_id))


async def get_active_rooms() -> List[int]:
    try:
        files = os.listdir(_HISTORY_DIR)
    except FileNotFoundError:
        return []
    rooms = []
    for f in files:
        if f.startswith("room_") and f.endswith(".json"):
            try:
                rooms.append(int(f[5:-5]))
            except ValueError:
                pass
    return rooms
