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

# --- Build Messenger web client if needed ---
if [ ! -f "$SCRIPT_DIR/Messenger/client/dist-web/index.html" ]; then
    echo "[0/3] Building Messenger web client..."
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

# --- Start Services ---
echo "[1/3] Starting ClaudeCodeWrapper (port $CLAUDE_WRAPPER_PORT)..."
gnome-terminal --tab --title="ClaudeCodeWrapper" -- bash -c "cd '$SCRIPT_DIR/ClaudeCodeWrapper' && python3 run.py; exec bash"

echo "[2/3] Starting Messenger (port $MESSENGER_PORT)..."
gnome-terminal --tab --title="Messenger" -- bash -c "cd '$SCRIPT_DIR/Messenger' && npm run dev:server; exec bash"

echo
echo "Waiting for services to start..."
sleep 4

if [ "$USE_CLOUDFLARE" = "true" ]; then
    echo "[3/3] Starting Cloudflare Tunnel ($CLOUDFLARE_TUNNEL_NAME)..."
    gnome-terminal --tab --title="Cloudflare Tunnel" -- bash -c "'$CLOUDFLARED_BIN' tunnel run $CLOUDFLARE_TUNNEL_NAME; exec bash"
else
    echo "[3/3] Cloudflare disabled (USE_CLOUDFLARE=false in settings.txt). Skipping."
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
echo "    Messenger:         http://localhost:$MESSENGER_PORT"
echo "    ClaudeCodeWrapper: http://localhost:$CLAUDE_WRAPPER_PORT"
echo "    OpenCode:          http://localhost:$MESSENGER_PORT/opencode"
echo "=========================================="
echo
echo "You can close this window."
sleep 10
