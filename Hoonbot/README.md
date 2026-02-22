# Hoonbot

A personal AI assistant that lives inside [Huni Messenger](../Messenger). Hoonbot runs locally, connects to an LLM backend, and provides conversational AI with persistent memory, scheduled tasks, a proactive heartbeat loop, extensible skills, daily logging, and desktop notifications.

## Architecture

```
┌─────────────┐       webhook        ┌───────────┐    multipart/form    ┌─────────┐
│    Huni      │  ──────────────────► │  Hoonbot  │  ─────────────────► │ LLM API │
│  Messenger   │  ◄────────────────── │  (FastAPI) │  ◄───────────────── │         │
│  :3000       │     send-message     │  :3939     │    chat response    │ :10007  │
└─────────────┘                       └─────┬─────┘                     └─────────┘
                                            │
                                     ┌──────┴──────┐
                                     │   SQLite DB  │
                                     │  (WAL mode)  │
                                     │  - memory    │
                                     │  - history   │
                                     │  - schedules │
                                     └─────────────┘
```

**Hoonbot** registers itself as a bot with Messenger on startup, subscribes to `new_message` webhook events, and replies by calling the LLM API. All persistent state (memory, conversation history, scheduled jobs) is stored in a single SQLite database.

## Features

### Persistent Memory
Key-value store with full-text search (SQLite FTS5). The LLM can save and delete memories using inline commands. Memories are injected into every prompt so context carries across conversations.

### Conversation History
Per-room message history stored in SQLite, trimmed to a configurable maximum (default 50 messages). When history approaches capacity, a **compaction flush** prompts the LLM to save important facts to memory before old messages are dropped.

### Heartbeat (Proactive Loop)
A periodic background tick (default every 60 minutes) that:
1. Runs any due scheduled jobs.
2. Performs compaction flushes for rooms near history capacity.
3. Evaluates a checklist (`HEARTBEAT.md`) against current context (memory, history, system info, schedules).
4. Decides autonomously whether to: do nothing, send a message, run a background task, or create a new scheduled job.

Configurable active hours prevent the bot from acting during off-hours.

### Scheduled Jobs
Cron-based recurring tasks or one-time reminders. The LLM creates them via inline commands in responses, or the heartbeat can create them autonomously. Scheduled jobs are persisted in SQLite and survive restarts.

### Skills (Extensible)
Markdown files in `skills/` are loaded into the system prompt on every request. The LLM can create new skills at runtime using `[SKILL_CREATE]` commands, making Hoonbot self-extending.

Built-in skills:
- **daily_log** — Guidelines for daily log usage.
- **self_extend** — Instructions for creating new skills.
- **system_info** — When and how to alert on system resource issues.

### Daily Log
Append-only daily notes stored as `data/memory/YYYY-MM-DD.md`. The last two days of logs are injected into the system prompt for narrative continuity across sessions.

### Desktop Notifications
Urgent alerts via the `plyer` library. The LLM can trigger them with `[NOTIFY]` commands. Controlled by the `HOONBOT_NOTIFICATIONS` environment variable.

### Incoming Webhooks
External services (GitHub, CI, calendars, etc.) can POST to `/webhook/incoming/<source>` to trigger Hoonbot. The payload is converted into a synthetic message and processed through the normal pipeline in the home room.

### Catch-Up on Startup
When Hoonbot starts, it scans all rooms for unanswered messages sent while it was offline and responds to them.

### Message Debouncing
Rapid consecutive messages from the same room are debounced (1.5 seconds) and combined before processing, preventing duplicate replies.

## Project Structure

```
Hoonbot/
├── hoonbot.py              # Entry point — FastAPI app, lifespan, startup sequence
├── config.py               # All configuration options with env overrides
├── reset.py                # CLI utility to reset/inspect persistent data
├── SOUL.md                 # System prompt — personality, behavior, command syntax
├── HEARTBEAT.md            # Heartbeat checklist — what to evaluate each tick
├── requirements.txt        # Python dependencies
│
├── core/
│   ├── llm.py              # LLM API client, soul loader, message builder
│   ├── memory.py           # Persistent memory (SQLite + FTS5)
│   ├── history.py          # Per-room conversation history
│   ├── messenger.py        # Huni Messenger bot API client
│   ├── heartbeat.py        # Proactive background loop
│   ├── scheduled.py        # Scheduled job storage and execution
│   ├── scheduler.py        # APScheduler wrapper
│   ├── skills.py           # Skill loader and creator
│   ├── daily_log.py        # Append-only daily log
│   ├── notify.py           # Desktop notification sender
│   ├── status_file.py      # Writes data/status.md snapshot
│   ├── sysinfo.py          # CPU/RAM/disk/battery info via psutil
│   └── retry.py            # Exponential backoff retry wrapper
│
├── handlers/
│   ├── webhook.py          # POST /webhook and POST /webhook/incoming/<source>
│   └── health.py           # GET /health
│
├── skills/                 # Markdown skill files (injected into system prompt)
│   ├── daily_log.md
│   ├── self_extend.md
│   └── system_info.md
│
└── data/                   # Created at runtime
    ├── hoonbot.db          # SQLite database
    ├── .apikey             # Persisted Messenger API key
    ├── status.md           # Auto-generated status snapshot
    └── memory/             # Daily logs (YYYY-MM-DD.md)
```

## Prerequisites

