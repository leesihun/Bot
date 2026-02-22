#!/usr/bin/env python3
"""
Hoonbot Reset Utility

Reset persistent data (memory, conversation history, scheduled jobs, or everything).
Run while Hoonbot is STOPPED to avoid database conflicts.

Usage:
    python reset.py --all              # Reset everything (memory + history + schedules)
    python reset.py --memory           # Reset only persistent memory
    python reset.py --history          # Reset only conversation history
    python reset.py --history --room 1 # Reset history for a specific room
    python reset.py --schedules        # Reset only scheduled jobs
    python reset.py --list-memory      # List all stored memories (read-only)
    python reset.py --list-schedules   # List all scheduled jobs (read-only)
"""
import argparse
import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "hoonbot.db")


def get_db():
    if not os.path.exists(DB_PATH):
        print(f"Database not found: {DB_PATH}")
        print("Hoonbot has not been run yet or data directory is missing.")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def list_memory(db):
    cur = db.execute("SELECT key, value, tags, updated_at FROM memory ORDER BY key")
    rows = cur.fetchall()
    if not rows:
        print("No memories stored.")
        return
    print(f"\n{'Key':<30} {'Value':<40} {'Tags':<20} {'Updated'}")
    print("-" * 110)
    for key, value, tags, updated in rows:
        print(f"{key:<30} {value:<40} {tags:<20} {updated}")
    print(f"\nTotal: {len(rows)} memories")


def list_schedules(db):
    try:
        cur = db.execute(
            "SELECT id, name, cron, once_at, room_id, prompt, enabled, last_run FROM scheduled_jobs ORDER BY id"
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        print("No scheduled_jobs table yet (run Hoonbot at least once first).")
        return
    if not rows:
        print("No scheduled jobs.")
        return
    print(f"\n{'ID':<5} {'Name':<25} {'Cron/At':<20} {'Room':<6} {'Enabled':<8} {'Prompt'}")
    print("-" * 100)
    for id_, name, cron, once_at, room_id, prompt, enabled, last_run in rows:
        schedule = cron or once_at or "?"
        status = "yes" if enabled else "no"
        print(f"{id_:<5} {name:<25} {schedule:<20} {room_id:<6} {status:<8} {prompt[:40]}")
    print(f"\nTotal: {len(rows)} jobs")


def reset_memory(db):
    db.execute("DELETE FROM memory")
    # Rebuild FTS index
    try:
        db.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
    except Exception:
        pass
    db.commit()
    print("All memories deleted.")


def reset_history(db, room_id=None):
    if room_id is not None:
        db.execute("DELETE FROM room_history WHERE room_id = ?", (room_id,))
        db.commit()
        print(f"Conversation history for room {room_id} deleted.")
    else:
        db.execute("DELETE FROM room_history")
        db.commit()
        print("All conversation history deleted.")


def reset_schedules(db):
    try:
        db.execute("DELETE FROM scheduled_jobs")
        db.commit()
        print("All scheduled jobs deleted.")
    except sqlite3.OperationalError:
        print("No scheduled_jobs table yet (nothing to reset).")


def reset_all(db):
    reset_memory(db)
    reset_history(db)
    reset_schedules(db)
    print("\nAll Hoonbot data has been reset.")


def main():
    parser = argparse.ArgumentParser(
        description="Hoonbot Reset Utility - manage persistent data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset.py --all              Reset everything
  python reset.py --memory           Clear all memories
  python reset.py --history          Clear all conversation history
  python reset.py --history --room 1 Clear history for room 1 only
  python reset.py --schedules        Clear all scheduled jobs
  python reset.py --list-memory      View stored memories
  python reset.py --list-schedules   View scheduled jobs

Database location: %(db_path)s
        """ % {"db_path": DB_PATH},
    )
    parser.add_argument("--all", action="store_true", help="Reset everything")
    parser.add_argument("--memory", action="store_true", help="Reset persistent memory")
    parser.add_argument("--history", action="store_true", help="Reset conversation history")
    parser.add_argument("--schedules", action="store_true", help="Reset scheduled jobs")
    parser.add_argument("--room", type=int, help="Specific room ID (use with --history)")
    parser.add_argument("--list-memory", action="store_true", help="List all memories")
    parser.add_argument("--list-schedules", action="store_true", help="List all scheduled jobs")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if not any([args.all, args.memory, args.history, args.schedules, args.list_memory, args.list_schedules]):
        parser.print_help()
        sys.exit(0)

    db = get_db()

    # Read-only operations
    if args.list_memory:
        list_memory(db)
        if not any([args.all, args.memory, args.history, args.schedules]):
            db.close()
            return

    if args.list_schedules:
        list_schedules(db)
        if not any([args.all, args.memory, args.history, args.schedules]):
            db.close()
            return

    # Destructive operations - confirm first
    actions = []
    if args.all:
        actions.append("ALL data (memory + history + schedules)")
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

    if actions:
        if not args.yes:
            print(f"\nThis will DELETE: {', '.join(actions)}")
            confirm = input("Are you sure? [y/N] ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                db.close()
                return

        if args.all:
            reset_all(db)
        else:
            if args.memory:
                reset_memory(db)
            if args.history:
                reset_history(db, args.room)
            if args.schedules:
                reset_schedules(db)

    db.close()


if __name__ == "__main__":
    main()
