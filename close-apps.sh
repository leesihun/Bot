#!/bin/bash

pkill -f "ClaudeCodeWrapper" 2>/dev/null
pkill -f "Messenger" 2>/dev/null
pkill -f "cloudflared" 2>/dev/null
echo "ClaudeCodeWrapper, Messenger, and cloudflared have been closed."
