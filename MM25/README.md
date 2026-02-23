# MM25 - Personal AI Assistant System

MM25 (Hoonbot) is a personal AI assistant that runs locally and integrates with Huni Messenger. It provides conversational AI with persistent memory, proactive heartbeat monitoring, scheduled tasks, extensible skills, and desktop notifications.

## Overview

MM25 is designed as a personal AI companion that:
- Lives inside Huni Messenger application
- Runs locally on your machine (not a cloud service)
- Has persistent memory across conversations
- Can proactively monitor and take actions via heartbeat
- Supports scheduled jobs and reminders
- Can be extended with custom skills
- Sends desktop notifications for urgent alerts

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

### Components

| Component | Port | Description |
|-----------|------|-------------|
| Huni Messenger | 3000 | Messaging platform that sends webhook events to Hoonbot |
| Hoonbot (MM25) | 3939 | FastAPI server handling messages, webhooks, and AI processing |
| LLM API | 10007 | Local LLM backend for generating responses |

## Features

### 1. Persistent Memory
- Key-value store with full-text search (SQLite FTS5)
- LLM can save/delete memories using inline commands
- Memories are injected into every prompt for context continuity

### 2. Conversation History
- Per-room message history stored in SQLite
- Configurable maximum (default 50 messages per room)
- **Compaction flush** - when history approaches capacity, prompts LLM to save important facts before old messages are dropped

### 3. Heartbeat (Proactive Loop)
A periodic background tick (default every 60 minutes) that:
1. Runs any due scheduled jobs
2. Performs compaction flushes for rooms near history capacity
3. Evaluates a checklist against current context
4. Decides autonomously whether to: do nothing, send a message, run a background task, or create a new scheduled job

Configurable active hours prevent the bot from acting during off-hours.

### 4. Scheduled Jobs
- Cron-based recurring tasks or one-time reminders
- Created via inline commands in LLM responses
- Persisted in SQLite and survive restarts

### 5. Skills (Extensible)
- Markdown files in `skills/` loaded into system prompt on every request
- LLM can create new skills at runtime using `[SKILL_CREATE]` commands
- Built-in skills: daily_log, self_extend, system_info

### 6. Daily Log
- Append-only daily notes stored as `data/memory/YYYY-MM-DD.md`
- Last two days of logs injected into system prompt for narrative continuity

### 7. Desktop Notifications
- Urgent alerts via `plyer` library
- Triggered with `[NOTIFY]` commands
- Controlled by `HOONBOT_NOTIFICATIONS` environment variable

### 8. Incoming Webhooks
- External services can POST to `/webhook/incoming/<source>`
- Payload converted into synthetic message and processed in home room
- Supports GitHub, CI/CD, calendars, monitoring tools, etc.

### 9. Catch-Up on Startup
- Scans all rooms for unanswered messages sent while offline
- Responds to missed messages on startup

### 10. Message Debouncing
- Rapid consecutive messages debounced (1.5 seconds)
- Prevents duplicate replies

## Quick Start

### Prerequisites
- Python 3.10+
- Huni Messenger running on port 3000
- LLM API running on port 10007

### Installation

```bash
cd Hoonbot
pip install -r requirements.txt
```

### Running

```bash
python Hoonbot/hoonbot.py
```

Or with uvicorn directly:

```bash
uvicorn Hoonbot.hoonbot:app --host 0.0.0.0 --port 3939
```

### Startup Sequence

1. Open SQLite database (WAL mode), create tables if needed
2. Restore API key from `data/.apikey` or register a new bot with Messenger
3. Register webhook subscription for `new_message` events
4. Start heartbeat scheduler (if enabled)
5. Generate initial `data/status.md` snapshot
6. Catch up on any missed messages from while offline

## Configuration

All options can be overridden with environment variables.

