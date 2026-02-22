"""Desktop notifications via plyer.

Sends OS-level notifications when Hoonbot wants the user's attention
outside of the Messenger UI (e.g., urgent heartbeat alerts).

The LLM can trigger a notification by emitting:
    [NOTIFY: title=Alert Title, message=The notification body text]

Can be disabled via HOONBOT_NOTIFICATIONS=false.
"""
import re
import logging
from typing import List, Dict

import config

logger = logging.getLogger(__name__)


def send(title: str, message: str) -> None:
    """Send a desktop notification. No-ops silently if disabled or unavailable."""
    if not config.NOTIFICATIONS_ENABLED:
        return
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Hoonbot",
            timeout=10,
        )
        logger.info(f"[Notify] Sent: {title!r}")
    except Exception as e:
        logger.debug(f"[Notify] Unavailable (install plyer?): {e}")


def parse_notify_commands(text: str) -> List[Dict]:
    """Extract [NOTIFY: title=..., message=...] commands from LLM output."""
    pattern = r"\[NOTIFY:\s*title=([^,\]]+),\s*message=([^\]]+)\]"
    commands = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        commands.append({
            "title": m.group(1).strip(),
            "message": m.group(2).strip(),
        })
    return commands


def strip_notify_commands(text: str) -> str:
    """Remove [NOTIFY: ...] commands from text before sending to user."""
    pattern = r"\[NOTIFY:[^\]]*\]\n?"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
