# Hoonbot — Revised Plan

## Context

Hoonbot is a personal AI assistant that connects two existing systems: **Messenger** (chat UI on port 3000) and **LLM_API** (local LLM backend on port 10007). Instead of building its own UI or LLM adapter, Hoonbot is a lightweight **bot service** that receives messages from Messenger via webhooks and responds using LLM_API.

```
Messenger (port 3000)  <--webhook/REST-->  Hoonbot (port 3939)  <--REST-->  LLM_API (port 10007)
   [UI + chat server]                       [bot service]                    [LLM + agents + tools]
```

**Removed from original plan:** WebChat UI, Ollama/llama.cpp adapters, Gateway server, ClawHub, skills/plugins, cross-platform support (Linux only), voice features.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3 | Matches LLM_API; simple for a backend-only bot service |
| HTTP Framework | FastAPI | Async webhook handling, minimal boilerplate |
| HTTP Client | httpx | Async calls to Messenger and LLM_API |
| Database | aiosqlite | Async SQLite for conversation history + memory |
| Process manager | systemd | Linux only, consistent with Messenger's deployment |

---

## Folder Structure

```
Hoonbot/
  hoonbot.py              # Entry point (FastAPI app, startup logic)
  config.py               # All configuration (ports, URLs, paths)
  SOUL.md                 # Bot personality / system prompt
  requirements.txt        # Python dependencies (fastapi, uvicorn, httpx, aiosqlite, apscheduler)

  core/
    __init__.py
    messenger.py          # Messenger API client (send message, typing, register bot/webhook)
    llm.py                # LLM_API client (chat completions wrapper)
    history.py            # Per-room conversation history (SQLite)
    memory.py             # Persistent key-value memory store (SQLite)
    scheduler.py          # APScheduler wrapper (cron + interval jobs)
    heartbeat.py          # Proactive tick logic (reason over memory → decide action → execute)

  handlers/
    __init__.py
    webhook.py            # POST /webhook — receives Messenger webhooks, processes messages
    health.py             # GET /health

  data/                   # Auto-created, gitignored
    hoonbot.db            # SQLite database
```

---

## Message Flow

1. User sends message in Messenger
2. Messenger dispatches webhook → `POST http://localhost:3939/webhook`
3. Hoonbot receives webhook, ignores own messages and non-text messages
4. Sends typing indicator → `POST http://localhost:3000/api/typing`
5. Loads per-room conversation history from SQLite
6. Builds messages array: `[system (SOUL.md), ...history, user_message]`
7. Calls LLM_API → `POST http://localhost:10007/v1/chat/completions` (multipart form-data, `agent_type=auto`)
8. Saves assistant response to per-room history
9. Sends response → `POST http://localhost:3000/api/send-message`
10. Stops typing → `POST http://localhost:3000/api/stop-typing`

---

## Phase 1: Working Bot (MVP)

### Step 1: Project scaffolding
- Create folder structure above
- `requirements.txt`: fastapi, uvicorn, httpx, aiosqlite
- `config.py` with all constants (ports, URLs, bot name, DB path, max history)

### Step 2: Messenger API client — `core/messenger.py`
Async httpx wrapper for Messenger's bot API:
- `register_bot(name)` → POST `/api/bots` → stores API key
- `register_webhook(url, events)` → POST `/api/webhooks` → subscribes to `new_message`
- `send_message(room_id, content)` → POST `/api/send-message`
- `send_typing(room_id)` / `stop_typing(room_id)`
- All requests use `x-api-key` header

Key files to reference:
- `Messenger/server/src/routes/api.ts` — bot API endpoints
- `Messenger/server/src/services/webhook.ts` — webhook payload format
- `Messenger/docs/API.md` — full API reference

### Step 3: LLM_API client — `core/llm.py`
Async wrapper for LLM_API's chat completions:
- `chat(messages, agent_type="auto")` → POST `/v1/chat/completions`
- **Important**: endpoint uses `Form(...)` not JSON body. Send as multipart form-data with `messages` as a JSON string.
- Returns assistant message content

Key file to reference:
- `LLM_API/backend/api/routes/chat.py` — endpoint interface (Form-data fields)

