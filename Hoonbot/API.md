# Hoonbot API Documentation

Hoonbot exposes a FastAPI server on port **3939** (configurable via `HOONBOT_PORT`).

Base URL: `http://localhost:3939`

---

## Endpoints

### GET /health

Health check endpoint.

**Response** `200 OK`

```json
{
  "status": "ok",
  "timestamp": "2026-02-22T12:00:00.000000+00:00"
}
```

---

### POST /webhook

Receives event notifications from Huni Messenger. This is registered automatically on startup — you do not need to call it manually.

**Request Body**

```json
{
  "event": "new_message",
  "roomId": 1,
  "timestamp": "2026-02-22T12:00:00.000Z",
  "data": {
    "id": 42,
    "content": "Hello Hoonbot",
    "type": "text",
    "senderName": "Lee",
    "senderId": 3,
    "isBot": false
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Event type. Only `"new_message"` is processed; all others are ignored. |
| `roomId` | integer | The room the message was sent in. |
| `timestamp` | string | ISO 8601 timestamp of the event. |
| `data.id` | integer | Message ID. |
| `data.content` | string | Message text. |
| `data.type` | string | Message type. Only `"text"` is processed. |
| `data.senderName` | string | Display name of the sender. |
| `data.senderId` | integer | User ID of the sender. |
| `data.isBot` | boolean | Whether the sender is a bot. Bot messages are ignored. |

**Behavior**

- Messages from bots or from Hoonbot itself are ignored.
- Empty or non-text messages are ignored.
- In rooms other than the home room (`HOONBOT_HOME_ROOM_ID`), Hoonbot only responds when `@Hoonbot` is mentioned in the message. The mention is stripped before processing.
- Rapid messages from the same room are debounced (1.5 second window). Only the latest message in the window is processed.

**Response** `200 OK`

```json
{
  "ok": true
}
```

---

### POST /webhook/incoming/{source}

Accepts webhook triggers from external services (GitHub, CI systems, calendars, monitoring tools, etc.). The payload is converted into a synthetic message and processed through Hoonbot's normal message pipeline, delivered to the home room.

**URL Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `source` | string | Identifies the external service (e.g., `github`, `ci/build`, `calendar`). Appears in the synthetic message as `[Webhook from <source>]`. |

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `X-Webhook-Secret` | Conditional | Required if `HOONBOT_WEBHOOK_SECRET` env var is set. Must match exactly. |
| `Content-Type` | Yes | `application/json` |

**Request Body**

Any valid JSON object. If the body contains a `"message"` key, its value is used as the content. Otherwise, the entire JSON payload is pretty-printed.

**Example: With `message` field**

```bash
curl -X POST http://localhost:3939/webhook/incoming/github \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: your-secret-here" \
  -d '{"message": "New PR #42 opened: Fix login bug", "repo": "huni/app"}'
```

Hoonbot receives: `[Webhook from github] New PR #42 opened: Fix login bug`

**Example: Without `message` field**

```bash
curl -X POST http://localhost:3939/webhook/incoming/monitor \
  -H "Content-Type: application/json" \
  -d '{"cpu": 95, "alert": "high_cpu", "host": "server-1"}'
```

Hoonbot receives:
```
[Webhook from monitor] {
  "cpu": 95,
  "alert": "high_cpu",
  "host": "server-1"
}
```

**Response** `200 OK`

```json
{
  "ok": true
}
```

**Error Response** `401 Unauthorized` (when secret is configured but missing/wrong)

```json
{
  "detail": "Invalid webhook secret"
}
```

---

## Message Processing Pipeline

When Hoonbot receives a valid message (from either `/webhook` or `/webhook/incoming`), it goes through this pipeline:

```
1. Send typing indicator to the room
2. Load context:
   ├── SOUL.md (system prompt / personality)
   ├── Persistent memories (from SQLite, ordered by recency)
   ├── Skills (all .md files from skills/)
   ├── Daily logs (last 2 days)
   ├── Conversation history (last 50 messages for the room)
   └── Extra reference documents (from MEMORY_EXTRA_PATHS)
3. Build message array: [system, ...history, user]
4. Call LLM API → get response
5. Parse and execute inline commands:
   ├── MEMORY_SAVE    → save to memory store
   ├── MEMORY_DELETE   → delete from memory store
   ├── SCHEDULE        → create scheduled job
   ├── SKILL_CREATE    → write new skill file
   ├── DAILY_LOG       → append to daily log
   └── NOTIFY          → send desktop notification
6. Strip all command tags from visible reply
7. Save user + assistant messages to history
8. Send reply to room (auto-chunked if over 2000 chars)
9. Stop typing indicator
```

---

## Heartbeat System

The heartbeat runs as a background interval job (default every 3600 seconds).

### Tick Sequence

```
1. Check active hours → skip if outside window
2. Run due scheduled jobs
3. Run compaction flushes for rooms near history limit
4. Build heartbeat context:
   ├── HEARTBEAT.md checklist
   ├── Current datetime
   ├── All persistent memories
   ├── Recent conversation history (last 10 messages)
   ├── All scheduled jobs
   └── System info (CPU, RAM, disk, battery)
5. Ask LLM: "What should you do right now?"
6. Parse JSON action and execute
```

### Heartbeat Actions

The LLM responds with exactly one JSON action:

**No action (most common)**
```json
{"action": "none"}
```

**Send a message to the home room**
```json
{"action": "message", "content": "Hey, your meeting is in 30 minutes!"}
```

**Run a background task**
```json
{"action": "task", "content": "Search for the latest Python security advisories"}
```

**Create a recurring scheduled job**
```json
{"action": "schedule", "name": "daily_digest", "cron": "09:00", "prompt": "Summarize pending tasks"}
```

