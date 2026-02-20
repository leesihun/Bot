#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Load Settings ---
SETTINGS="$SCRIPT_DIR/settings.txt"
if [ -f "$SETTINGS" ]; then
    source "$SETTINGS"
else
    # Fallback defaults if settings.txt is missing
    USE_CLOUDFLARE=true
fi

pkill -f "ClaudeCodeWrapper" 2>/dev/null
pkill -f "Messenger" 2>/dev/null

if [ "$USE_CLOUDFLARE" = "true" ]; then
    pkill -f "cloudflared" 2>/dev/null
    echo "ClaudeCodeWrapper, Messenger, and cloudflared have been closed."
else
    echo "ClaudeCodeWrapper and Messenger have been closed."
fi