### Step 4: Conversation history — `core/history.py`
SQLite-backed per-room history:
- Table: `room_history(room_id, role, content, timestamp)`
- `add_message(room_id, role, content)`
- `get_history(room_id, limit=MAX_HISTORY)` → recent messages as `[{role, content}]`
- `clear_history(room_id)`
- Auto-trims to configurable limit (default 50 messages)

### Step 5: SOUL.md
Bot personality file loaded as the system prompt on every request.

### Step 6: Webhook handler — `handlers/webhook.py`
- `POST /webhook` — receives Messenger webhook payloads
- Ignores own messages (by sender name matching bot name)
- Ignores non-text message types
- Processes messages asynchronously via `asyncio.create_task`
- `process_message()`: typing → load history → build messages → call LLM → save history → send response → stop typing
- Error handling: sends error message back to Messenger on failure

### Step 7: Entry point — `hoonbot.py`
- FastAPI app with startup event:
  1. Init SQLite database (create tables if not exist)
  2. Register bot with Messenger (if not already registered)
  3. Register webhook with Messenger (subscribe to `new_message`)
  4. Start uvicorn on port 3939

### Step 8: Integration
- Update `start-all.sh` to add Hoonbot as a service
- Add to `settings.txt` if it exists

---

## Phase 2: Persistent Memory + Heartbeat

### `core/memory.py`
SQLite table: `memory(id, key, value, tags, created_at, updated_at)`
- `save(key, value, tags=[])` — upsert by key
- `recall(key)` — exact match lookup
- `search(query, limit=10)` — FTS5 full-text search
- `list_all(tag=None)` — browse all memories

Memory instructions added to SOUL.md so the LLM knows to output structured memory commands (e.g., `[MEMORY_SAVE: key=..., value=...]`). Hoonbot parses these from LLM responses and executes them.

### `core/scheduler.py`
APScheduler-based job scheduler:
- Wraps `AsyncIOScheduler`
- `add_cron_job(func, cron_expr, id)` — add a cron-style job
- `add_interval_job(func, seconds, id)` — add a repeating interval job
- `remove_job(id)` — cancel a job
- Jobs stored in SQLite for persistence across restarts (`apscheduler.jobstores.sqlalchemy` or manual table)

Additional SQLite table: `scheduled_jobs(id, name, cron, target_room_id, prompt, enabled, last_run)`

### `core/heartbeat.py` — Proactive Reasoning

The heartbeat tick runs on a configurable interval (default: every hour). On each tick:

1. **Load context** — fetch all memories + recent history from the home room
2. **Reason proactively** — call LLM_API with a system prompt like:
   ```
   You are Hoonbot. It is now {datetime}. Based on the user's persistent memory and
   recent conversation, decide if there is anything useful you should proactively do
   right now. Think: scheduled tasks due, things to remind the user about, background
   work to kick off, or simply a check-in. If nothing is needed, respond with {"action": "none"}.
   Otherwise respond with JSON: {"action": "message"|"task"|"none", "content": "..."}
   ```
3. **Execute the action**:
   - `"message"` → send the content to the home room
   - `"task"` → create a background task entry in SQLite, run the task asynchronously, report completion
   - `"none"` → do nothing (silent tick)

Additional SQLite table: `background_tasks(id, description, status, result, created_at, completed_at, room_id)`

### Scheduled Messages
- Stored in `scheduled_jobs` table with a natural-language `prompt` field
- On tick, scheduler checks for due jobs and sends the LLM the prompt to generate the message
- Example use: "Every morning at 8am, summarize today's date, weather (from memory), and any pending reminders"
- Jobs can be created by the user by chatting with Hoonbot ("remind me every Monday at 9am to...")

### Health Monitoring
- On heartbeat, ping `GET http://localhost:10007/health` and `GET http://localhost:3000/health`
- If a service is down, send an alert message to the home room
- Configurable: which services to monitor, alert threshold (N consecutive failures)

---

## Phase 3: Polish

- Retry logic for LLM_API/Messenger timeouts
- Split long responses into multiple messages
- Mention handling (respond only when @mentioned in group rooms)
- Rate limiting / debounce rapid messages
- Graceful shutdown (clear typing indicators on SIGTERM)
- Structured logging

