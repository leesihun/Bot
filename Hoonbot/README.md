# Hoonbot

A simplified, tool-driven personal AI assistant that connects Huni Messenger (chat UI) with LLM_API_fast (LLM backend).

## Quick Start

### Prerequisites

1. **LLM_API_fast** running:
   ```bash
   cd ../LLM_API_fast
   python tools_server.py &      # Terminal 1
   python run_backend.py &       # Terminal 2
   ```

2. **Huni Messenger** running on port 3000

### Setup (One-Time)

Run the setup script to automatically get LLM_API_KEY:

```bash
cd Hoonbot
python setup.py
```

This will:
- Connect to LLM_API_fast
- Login with default credentials (admin/administrator)
- Get access token
- List available models
- Save to `.env` file
- Set environment variables

Example output:
```
[Setup] Connecting to LLM_API_fast at http://localhost:10007
✓ Successfully obtained access token

Available models:
  1. llama2
  2. mistral
  3. neural-chat

Selected: llama2
✓ Set LLM_API_KEY
✓ Set LLM_MODEL
✓ Saved environment variables to .env

Setup Complete!
```

### Start Hoonbot

```bash
cd Hoonbot

# Load environment variables from .env
source .env

# Start Hoonbot
python hoonbot.py
```

Expected output:
```
[Messenger] Bot registered and key saved
[Messenger] Webhook target: http://localhost:3939/webhook
[Hoonbot] Ready on port 3939
```

## Key Documentation Files

### 📋 [PROMPT.md](PROMPT.md) - System Prompt
**What it is:** The unified prompt that tells the LLM how to behave, what tools to use, and how to manage memory.

**Key sections:**
- Identity and behavior guidelines
- Memory system instructions (read/write/update)
- Complete tool documentation
- When to update memory
- Webhook handling

**Usage:** Automatically loaded and injected into every LLM conversation.

### 🏗️ [ARCHITECTURE.md](ARCHITECTURE.md) - System Design
**What it is:** Complete technical documentation of how Hoonbot works.

**Key sections:**
- Data flow diagrams
- Component descriptions
- File organization
- Configuration options
- Startup sequence
- Troubleshooting guide

**Read this if you want to understand how everything connects.**

### 🧠 [data/memory.md](data/memory.md) - Persistent Memory
**What it is:** The single memory file where information persists across conversations.

**Features:**
- Plain Markdown format
- Automatically injected into every LLM call
- Absolute path provided to LLM
- Can be edited manually or via file_writer tool

**The LLM uses file_reader to read and file_writer to update this file.**

## How It Works

### 1. User sends a message in Messenger
```
User → Messenger (port 3000) → Hoonbot (port 3939)
```

### 2. Hoonbot processes the message
```
1. Load PROMPT.md (system prompt)
2. Load data/memory.md (persistent memory)
3. Build message with absolute path to memory file
4. Call LLM_API_fast with agent_type: auto
```

### 3. LLM uses tools to accomplish the task
```
LLM can use:
- file_reader     : Read memory and other files
- file_writer     : Update memory and save files
- file_navigator  : Explore directories
- websearch       : Search the web
- python_coder    : Run Python code
- rag             : Query documents
- shell_exec      : Run shell commands
```

### 4. LLM returns response to Hoonbot
```
LLM response → Hoonbot → Messenger (port 3000) → User
```

## File Structure

```
Hoonbot/
├── README.md               ← Start here
├── ARCHITECTURE.md         ← Technical design
├── PROMPT.md              ← System prompt (unified)
├── SOUL.md                ← Legacy personality file
│
├── hoonbot.py             # Main entry point
├── config.py              # Configuration
├── reset.py               # Memory reset utility
├── test_llm.py            # Test script
│
├── handlers/
│   ├── webhook.py         # Message processing
│   └── health.py          # Health check
│
├── core/
│   ├── messenger.py       # Messenger API client
│   └── retry.py           # Retry decorator
│
└── data/
    ├── memory.md          # Persistent memory
    └── .apikey            # Messenger API key (auto-created)
```

## Configuration

All settings via environment variables in `config.py`:

```bash
# Server
HOONBOT_PORT=3939
HOONBOT_HOST=0.0.0.0

# Messenger
MESSENGER_PORT=3000
HOONBOT_BOT_NAME=Hoonbot
HOONBOT_HOME_ROOM_ID=1

# LLM_API_fast (REQUIRED)
LLM_API_KEY=your_token_here       # Must set
LLM_MODEL=your_model_name          # Must set
LLM_API_URL=http://localhost:10007 # Auto-detected, can override

# Webhooks (optional)
HOONBOT_WEBHOOK_SECRET=optional_secret_for_incoming_webhooks
```

## Core Concepts

### Memory System

**How it works:**
1. `data/memory.md` is a plain Markdown file
2. On every LLM call, memory is included in the system prompt
3. LLM can read the file with `file_reader` tool
4. LLM can update the file with `file_writer` tool

**What to save:**
- User preferences and personal information
- Important facts and decisions
- Project status
- Anything the user says to remember

