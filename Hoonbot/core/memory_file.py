"""
File-based persistent memory store: data/memory.md
Internal state store: data/state.json

User memory is stored as Markdown bullet points (human-readable, directly
injected into the LLM system prompt). Internal state (compaction timestamps,
etc.) is stored in state.json.

Memory format:
    ## Persistent Memory

    - **key**: value [tag1,tag2]
    - **another_key**: another value
"""
import json
import os
import re
import logging
from datetime import datetime
from typing import List, Optional, Union

import config

logger = logging.getLogger(__name__)

_DATA_DIR = config.DATA_DIR
MEMORY_FILE_PATH = os.path.join(_DATA_DIR, "memory.md")
_STATE_FILE = os.path.join(_DATA_DIR, "state.json")

# Regex to parse one bullet line:
#   - **key** _(YYYY-MM-DD HH:MM)_: value [optional tags]
# Timestamp part is optional for backwards compatibility.
_LINE_RE = re.compile(
    r"^- \*\*(.+?)\*\*(?:\s+_\(([^)]+)\)_)?: (.+?)(?:\s+\[([^\]]*)\])?$"
)


# ---------------------------------------------------------------------------
# User memory API
# ---------------------------------------------------------------------------


def save(key: str, value: str, tags: Union[List[str], str] = "") -> None:
    """Upsert a key-value entry. Tags may be a list or a comma-separated string."""
    if isinstance(tags, list):
        tags_str = ",".join(t for t in tags if t)
    else:
        tags_str = tags or ""

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entries = _read_entries()
    entries[key] = {"value": value.strip(), "tags": tags_str, "ts": ts}
    _write_entries(entries)
    logger.info(f"[MemoryFile] Saved: {key!r} = {value!r}")


def delete(key: str) -> bool:
    """Remove an entry by key. Returns True if it existed."""
    entries = _read_entries()
    if key in entries:
        del entries[key]
        _write_entries(entries)
        logger.info(f"[MemoryFile] Deleted: {key!r}")
        return True
    logger.debug(f"[MemoryFile] Delete miss: {key!r}")
    return False


def load() -> str:
    """Return the full contents of memory.md for injection into the system prompt."""
    try:
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content if content else ""
    except FileNotFoundError:
        return ""


def list_all() -> List[dict]:
    """Return all entries as a list of dicts with keys: key, value, tags, ts."""
    entries = _read_entries()
    return [
        {"key": k, "value": v["value"], "tags": v["tags"], "ts": v.get("ts", "")}
        for k, v in entries.items()
    ]


# ---------------------------------------------------------------------------
# Internal state API (replaces SQLite _system memories)
# ---------------------------------------------------------------------------


def recall_state(key: str) -> Optional[str]:
    """Read an internal state value from state.json."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(key: str, value: str) -> None:
    """Write an internal state value to state.json."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state[key] = value
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_entries() -> dict:
    """Parse memory.md into an ordered dict {key: {value, tags, ts}}."""
    entries: dict = {}
    try:
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                m = _LINE_RE.match(line.strip())
                if m:
                    key = m.group(1).strip()
                    ts = (m.group(2) or "").strip()
                    value = m.group(3).strip()
                    tags = (m.group(4) or "").strip()
                    entries[key] = {"value": value, "tags": tags, "ts": ts}
    except FileNotFoundError:
        pass
    return entries


def _write_entries(entries: dict) -> None:
    """Write the entries dict back to memory.md."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    lines = ["## Persistent Memory\n"]
    for key, entry in entries.items():
        ts_part = f" _({entry['ts']})_" if entry.get("ts") else ""
        tag_part = f" [{entry['tags']}]" if entry.get("tags") else ""
        lines.append(f"- **{key}**{ts_part}: {entry['value']}{tag_part}")
    with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
