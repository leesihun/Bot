"""Async client for the LLM_API /v1/chat/completions endpoint."""
import json
import logging
from typing import List, Dict, Optional

import httpx
import config

logger = logging.getLogger(__name__)


async def chat(
    messages: List[Dict[str, str]],
    agent_type: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Call LLM_API chat completions and return the assistant's reply text.

    The endpoint uses multipart/form-data with `messages` as a JSON string.
    See: LLM_API/backend/api/routes/chat.py
    """
    agent = agent_type or config.LLM_API_AGENT_TYPE

    form_data = {
        "messages": json.dumps(messages),
        "agent_type": agent,
        "stream": "false",
    }
    if session_id:
        form_data["session_id"] = session_id

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{config.LLM_API_URL}/v1/chat/completions",
            data=form_data,
        )
        resp.raise_for_status()
        body = resp.json()

    # OpenAI-compatible response shape
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        logger.error(f"[LLM] Unexpected response shape: {body}")
        raise ValueError(f"Unexpected LLM response: {body}") from exc

    return content


def load_soul() -> str:
    """Read SOUL.md and return its contents as a string."""
    try:
        with open(config.SOUL_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"[LLM] SOUL.md not found at {config.SOUL_PATH}")
        return "You are Hoonbot, a helpful personal AI assistant."


def build_messages(
    soul: str,
    history: List[Dict[str, str]],
    user_content: str,
    memory_context: str = "",
) -> List[Dict[str, str]]:
    """
    Assemble the full messages list:
    [system (SOUL + memory), ...history, user]
    """
    system_parts = [soul]
    if memory_context:
        system_parts.append(memory_context)
    system_content = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
