"""Async client for the LLM_API /v1/chat/completions endpoint."""
import json
import logging
from typing import Dict, List, Optional

import httpx
import config
from core.retry import with_retry

logger = logging.getLogger(__name__)


async def chat(
    messages: List[Dict[str, str]],
    session_id: Optional[str] = None,
    timeout_seconds: float = 120,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> str:
    """
    Call LLM_API chat completions and return the assistant's reply text.

    Tools are handled server-side by LLM_API_fast's agent loop.
    The endpoint uses multipart/form-data with `messages` as a JSON string.
    See: LLM_API_fast/backend/api/routes/chat.py
    """
    body = await _api_call(
        messages, session_id, timeout_seconds, max_attempts, base_delay
    )
    msg = body["choices"][0]["message"]
    return msg.get("content") or ""


async def _api_call(
    messages: List[Dict],
    session_id: Optional[str],
    timeout_seconds: float,
    max_attempts: int,
    base_delay: float,
) -> dict:
    """Single HTTP call to the completions endpoint with retry."""
    form_data: dict = {
        "messages": json.dumps(messages),
        "stream": "false",
    }
    if session_id:
        form_data["session_id"] = session_id

    endpoint = f"{config.LLM_API_URL}/v1/chat/completions"

    async def _call():
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            try:
                resp = await client.post(endpoint, data=form_data)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.warning(
                    f"[LLM] Request failed endpoint={endpoint} "
                    f"error={type(exc).__name__}: {exc}"
                )
                raise

    body = await with_retry(
        _call,
        label="LLM chat",
        max_attempts=max_attempts,
        base_delay=base_delay,
    )

    try:
        _ = body["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        logger.error(f"[LLM] Unexpected response shape: {body}")
        raise ValueError(f"Unexpected LLM response: {body}") from exc

    return body


def load_soul() -> str:
    """Read SOUL.md and return its contents as a string.

    Replaces {HOONBOT_DATA_DIR} with the actual absolute path of Hoonbot's
    data/ directory so SOUL.md stays portable across installations.
    """
    try:
        with open(config.SOUL_PATH, "r", encoding="utf-8") as f:
            soul = f.read().strip()
        # Forward-slash path works on both Windows and Linux for the LLM's benefit
        data_dir = str(config.DATA_DIR).replace("\\", "/")
        return soul.replace("{HOONBOT_DATA_DIR}", data_dir)
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
    [system (SOUL + memory_context + skills), ...history, user]

    memory_context should contain both the persistent memory (memory.md)
    and the live context (context.md) — assembled by the caller.
    """
    from core import skills as skills_mod

    system_parts = [soul]
    if memory_context:
        system_parts.append(memory_context)

    # Skills — loaded fresh each call so self-created skills appear immediately
    skills_ctx = skills_mod.load_skills()
    if skills_ctx:
        system_parts.append(skills_ctx)

    system_content = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
