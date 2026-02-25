"""Async client for the LLM_API /v1/chat/completions endpoint."""
import json
import logging
from typing import Awaitable, Callable, Dict, List, Optional

import httpx
import config
from core.retry import with_retry

logger = logging.getLogger(__name__)


async def chat(
    messages: List[Dict[str, str]],
    agent_type: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout_seconds: float = 120,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    tools: Optional[List[Dict]] = None,
    tool_executor: Optional[Callable[[str, dict], Awaitable[str]]] = None,
) -> str:
    """
    Call LLM_API chat completions and return the assistant's reply text.

    If `tools` and `tool_executor` are provided, handles tool call responses
    transparently: executes each tool, appends results, then gets the final
    text response from the LLM. Callers always receive a plain string.

    The endpoint uses multipart/form-data with `messages` as a JSON string.
    See: LLM_API/backend/api/routes/chat.py
    """
    agent = agent_type or config.LLM_API_AGENT_TYPE

    body = await _api_call(
        messages, agent, session_id, timeout_seconds, max_attempts, base_delay, tools
    )
    choice = body["choices"][0]
    msg = choice["message"]
    finish_reason = choice.get("finish_reason", "stop")

    # --- Tool call loop (single round) ---
    if finish_reason == "tool_calls" and tool_executor and msg.get("tool_calls"):
        tool_calls = msg["tool_calls"]
        logger.info(f"[LLM] Tool calls requested: {[tc['function']['name'] for tc in tool_calls]}")

        # Build extended messages: original + assistant tool-call message + results
        extended = list(messages) + [msg]
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                logger.warning(f"[LLM] Could not parse tool args for {tool_name!r}")
                args = {}

            result = await tool_executor(tool_name, args)
            logger.debug(f"[LLM] Tool result for {tool_name!r}: {result!r}")
            extended.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        # Get final text response — no tools on follow-up to prevent infinite loops
        body = await _api_call(
            extended, agent, session_id, timeout_seconds, max_attempts, base_delay,
            tools=None,
        )
        msg = body["choices"][0]["message"]

    content = msg.get("content") or ""
    return content


async def _api_call(
    messages: List[Dict],
    agent: str,
    session_id: Optional[str],
    timeout_seconds: float,
    max_attempts: int,
    base_delay: float,
    tools: Optional[List[Dict]],
) -> dict:
    """Single HTTP call to the completions endpoint with retry."""
    form_data: dict = {
        "messages": json.dumps(messages),
        "agent_type": agent,
        "stream": "false",
    }
    if session_id:
        form_data["session_id"] = session_id
    if tools:
        form_data["tools"] = json.dumps(tools)

    endpoint = f"{config.LLM_API_URL}/v1/chat/completions"

    async def _call():
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            try:
                resp = await client.post(endpoint, data=form_data)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.warning(
                    f"[LLM] Request failed endpoint={endpoint} agent={agent} "
                    f"error={type(exc).__name__}: {exc}"
                )
                raise

    body = await with_retry(
        _call,
        label=f"LLM chat ({agent})",
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
    [system (SOUL + memory + skills + daily log), ...history, user]
    """
    from core import skills as skills_mod
    from core import daily_log

    system_parts = [soul]
    if memory_context:
        system_parts.append(memory_context)

    # Skills — loaded fresh each call so self-created skills appear immediately
    skills_ctx = skills_mod.load_skills()
    if skills_ctx:
        system_parts.append(skills_ctx)

    # Recent daily logs (today + yesterday) for narrative context
    log_ctx = daily_log.load_recent_logs()
    if log_ctx:
        system_parts.append(log_ctx)

    system_content = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