---

## Configuration

### `config.py`
Reads from environment variables with defaults that match `settings.txt`. Since `start-all.sh` sources (but does not export) `settings.txt`, values must be set as defaults here too.

```python
import os

HOONBOT_PORT    = int(os.environ.get("HOONBOT_PORT", 3939))
HOONBOT_HOST    = "0.0.0.0"

MESSENGER_PORT  = int(os.environ.get("MESSENGER_PORT", 3000))
MESSENGER_URL   = f"http://localhost:{MESSENGER_PORT}"
MESSENGER_BOT_NAME      = "Hoonbot"
MESSENGER_API_KEY       = ""   # Auto-filled on first registration, persisted in DB
MESSENGER_HOME_ROOM_ID  = int(os.environ.get("HOONBOT_HOME_ROOM_ID", 1))

LLM_API_PORT    = int(os.environ.get("LLM_API_PORT", 10007))
LLM_API_URL     = f"http://localhost:{LLM_API_PORT}"
LLM_API_AGENT_TYPE = "auto"

SOUL_PATH = "SOUL.md"
DB_PATH   = "data/hoonbot.db"
MAX_HISTORY_MESSAGES = 50

# Heartbeat
HEARTBEAT_ENABLED           = os.environ.get("HOONBOT_HEARTBEAT_ENABLED", "true").lower() == "true"
HEARTBEAT_INTERVAL_SECONDS  = int(os.environ.get("HOONBOT_HEARTBEAT_INTERVAL", 3600))
```

### Additions to `settings.txt`
Add a new section at the bottom:

```bash
# --- LLM API ---
LLM_API_PORT=10007
LLM_API_TOOLS_PORT=10006

# --- Hoonbot ---
HOONBOT_PORT=3939
HOONBOT_HOME_ROOM_ID=1
HOONBOT_HEARTBEAT_ENABLED=true
HOONBOT_HEARTBEAT_INTERVAL=3600
```

### Additions to `start-all.sh`
Renumber steps from `[1/3]` → `[1/5]` and add LLM_API + Hoonbot:

```bash
echo "[1/5] Starting LLM API tools server (port $LLM_API_TOOLS_PORT)..."
gnome-terminal --tab --title="LLM_API Tools" -- bash -c "cd '$SCRIPT_DIR/../LLM_API' && python3 tools_server.py; exec bash"
sleep 2

echo "[2/5] Starting LLM API main server (port $LLM_API_PORT)..."
gnome-terminal --tab --title="LLM_API" -- bash -c "cd '$SCRIPT_DIR/../LLM_API' && python3 run_backend.py; exec bash"

echo "[3/5] Starting Messenger (port $MESSENGER_PORT)..."
gnome-terminal --tab --title="Messenger" -- bash -c "cd '$SCRIPT_DIR/Messenger' && npm run dev:server; exec bash"

echo "[4/5] Starting Hoonbot (port $HOONBOT_PORT)..."
gnome-terminal --tab --title="Hoonbot" -- bash -c "cd '$SCRIPT_DIR/Hoonbot' && python3 hoonbot.py; exec bash"
```
Note: ClaudeCodeWrapper (`[5/5]`) remains unchanged.

---

## Startup Order

```
1. LLM_API tools server  (port $LLM_API_TOOLS_PORT = 10006)
2. LLM_API main server   (port $LLM_API_PORT        = 10007)
3. Messenger             (port $MESSENGER_PORT       = 3000)
4. Hoonbot               (port $HOONBOT_PORT         = 3939)
5. ClaudeCodeWrapper     (port $CLAUDE_WRAPPER_PORT  = 8000)
```

All ports are defined in `settings.txt` and read by `start-all.sh`.
Hoonbot's `config.py` mirrors these values as defaults.

---

## Verification

1. Start all services in order
2. Hoonbot should auto-register as a bot in Messenger and subscribe to webhooks
3. Open Messenger UI, create/enter a room where Hoonbot is a member
4. Send a message → Hoonbot should show typing, then respond
5. Test conversation context: ask a follow-up question referencing previous message
6. Check `data/hoonbot.db` for stored history