| Option | Env Variable | Default | Description |
|--------|-------------|---------|-------------|
| Server port | `HOONBOT_PORT` | 3939 | Port Hoonbot listens on |
| Server host | - | 0.0.0.0 | Bind address |
| Messenger port | `MESSENGER_PORT` | 3000 | Huni Messenger server port |
| Bot name | - | Hoonbot | Display name in Messenger |
| Home room ID | `HOONBOT_HOME_ROOM_ID` | 1 | Default room for webhooks |
| LLM API port | `LLM_API_PORT` | 10007 | LLM backend port |
| LLM agent type | - | auto | chat, react, plan_execute, or auto |
| Max history | - | 50 | Max messages kept per room |
| Max message length | `HOONBOT_MAX_MESSAGE_LENGTH` | 2000 | Message chunk size |
| Heartbeat enabled | `HOONBOT_HEARTBEAT_ENABLED` | true | Enable/disable proactive loop |
| Heartbeat interval | `HOONBOT_HEARTBEAT_INTERVAL` | 3600 | Seconds between ticks |
| Heartbeat active start | `HOONBOT_HEARTBEAT_ACTIVE_START` | 00:00 | Active hours start (HH:MM) |
| Heartbeat active end | `HOONBOT_HEARTBEAT_ACTIVE_END` | 23:59 | Active hours end (HH:MM) |
| Notifications | `HOONBOT_NOTIFICATIONS` | true | Enable desktop notifications |
| Compaction threshold | `HOONBOT_COMPACTION_THRESHOLD` | 0.8 | History fraction triggering compaction |
| Webhook secret | `HOONBOT_WEBHOOK_SECRET` | - | Secret for incoming webhook auth |

## LLM Command Syntax

Hoonbot's LLM uses inline commands embedded in responses. These are parsed, executed, and stripped before the reply is sent.

### Memory Commands

```
[MEMORY_SAVE: key=<short_key>, value=<what to remember>, tags=<comma-separated>]
[MEMORY_DELETE: key=<short_key>]
```

### Scheduling Commands

```
[SCHEDULE: name=<short_name>, cron=<HH:MM or cron>, prompt=<what to do>]
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

## Project Structure

```
Hoonbot/
├── hoonbot.py              # Entry point — FastAPI app, lifespan, startup
├── config.py               # All configuration options with env overrides
├── reset.py                # CLI utility to reset/inspect persistent data
├── SOUL.md                 # System prompt — personality, behavior
├── HEARTBEAT.md            # Heartbeat checklist
├── requirements.txt        # Python dependencies
│
├── core/
│   ├── llm.py              # LLM API client, soul loader, message builder
│   ├── memory.py           # Persistent memory (SQLite + FTS5)
│   ├── history.py          # Per-room conversation history
│   ├── messenger.py         # Huni Messenger bot API client
│   ├── heartbeat.py        # Proactive background loop
│   ├── scheduled.py        # Scheduled job storage and execution
│   ├── scheduler.py        # APScheduler wrapper
│   ├── skills.py           # Skill loader and creator
│   ├── daily_log.py        # Append-only daily log
│   ├── notify.py           # Desktop notification sender
│   ├── status_file.py      # Writes data/status.md snapshot
│   ├── sysinfo.py          # CPU/RAM/disk/battery info
│   └── retry.py            # Exponential backoff retry
│
├── handlers/
│   ├── webhook.py          # POST /webhook and /webhook/incoming/<source>
│   └── health.py           # GET /health
│
├── skills/                 # Markdown skill files
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

## Reset Utility

Manage persistent data while Hoonbot is stopped:

```bash
python Hoonbot/reset.py --all                # Reset everything
python Hoonbot/reset.py --memory             # Clear all memories
python Hoonbot/reset.py --history            # Clear all conversation history
python Hoonbot/reset.py --history --room 1   # Clear history for room 1 only
python Hoonbot/reset.py --schedules          # Clear all scheduled jobs
python Hoonbot/reset.py --list-memory        # View stored memories
python Hoonbot/reset.py --list-schedules     # View scheduled jobs
```

## Customization

### SOUL.md
Edit `SOUL.md` to change Hoonbot's personality, default language, behavior rules, and command syntax.

### HEARTBEAT.md
Edit `HEARTBEAT.md` to customize what the heartbeat checks each tick.

### Skills
Add `.md` files to `skills/` to extend capabilities. The LLM can also create new skills at runtime.

## Dependencies

| Package | Purpose |
|---------|---------|
| fastapi | HTTP server framework |
| uvicorn | ASGI server |
| httpx | Async HTTP client (LLM + Messenger) |
| aiosqlite | Async SQLite driver |
| apscheduler | Heartbeat interval scheduling |
| psutil | System resource monitoring |
| plyer | Desktop notifications |

## License

Created by and for Huni.
