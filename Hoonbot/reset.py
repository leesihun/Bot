#!/usr/bin/env python3
"""
Hoonbot Reset Utility

Reset persistent data (memory, conversation history, scheduled jobs, or everything).
Run while Hoonbot is STOPPED to avoid file conflicts.

All data is stored as plain files under data/:
  - data/memory.md          — persistent memory
  - data/history/room_*.json — per-room conversation history
  - data/schedules.json     — scheduled jobs
  - data/state.json         — internal state (compaction timestamps, etc.)
  - data/memory/*.md        — daily logs
  - data/status.md          — auto-generated status snapshot

Usage:
    python reset.py --all              # Reset everything
    python reset.py --memory           # Reset only persistent memory
    python reset.py --history          # Reset only conversation history
    python reset.py --history --room 1 # Reset history for a specific room
    python reset.py --schedules        # Reset only scheduled jobs
    python reset.py --daily-logs       # Reset only daily logs
    python reset.py --list-memory      # List all stored memories (read-only)
    python reset.py --list-schedules   # List all scheduled jobs (read-only)
"""
import argparse
import json
import os
import re
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.md")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")
HISTORY_DIR = os.path.join(DATA_DIR, "history")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
DAILY_LOGS_DIR = os.path.join(DATA_DIR, "memory")
STATUS_FILE = os.path.join(DATA_DIR, "status.md")

# Regex to parse memory.md lines:
#   - **key** _(YYYY-MM-DD HH:MM)_: value [optional tags]
_LINE_RE = re.compile(
    r"^- \*\*(.+?)\*\*(?:\s+_\(([^)]+)\)_)?: (.+?)(?:\s+\[([^\]]*)\])?$"
)


def list_memory():
    if not os.path.exists(MEMORY_FILE):
        print("No memories stored.")
        return
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    for line in lines:
        m = _LINE_RE.match(line.strip())
        if m:
            entries.append({
                "key": m.group(1).strip(),
                "ts": (m.group(2) or "").strip(),
                "value": m.group(3).strip(),
                "tags": (m.group(4) or "").strip(),
            })

    if not entries:
        print("No memories stored.")
        return

    print(f"\n{'Key':<30} {'Value':<40} {'Tags':<20} {'Updated'}")
    print("-" * 110)
    for e in entries:
        print(f"{e['key']:<30} {e['value']:<40} {e['tags']:<20} {e['ts']}")
    print(f"\nTotal: {len(entries)} memories")


def list_schedules():
    if not os.path.exists(SCHEDULES_FILE):
        print("No scheduled jobs.")
        return
    try:
        with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("No scheduled jobs (or file is corrupted).")
        return

    if not jobs:
        print("No scheduled jobs.")
        return

    print(f"\n{'ID':<5} {'Name':<25} {'Cron/At':<20} {'Room':<6} {'Enabled':<8} {'Prompt'}")
    print("-" * 100)
    for j in jobs:
        schedule = j.get("cron") or j.get("once_at") or "?"
        status = "yes" if j.get("enabled", True) else "no"
        prompt = j.get("prompt", "")[:40]
        print(f"{j['id']:<5} {j['name']:<25} {schedule:<20} {j['room_id']:<6} {status:<8} {prompt}")
    print(f"\nTotal: {len(jobs)} jobs")


def reset_memory():
    if os.path.exists(MEMORY_FILE):
        os.remove(MEMORY_FILE)
    print("All memories deleted.")


def reset_history(room_id=None):
    if not os.path.isdir(HISTORY_DIR):
        print("No conversation history.")
        return

    if room_id is not None:
        path = os.path.join(HISTORY_DIR, f"room_{room_id}.json")
        if os.path.exists(path):
            os.remove(path)
            print(f"Conversation history for room {room_id} deleted.")
        else:
            print(f"No history found for room {room_id}.")
    else:
        count = 0
        for f in os.listdir(HISTORY_DIR):
            if f.startswith("room_") and f.endswith(".json"):
                os.remove(os.path.join(HISTORY_DIR, f))
                count += 1
        print(f"All conversation history deleted ({count} room(s)).")


def reset_schedules():
    if os.path.exists(SCHEDULES_FILE):
        os.remove(SCHEDULES_FILE)
    print("All scheduled jobs deleted.")


def reset_daily_logs():
    if not os.path.isdir(DAILY_LOGS_DIR):
        print("No daily logs.")
        return
    count = 0
    for f in os.listdir(DAILY_LOGS_DIR):
        if f.endswith(".md"):
            os.remove(os.path.join(DAILY_LOGS_DIR, f))
            count += 1
    print(f"All daily logs deleted ({count} file(s)).")


def reset_all():
    reset_memory()
    reset_history()
    reset_schedules()
    reset_daily_logs()
    # Also clean internal state and status snapshot
    for path in [STATE_FILE, STATUS_FILE]:
        if os.path.exists(path):
            os.remove(path)
    print("\nAll Hoonbot data has been reset.")


def main():
    parser = argparse.ArgumentParser(
        description="Hoonbot Reset Utility - manage persistent data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python reset.py --all              Reset everything
  python reset.py --memory           Clear all memories
  python reset.py --history          Clear all conversation history
  python reset.py --history --room 1 Clear history for room 1 only
  python reset.py --schedules        Clear all scheduled jobs
  python reset.py --daily-logs       Clear all daily logs
  python reset.py --list-memory      View stored memories
  python reset.py --list-schedules   View scheduled jobs

Data directory: {DATA_DIR}
        """,
    )
    parser.add_argument("--all", action="store_true", help="Reset everything")
    parser.add_argument("--memory", action="store_true", help="Reset persistent memory")
    parser.add_argument("--history", action="store_true", help="Reset conversation history")
    parser.add_argument("--schedules", action="store_true", help="Reset scheduled jobs")
    parser.add_argument("--daily-logs", action="store_true", help="Reset daily logs")
    parser.add_argument("--room", type=int, help="Specific room ID (use with --history)")
    parser.add_argument("--list-memory", action="store_true", help="List all memories")
    parser.add_argument("--list-schedules", action="store_true", help="List all scheduled jobs")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if not any([args.all, args.memory, args.history, args.schedules,
                args.daily_logs, args.list_memory, args.list_schedules]):
        parser.print_help()
        sys.exit(0)

    # Read-only operations
    if args.list_memory:
        list_memory()
        if not any([args.all, args.memory, args.history, args.schedules, args.daily_logs]):
            return

    if args.list_schedules:
        list_schedules()
        if not any([args.all, args.memory, args.history, args.schedules, args.daily_logs]):
            return

    # Destructive operations - confirm first
    actions = []
    if args.all:
        actions.append("ALL data (memory + history + schedules + daily logs + state)")
    else:
        if args.memory:
            actions.append("persistent memory")
        if args.history:
            if args.room is not None:
                actions.append(f"conversation history (room {args.room})")
            else:
                actions.append("all conversation history")
        if args.schedules:
            actions.append("scheduled jobs")
        if args.daily_logs:
            actions.append("daily logs")

    if actions:
        if not args.yes:
            print(f"\nThis will DELETE: {', '.join(actions)}")
            confirm = input("Are you sure? [y/N] ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return

        if args.all:
            reset_all()
        else:
            if args.memory:
                reset_memory()
            if args.history:
                reset_history(args.room)
            if args.schedules:
                reset_schedules()
            if args.daily_logs:
                reset_daily_logs()


if __name__ == "__main__":
    main()
