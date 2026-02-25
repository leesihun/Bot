"""
LLM tool definitions (OpenAI function-calling format) and executor.

Tools give the LLM a reliable, structured way to persist memory and create
schedules. Memory is stored in data/memory.md, schedules in data/schedules.json.
No SQLite involved.

Usage in callers:
    from core import tools as tools_mod

    async def my_executor(tool_name: str, args: dict) -> str:
        return await tools_mod.execute(tool_name, args, room_id=room_id)

    reply = await llm.chat(messages, tools=tools_mod.HOONBOT_TOOLS, tool_executor=my_executor)
"""
import logging
from typing import Any, Dict, List, Optional

import config
from core import memory_file as mem_file
from core import scheduled as sched_store
from core import status_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

HOONBOT_TOOLS: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "중요한 정보를 영구 메모리(data/memory.md)에 저장합니다. "
                "저장 시 현재 시각이 자동으로 기록됩니다. "
                "사용자의 이름, 선호도, 진행 중인 프로젝트, 반복적으로 참조하는 사실 등을 기억할 때 사용하세요. "
                "같은 key가 이미 존재하면 덮어쓰고 타임스탬프도 갱신됩니다. "
                "언제든지 저장할 게 있으면 즉시 호출하세요 — 대화가 끝나면 컨텍스트가 사라집니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "메모리의 고유 식별자. "
                            "영문 소문자와 언더스코어만 사용. "
                            "예: user_name, prefers_dark_mode, project_hoonbot_status"
                        ),
                    },
                    "value": {
                        "type": "string",
                        "description": "저장할 내용. 자유 형식으로 작성.",
                    },
                    "tags": {
                        "type": "string",
                        "description": (
                            "분류 태그. 쉼표로 구분. 선택사항. "
                            "예: personal, preferences, work, project"
                        ),
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": (
                "더 이상 유효하지 않거나 잘못된 메모리 항목을 삭제합니다. "
                "오래되거나 덮어써야 하는 기존 정보를 지울 때 사용하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "삭제할 메모리의 key",
                    },
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_schedule",
            "description": (
                "반복 또는 일회성 예약 작업을 만듭니다. "
                "사용자가 알림, 정기 보고, 리마인더를 요청할 때 사용하세요. "
                "호출 전에 컨텍스트의 기존 스케줄 목록을 확인해 중복을 피하세요. "
                "cron(반복)과 once_at(일회성) 중 반드시 하나를 지정해야 합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "작업 이름. 영문 소문자와 언더스코어. "
                            "예: morning_briefing, weekly_review, meeting_reminder"
                        ),
                    },
                    "prompt": {
                        "type": "string",
                        "description": "이 시각에 실행할 작업 설명. 예: '오늘의 일정과 날씨를 요약해줘'",
                    },
                    "cron": {
                        "type": "string",
                        "description": (
                            "반복 실행 시간. HH:MM (24h) 또는 5-field cron 표현식. "
                            "예: 09:00, 0 9 * * 1-5"
                        ),
                    },
                    "once_at": {
                        "type": "string",
                        "description": (
                            "일회성 실행 시각. YYYY-MM-DD HH:MM 형식. "
                            "예: 2026-03-01 14:00"
                        ),
                    },
                },
                "required": ["name", "prompt"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


async def execute(
    tool_name: str,
    args: Dict[str, Any],
    room_id: Optional[int] = None,
) -> str:
    """Execute a named tool call. Returns a result string sent back to the LLM."""
    try:
        if tool_name == "save_memory":
            return _save_memory(args)
        elif tool_name == "delete_memory":
            return _delete_memory(args)
        elif tool_name == "create_schedule":
            return await _create_schedule(args, room_id)
        else:
            logger.warning(f"[Tool] Unknown tool called: {tool_name!r}")
            return f"알 수 없는 도구: {tool_name}"
    except Exception as exc:
        logger.error(f"[Tool] {tool_name} failed: {exc}", exc_info=True)
        return f"오류 발생: {exc}"


def _save_memory(args: Dict[str, Any]) -> str:
    key = args["key"].strip()
    value = args["value"].strip()
    tags = args.get("tags", "")
    mem_file.save(key, value, tags)
    return f"저장 완료: {key} = {value}"


def _delete_memory(args: Dict[str, Any]) -> str:
    key = args["key"].strip()
    deleted = mem_file.delete(key)
    return f"삭제 완료: {key}" if deleted else f"키를 찾을 수 없음: {key}"


async def _create_schedule(
    args: Dict[str, Any],
    room_id: Optional[int] = None,
) -> str:
    name = args["name"].strip()
    prompt_text = args["prompt"].strip()
    cron = (args.get("cron") or "").strip() or None
    once_at = (args.get("once_at") or "").strip() or None

    if not cron and not once_at:
        return "오류: cron 또는 once_at 중 하나를 반드시 지정해야 합니다."

    rid = room_id if room_id is not None else config.MESSENGER_HOME_ROOM_ID
    job_id = await sched_store.add_job(name, rid, prompt_text, cron=cron, once_at=once_at)
    await status_file.refresh()
    logger.info(f"[Tool] create_schedule: {name!r} #{job_id}")

    schedule_desc = f"매일 {cron}" if cron else f"{once_at}에 1회"
    return f"예약 완료: {name} ({schedule_desc}) — #{job_id}"
