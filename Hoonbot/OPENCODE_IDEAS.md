# OpenClaw vs Hoonbot — Deep Comparison & Implementation Ideas

_Research conducted 2026-02-22. OpenClaw v0.x (135k+ GitHub stars)._

---

## What is OpenClaw?

OpenClaw (formerly Clawdbot/Moltbot) is a free, open-source autonomous AI agent by Peter Steinberger. It runs locally, uses messaging apps (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, etc.) as its UI, and acts as a "digital employee" — always on, proactive, self-extending.

Key philosophy: **files are the source of truth**. Memory is Markdown. Skills are Markdown. Config is JSON5. Everything is human-readable and hackable.

---

## Implementation Status

### Completed

- **Skills system** — `skills/*.md` injected into system prompt; self-creation via `[SKILL_CREATE: ...]`
- **HEARTBEAT.md** — user-editable checklist file guiding proactive behavior
- **Active hours** — skip heartbeat outside `HEARTBEAT_ACTIVE_START`–`HEARTBEAT_ACTIVE_END`
- **Daily memory logs** — `data/memory/YYYY-MM-DD.md` append-only narrative logs
- **Desktop notifications** — `plyer` via `[NOTIFY: title=..., message=...]`
- **System info (psutil)** — CPU/RAM/disk/battery injected into heartbeat context
- **Temporal decay** — memories ordered by `updated_at DESC` in prompts
- **Extra memory paths** — `HOONBOT_MEMORY_EXTRA_PATHS` indexes external Markdown files
- **Parallel background tasks** — `asyncio.create_task()` for non-blocking heartbeat tasks
- **Autonomous schedule creation** — heartbeat can autonomously create scheduled jobs
- **data/status.md** — human-readable mirror of all DB state (memories, schedules, skills)
- **Context compaction memory flush** — heartbeat saves key memories when history approaches limit
- **Incoming webhooks** — `POST /webhook/incoming/<source>` for external service triggers

---

## Architecture Comparison

| Component | OpenClaw | Hoonbot |
|-----------|----------|---------|
| **Runtime** | Node.js Gateway (port 18789) | Python FastAPI (port 3939) |
| **LLM** | Any provider (Anthropic, OpenAI, local) | Local LLM_API (port 10007) |
| **Chat UI** | 17+ channels (WhatsApp, Telegram, etc.) | Huni Messenger only |
| **Memory** | Markdown files + vector/BM25 hybrid search | SQLite + FTS5 |
| **Scheduling** | Cron CLI + Heartbeat system | SQLite scheduled_jobs + heartbeat |
| **Skills/Plugins** | Markdown-based skill system (5700+ on ClawHub) | Markdown skills in `skills/` |
| **Heartbeat** | HEARTBEAT.md checklist, active hours | HEARTBEAT.md + active hours |
| **Daily logs** | `memory/YYYY-MM-DD.md` | `data/memory/YYYY-MM-DD.md` |
| **Sub-agents** | sessions_spawn (parallel isolated workers) | Partial (asyncio background tasks) |
| **Voice** | ElevenLabs TTS + wake word + phone calls | Not planned |
| **Browser** | Full Chromium automation | Deferred |
| **Device control** | Nodes (camera, screen, location) | Desktop notifications + sysinfo |
| **Config** | Centralized JSON5 with hot-reload | Python config.py + env vars |
| **Hooks** | Event-driven TypeScript handlers | Incoming webhooks endpoint |
| **Compaction flush** | memoryFlush before context compaction | Heartbeat-triggered memory flush |

---

## Feature Notes

### MEMORY SYSTEM

- SQLite key-value store with FTS5 full-text search
- Daily memory logs: `data/memory/YYYY-MM-DD.md`
- Extra memory paths: inject external Markdown dirs/files
- Temporal decay: ORDER BY updated_at DESC
- Context compaction flush: heartbeat saves memories when history >= 80% full

### SKILLS SYSTEM

- `skills/*.md` loaded fresh on every LLM call
- YAML frontmatter stripped before injection
- Self-creating: `[SKILL_CREATE: name=..., description=...]...[/SKILL_CREATE]`
- Bundled: `system_info.md`, `daily_log.md`, `self_extend.md`

### INCOMING WEBHOOKS (added 2026-02-22)

External services POST to `http://localhost:3939/webhook/incoming/<source>` with optional `X-Webhook-Secret` header authentication.

```bash
# GitHub push notification
curl -X POST http://localhost:3939/webhook/incoming/github \
  -H "X-Webhook-Secret: mysecret" \
  -H "Content-Type: application/json" \
  -d '{"message": "New push to main: Fix login bug"}'

# Any external alert
curl -X POST http://localhost:3939/webhook/incoming/monitor \
  -d '{"message": "Disk usage exceeded 90%"}'
```

The LLM sees `[Webhook from <source>] ...` and responds as an automated notification handler.

### CONTEXT COMPACTION MEMORY FLUSH (added 2026-02-22)

When any room's history count >= `COMPACTION_FLUSH_THRESHOLD * MAX_HISTORY_MESSAGES` (default: 40/50 messages), the heartbeat prompts the LLM to review the last 20 messages and save important facts as memories before old messages get trimmed. Runs at most once per 4 hours per room.

---

## Config Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `HOONBOT_PORT` | `3939` | Hoonbot HTTP port |
| `HOONBOT_HOME_ROOM_ID` | `1` | Default room for heartbeat/webhooks |
| `HOONBOT_HEARTBEAT_ENABLED` | `true` | Enable/disable heartbeat |
| `HOONBOT_HEARTBEAT_INTERVAL` | `3600` | Heartbeat interval (seconds) |
| `HOONBOT_HEARTBEAT_ACTIVE_START` | `00:00` | Active hours start (HH:MM) |
| `HOONBOT_HEARTBEAT_ACTIVE_END` | `23:59` | Active hours end (HH:MM) |
| `HOONBOT_MEMORY_EXTRA_PATHS` | `` | Comma-separated Markdown paths to index |
| `HOONBOT_NOTIFICATIONS` | `true` | Enable desktop notifications |
| `HOONBOT_COMPACTION_THRESHOLD` | `0.8` | History fraction before compaction flush |
| `HOONBOT_WEBHOOK_SECRET` | `` | Secret for incoming webhooks (blank = no auth) |

---

## Deferred / Not Planned

- **Browser automation** — LLM_API's web search covers most cases; add Playwright if specific need arises
- **Voice** — ElevenLabs TTS + wake word, big project, separate scope
- **Model failover** — 3x retry on single LLM_API endpoint is sufficient for local use
- **Multi-agent routing** — single personal agent, not needed

---

## Sources

- [OpenClaw Official Site](https://openclaw.ai/)
- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Docs — Memory](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw Docs — Skills](https://docs.openclaw.ai/tools/skills)
- [OpenClaw Docs — Webhooks](https://docs.openclaw.ai/automation/webhook)
- [OpenClaw Docs — Cron vs Heartbeat](https://docs.openclaw.ai/automation/cron-vs-heartbeat)
- [ClawHub Registry](https://github.com/openclaw/clawhub)
- [DigitalOcean — What is OpenClaw](https://www.digitalocean.com/resources/articles/what-is-openclaw)
- [OpenClaw Memory Deep Dive](https://snowan.gitbook.io/study-notes/ai-blogs/openclaw-memory-system-deep-dive)
- [OpenClaw Architecture](https://ppaolo.substack.com/p/openclaw-system-architecture-overview)