- **Python 3.10+**
- **Huni Messenger** running on port 3000 (or configured via `MESSENGER_PORT`)
- **LLM API** running on port 10007 (or configured via `LLM_API_PORT`) with an OpenAI-compatible `/v1/chat/completions` endpoint

## Installation

```bash
cd Hoonbot
pip install -r requirements.txt
```

### Dependencies

| Package      | Purpose                              |
|--------------|--------------------------------------|
| fastapi      | HTTP server framework                |
| uvicorn      | ASGI server                          |
| httpx        | Async HTTP client (LLM + Messenger)  |
| aiosqlite    | Async SQLite driver                  |
| apscheduler  | Heartbeat interval scheduling        |
| psutil       | System resource monitoring           |
| plyer        | Desktop notifications                |

## Running

From the project root:

```bash
python Hoonbot/hoonbot.py
```

Or with uvicorn directly:

```bash
uvicorn Hoonbot.hoonbot:app --host 0.0.0.0 --port 3939
```

### Startup Sequence

1. Open SQLite database (WAL mode), create tables if needed.
2. Restore API key from `data/.apikey` or register a new bot with Messenger.
3. Register webhook subscription for `new_message` events.
4. Start heartbeat scheduler (if enabled).
5. Generate initial `data/status.md` snapshot.
6. Catch up on any missed messages from while Hoonbot was offline.

## Configuration

All options can be overridden with environment variables.

| Option | Env Variable | Default | Description |
|--------|-------------|---------|-------------|
| Server port | `HOONBOT_PORT` | `3939` | Port Hoonbot listens on |
| Server host | — | `0.0.0.0` | Bind address |
| Messenger port | `MESSENGER_PORT` | `3000` | Huni Messenger server port |
| Bot name | — | `Hoonbot` | Display name in Messenger |
| Home room ID | `HOONBOT_HOME_ROOM_ID` | `1` | Default room for webhooks and catch-up |
| LLM API port | `LLM_API_PORT` | `10007` | LLM backend port |
| LLM agent type | — | `auto` | `chat`, `react`, `plan_execute`, or `auto` |
| Max history | — | `50` | Max messages kept per room |
| Max message length | `HOONBOT_MAX_MESSAGE_LENGTH` | `2000` | Messenger message chunk size |
| Heartbeat enabled | `HOONBOT_HEARTBEAT_ENABLED` | `true` | Enable/disable proactive loop |
| Heartbeat interval | `HOONBOT_HEARTBEAT_INTERVAL` | `3600` | Seconds between heartbeat ticks |
| Heartbeat active start | `HOONBOT_HEARTBEAT_ACTIVE_START` | `00:00` | Active hours window start (HH:MM) |
| Heartbeat active end | `HOONBOT_HEARTBEAT_ACTIVE_END` | `23:59` | Active hours window end (HH:MM) |
| Extra memory paths | `HOONBOT_MEMORY_EXTRA_PATHS` | — | Comma-separated paths to .md files/dirs |
| Notifications | `HOONBOT_NOTIFICATIONS` | `true` | Enable desktop notifications |
| Compaction threshold | `HOONBOT_COMPACTION_THRESHOLD` | `0.8` | History fraction that triggers compaction |
| Webhook secret | `HOONBOT_WEBHOOK_SECRET` | — | Secret for incoming webhook auth |

## LLM Command Syntax

Hoonbot's LLM uses inline commands embedded in its responses. These are parsed, executed, and stripped before the reply is sent to the user.

### Memory

```
[MEMORY_SAVE: key=<short_key>, value=<what to remember>, tags=<comma-separated>]
[MEMORY_DELETE: key=<short_key>]
```

### Scheduling

```
[SCHEDULE: name=<short_name>, cron=<HH:MM or 5-field cron>, prompt=<what to do>]
[SCHEDULE: name=<short_name>, at=<YYYY-MM-DD HH:MM>, prompt=<what to remind>]
```

### Daily Log

```
[DAILY_LOG: Brief note about what happened]
```

### Skill Creation

```
[SKILL_CREATE: name=skill_name, description=One-line description]
Instructions for the skill...
[/SKILL_CREATE]
```

### Desktop Notifications

```
[NOTIFY: title=Alert Title, message=The notification body]
```

## Reset Utility

Manage persistent data while Hoonbot is stopped:

```bash
python Hoonbot/reset.py --all                # Reset everything
python Hoonbot/reset.py --memory             # Clear all memories
python Hoonbot/reset.py --history            # Clear all conversation history
python Hoonbot/reset.py --history --room 1   # Clear history for room 1 only
python Hoonbot/reset.py --schedules          # Clear all scheduled jobs
python Hoonbot/reset.py --list-memory        # View stored memories (read-only)
python Hoonbot/reset.py --list-schedules     # View scheduled jobs (read-only)
```

## Customization

### SOUL.md
Edit `SOUL.md` to change Hoonbot's personality, default language, behavior rules, and command syntax. This file is the system prompt injected into every LLM call.

### HEARTBEAT.md
Edit `HEARTBEAT.md` to customize what the heartbeat checks each tick. The default checklist includes: time-sensitive memories, system resources, conversation silence, schedule gaps, and proactive insights.

### Skills
Add `.md` files to `skills/` to extend Hoonbot's capabilities. Skills are loaded into the system prompt on every request. The LLM can also create new skills at runtime.
