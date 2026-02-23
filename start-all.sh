#!/bin/bash

echo "=========================================="
echo "  AIhoonbot.com - Starting All Services"
echo "=========================================="
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Load Settings ---
SETTINGS="$SCRIPT_DIR/settings.txt"
if [ ! -f "$SETTINGS" ]; then
    echo "[ERROR] settings.txt not found. Expected at: $SETTINGS"
    read -p "Press Enter to exit..."
    exit 1
fi
source "$SETTINGS"

# --- Required: Python3 ---
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python is not installed or not in PATH."
    read -p "Press Enter to exit..."
    exit 1
fi

# --- Required: Node.js ---
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed or not in PATH."
    read -p "Press Enter to exit..."
    exit 1
fi

# --- Optional: OpenCode CLI check ---
if [ "$CHECK_OPENCODE" = "true" ]; then
    if ! command -v "$OPENCODE_CMD" &> /dev/null; then
        echo "[WARN] '$OPENCODE_CMD' command not found. /opencode terminal will not work."
        echo "       Install opencode or set OPENCODE_CMD in settings.txt."
        echo
    fi
fi

# --- Cloudflare checks (only if enabled) ---
if [ "$USE_CLOUDFLARE" = "true" ]; then
    if [ ! -f "$CLOUDFLARED_BIN" ]; then
        echo "[ERROR] cloudflared not found at: $CLOUDFLARED_BIN"
        echo "        Run tunnel-setup.sh first, or set USE_CLOUDFLARE=false in settings.txt."
        read -p "Press Enter to exit..."
        exit 1
    fi
    if [ ! -f "$CLOUDFLARED_CONFIG" ]; then
        echo "[ERROR] Tunnel config not found at: $CLOUDFLARED_CONFIG"
        echo "        Run tunnel-setup.sh first, or set USE_CLOUDFLARE=false in settings.txt."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# --- npm install if needed ---
if [ ! -d "$SCRIPT_DIR/Messenger/node_modules" ]; then
    echo "[0/5] node_modules not found. Running npm install..."
    cd "$SCRIPT_DIR/Messenger"
    npm install
    if [ $? -ne 0 ]; then
        echo "[ERROR] npm install failed."
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "[OK] npm install done."
    echo
fi

# --- Build Messenger web client if needed ---
if [ ! -f "$SCRIPT_DIR/Messenger/client/dist-web/index.html" ]; then
    echo "[0/5] Building Messenger web client..."
    cd "$SCRIPT_DIR/Messenger"
    npm run build:web
    if [ $? -ne 0 ]; then
        echo "[ERROR] Messenger web client build failed."
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "[OK] Web client built."
    echo
fi

# --- Log directory ---
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# --- Start Services ---
LLM_API_DIR="$SCRIPT_DIR/../LLM_API"

if [ -d "$LLM_API_DIR" ]; then
    echo "[1/5] Starting LLM API tools server (port $LLM_API_TOOLS_PORT)..."
    cd "$LLM_API_DIR" && python3 tools_server.py > "$LOG_DIR/llm_tools.log" 2>&1 &
    sleep 2

    echo "[2/5] Starting LLM API main server (port $LLM_API_PORT)..."
    cd "$LLM_API_DIR" && python3 run_backend.py > "$LOG_DIR/llm_api.log" 2>&1 &
else
    echo "[1/5] LLM API not found at $LLM_API_DIR — skipping."
    echo "[2/5] LLM API not found — skipping."
fi

echo "[3/5] Starting Messenger (port $MESSENGER_PORT)..."
cd "$SCRIPT_DIR/Messenger" && npm run dev:server > "$LOG_DIR/messenger.log" 2>&1 &

echo "[4/5] Starting Hoonbot (port $HOONBOT_PORT)..."
cd "$SCRIPT_DIR/Hoonbot" && python3 hoonbot.py > "$LOG_DIR/hoonbot.log" 2>&1 &

echo "[5/5] Starting ClaudeCodeWrapper (port $CLAUDE_WRAPPER_PORT)..."
cd "$SCRIPT_DIR/ClaudeCodeWrapper" && python3 run.py > "$LOG_DIR/claude_wrapper.log" 2>&1 &

echo
echo "Waiting for services to start..."
sleep 4

if [ "$USE_CLOUDFLARE" = "true" ]; then
    echo "Starting Cloudflare Tunnel ($CLOUDFLARE_TUNNEL_NAME)..."
    "$CLOUDFLARED_BIN" tunnel run $CLOUDFLARE_TUNNEL_NAME > "$LOG_DIR/cloudflare.log" 2>&1 &
else
    echo "Cloudflare disabled (USE_CLOUDFLARE=false in settings.txt). Skipping."
fi

echo
echo "=========================================="
echo "  All services launched!"
echo
if [ "$USE_CLOUDFLARE" = "true" ]; then
    echo "  Messenger:          https://aihoonbot.com"
    echo "  ClaudeCodeWrapper:  https://aihoonbot.com/claude"
    echo "  OpenCode:           https://aihoonbot.com/opencode"
    echo
fi
echo "  Local access:"
echo "    LLM API:           http://localhost:$LLM_API_PORT"
echo "    Messenger:         http://localhost:$MESSENGER_PORT"
echo "    Hoonbot:           http://localhost:$HOONBOT_PORT"
echo "    ClaudeCodeWrapper: http://localhost:$CLAUDE_WRAPPER_PORT"
echo "    OpenCode:          http://localhost:$MESSENGER_PORT/opencode"
echo "=========================================="
echo
echo "  Logs: $LOG_DIR/"
echo "=========================================="
echo
echo "All services running in background. Press Ctrl+C to stop all."
wait