**Example update flow:**
```
User: "Remember: I'm working on Project X"
     ↓
LLM sees this
     ↓
LLM uses file_reader to read memory.md
     ↓
LLM adds "Project X" entry
     ↓
LLM uses file_writer to save updated memory.md
     ↓
Next message includes updated memory
```

### Tool System

Everything is handled through LLM_API_fast tools. The LLM automatically decides which tool to use:

- **Need to save information?** → Use file_writer
- **Need to check saved info?** → Use file_reader
- **Need to search the web?** → Use websearch
- **Need to analyze data?** → Use python_coder
- **Need to run a script?** → Use shell_exec

**No custom commands or parsing—just pure tool usage.**

### Webhook Events

External services can trigger Hoonbot by posting to:
```
POST http://localhost:3939/webhook/incoming/<source>
X-Webhook-Secret: optional_secret
Content-Type: application/json

{
  "message": "Something happened"
}
```

Example: GitHub webhook
```
POST http://localhost:3939/webhook/incoming/github
Content-Type: application/json

{
  "action": "opened",
  "pull_request": {
    "title": "Fix bug in auth",
    "url": "..."
  }
}
```

Hoonbot receives: `[Webhook from github] PR opened: Fix bug in auth...`

## Testing

### Test LLM Connection

```bash
export LLM_API_KEY="your_token"
export LLM_MODEL="your_model"
python test_llm.py
```

Shows:
- If LLM_API_fast is reachable
- If the LLM responds
- If memory update would work

### Reset Memory

```bash
# View current memory
python reset.py --view-memory

# Reset to blank
python reset.py --memory

# Reset everything
python reset.py --all
```

### Manual Memory Editing

Edit `data/memory.md` directly in any text editor:
```markdown
# Hoonbot Memory

## User
- Name: Huni
- Preferences: [list preferences]

## Projects
- [Project info]

## Notes
- [Important facts]
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  Huni Messenger (TypeScript/Electron)   │
│  Chat UI on port 3000                   │
└──────────────┬──────────────────────────┘
               │ HTTP: POST /webhook
               │
┌──────────────▼──────────────────────────┐
│  Hoonbot (Python/FastAPI)               │
│  Main entry: hoonbot.py                 │
│  Processing: handlers/webhook.py        │
│  Port: 3939                             │
│                                         │
│  1. Receive message from Messenger      │
│  2. Load PROMPT.md + memory.md          │
│  3. Call LLM_API_fast                   │
│  4. LLM uses tools (file_*, web*, etc)  │
│  5. Send reply back to Messenger        │
└──────────────┬──────────────────────────┘
               │ HTTP: POST /v1/chat/completions
               │
┌──────────────▼──────────────────────────┐
│  LLM_API_fast (Python/FastAPI)          │
│  Agent System on port 10007             │
│                                         │
│  Tools Available:                       │
│  • file_reader / file_writer            │
│  • file_navigator                       │
│  • websearch                            │
│  • python_coder                         │
│  • rag                                  │
│  • shell_exec                           │
└─────────────────────────────────────────┘
```

## Troubleshooting

### "LLM 서버에 연결할 수 없어요"

Can't connect to LLM_API_fast:
1. `ps aux | grep run_backend` — Check if it's running
2. `echo $LLM_API_KEY` — Check env var is set
3. Check LLM_API_URL in config.py matches server

### Memory not updating

LLM not using file_writer:
1. Check PROMPT.md has clear instructions
2. Run `python test_llm.py` to test LLM
3. Check LLM_API_fast logs for tool errors

### Bot not responding

General issues:
1. Check `docker ps` or `ps aux` — Are all services running?
2. Check logs in terminal running hoonbot.py
3. Try sending a simple test message
4. Check config.py for correct ports

## Development

### Add New Feature

Since everything uses LLM_API_fast tools:
1. Update PROMPT.md with new instructions
2. No code changes needed
3. LLM will use appropriate tools automatically

Example: Add CSV analysis
- Just mention in PROMPT.md that LLM can use python_coder for CSV
- LLM will automatically use that tool when needed

### Modify Memory Format

Edit `data/memory.md` directly or update PROMPT.md guidance.
No code changes needed.

### Add New Webhook Source

No code changes—just post to `/webhook/incoming/<source>` and Hoonbot handles it.

## Performance Tips

1. **Keep memory.md reasonably sized** — It's included in every prompt
2. **Use file_navigator to explore** — Don't guess file paths
3. **Set reasonable timeouts** — Especially for python_coder tasks
4. **Cache tool results** — If running similar operations

## Security

- **API Key:** Stored in `data/.apikey`, keep it secret
- **Webhook Secret:** Use for external integrations
- **File Access:** LLM has access to files via tools, be careful with sensitive paths
- **Code Execution:** python_coder runs code, validate requests first

## Support

Check these files in order:
1. **ARCHITECTURE.md** — How does it work?
2. **PROMPT.md** — What are the guidelines?
3. **config.py** — Is it configured correctly?
4. **test_llm.py** — Can we reach the LLM?

## License & Credits

Hoonbot — Simplified AI Assistant for Huni

---

**Last Updated:** 2026-02-26
**Version:** 1.0 (Simplified Architecture)