**Create a one-time scheduled job**
```json
{"action": "schedule", "name": "deadline_alert", "at": "2026-03-01 09:00", "prompt": "Project deadline is today"}
```

---

## Inline LLM Commands Reference

These commands are embedded in the LLM's response text, parsed and executed by Hoonbot, then stripped before the reply reaches the user.

### MEMORY_SAVE

Save or update a persistent memory entry.

```
[MEMORY_SAVE: key=<short_key>, value=<what to remember>, tags=<comma,separated,tags>]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `key` | Yes | Unique identifier for the memory (upsert on conflict) |
| `value` | Yes | The content to store |
| `tags` | No | Comma-separated tags for categorization |

**Examples**
```
[MEMORY_SAVE: key=user_birthday, value=March 5, tags=personal]
[MEMORY_SAVE: key=project_deadline, value=2026-03-15 for Hoonbot MVP, tags=projects,deadlines]
```

### MEMORY_DELETE

Remove a memory entry by key.

```
[MEMORY_DELETE: key=<short_key>]
```

### SCHEDULE (Recurring)

Create a recurring scheduled job.

```
[SCHEDULE: name=<short_name>, cron=<HH:MM or 5-field cron>, prompt=<what to do>]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Unique name for the job |
| `cron` | Yes | `HH:MM` for daily, or standard 5-field cron expression |
| `prompt` | Yes | Instruction the LLM will execute when the job fires |

**Examples**
```
[SCHEDULE: name=morning_briefing, cron=08:00, prompt=Good morning! Summarize today's schedule.]
[SCHEDULE: name=weekly_review, cron=0 18 * * 5, prompt=It's Friday — summarize this week's progress.]
```

### SCHEDULE (One-Time)

Create a one-time reminder.

```
[SCHEDULE: name=<short_name>, at=<YYYY-MM-DD HH:MM>, prompt=<what to remind>]
```

**Example**
```
[SCHEDULE: name=meeting_reminder, at=2026-02-25 14:00, prompt=Team meeting starts in 30 minutes.]
```

### DAILY_LOG

Append a note to today's daily log file (`data/memory/YYYY-MM-DD.md`).

```
[DAILY_LOG: Brief note about what happened]
```

### SKILL_CREATE

Create a new skill file in `skills/`.

```
[SKILL_CREATE: name=skill_name, description=One-line description]
Markdown instructions for how to use this skill.
Multiple lines are supported.
[/SKILL_CREATE]
```

### NOTIFY

Send a desktop notification.

```
[NOTIFY: title=Alert Title, message=The notification body]
```

---

## Database Schema

All tables are in `data/hoonbot.db` (SQLite, WAL mode).

### memory

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Auto-increment ID |
| `key` | TEXT (UNIQUE) | Memory key |
| `value` | TEXT | Memory content |
| `tags` | TEXT | Comma-separated tags |
| `created_at` | TEXT | ISO 8601 creation timestamp |
| `updated_at` | TEXT | ISO 8601 last update timestamp |

Full-text search is available via the `memory_fts` virtual table (FTS5 over `key`, `value`, `tags`). Kept in sync with triggers.

### room_history

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Auto-increment ID |
| `room_id` | INTEGER | Messenger room ID |
| `role` | TEXT | `"user"` or `"assistant"` |
| `content` | TEXT | Message content |
| `created_at` | TEXT | ISO 8601 timestamp |

Trimmed to `MAX_HISTORY_MESSAGES` (default 50) per room. Oldest messages are deleted first.

### scheduled_jobs

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Auto-increment ID |
| `name` | TEXT | Job name |
| `room_id` | INTEGER | Target room for output |
| `prompt` | TEXT | Instruction for the LLM |
| `cron` | TEXT | Cron expression (HH:MM or 5-field) |
| `once_at` | TEXT | ISO datetime for one-time jobs |
| `enabled` | INTEGER | 1 = active, 0 = disabled |
| `last_run` | TEXT | ISO 8601 timestamp of last execution |
| `created_at` | TEXT | ISO 8601 creation timestamp |

---

## External Service Integration

### Setting Up Incoming Webhooks

1. Optionally set a secret:
   ```bash
   export HOONBOT_WEBHOOK_SECRET="my-secret-token"
   ```

2. Configure your external service to POST to:
   ```
   http://<hoonbot-host>:3939/webhook/incoming/<source-name>
   ```

3. Include the secret in the `X-Webhook-Secret` header (if configured).

4. Send a JSON body. Include a `"message"` field for a human-readable summary, or send raw JSON which will be pretty-printed.

### Example: GitHub Webhook

Configure a GitHub repository webhook:
- **Payload URL**: `http://your-server:3939/webhook/incoming/github`
- **Content type**: `application/json`
- **Secret**: Set in `X-Webhook-Secret` header (your custom proxy must forward this)

### Example: Cron Job Alert

```bash
curl -X POST http://localhost:3939/webhook/incoming/backup \
  -H "Content-Type: application/json" \
  -d '{"message": "Nightly backup completed successfully. 42GB transferred."}'
```

### Example: CI/CD Pipeline

```bash
curl -X POST http://localhost:3939/webhook/incoming/ci/deploy \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $HOONBOT_WEBHOOK_SECRET" \
  -d '{"message": "Deploy to production succeeded", "version": "1.2.3", "commit": "abc1234"}'
```

---

## Error Handling

- **LLM call failures**: Retried up to 3 times with exponential backoff (base 2 seconds).
- **Messenger send failures**: Retried up to 3 times with exponential backoff.
- **Message processing errors**: An error message (`⚠️ Error: ...`) is sent to the room. The typing indicator is always cleared.
- **Heartbeat failures**: Logged and silently skipped. The next tick will run normally.
- **Invalid webhook secret**: Returns `401 Unauthorized` immediately.
