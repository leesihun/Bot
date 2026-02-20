#!/bin/bash

echo "=========================================="
echo "  AIhoonbot.com - Starting All Services"
echo "=========================================="
echo

CLOUDFLARED="$HOME/.cloudflared/cloudflared"

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python is not installed or not in PATH."
    read -p "Press Enter to exit..."
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed or not in PATH."
    read -p "Press Enter to exit..."
    exit 1
fi

if [ ! -f "$CLOUDFLARED" ]; then
    echo "[ERROR] cloudflared not found. Run tunnel-setup.sh first."
    read -p "Press Enter to exit..."
    exit 1
fi

if [ ! -f "$HOME/.cloudflared/config.yml" ]; then
    echo "[ERROR] Tunnel config not found. Run tunnel-setup.sh first."
    read -p "Press Enter to exit..."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

echo "[1/3] Starting ClaudeCodeWrapper (port 8000)..."
gnome-terminal --tab --title="ClaudeCodeWrapper" -- bash -c "cd '$SCRIPT_DIR/ClaudeCodeWrapper' && python3 run.py; exec bash"

echo "[2/3] Starting Messenger (port 3000)..."
gnome-terminal --tab --title="Messenger" -- bash -c "cd '$SCRIPT_DIR/Messenger' && npm run dev:server; exec bash"

echo
echo "Waiting for services to start..."
sleep 4

echo "[3/3] Starting Cloudflare Tunnel..."
gnome-terminal --tab --title="Cloudflare Tunnel" -- bash -c "'$CLOUDFLARED' tunnel run aihoonbot; exec bash"

echo
echo "=========================================="
echo "  All services launched!"
echo
echo "  Messenger:          https://aihoonbot.com"
echo "  ClaudeCodeWrapper:  https://aihoonbot.com/claude"
echo
echo "  Local access:"
echo "    Messenger:         http://localhost:3000"
echo "    ClaudeCodeWrapper: http://localhost:8000"
echo "=========================================="
echo
echo "You can close this window."
sleep 10
