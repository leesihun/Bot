import os

# --- Hoonbot server ---
HOONBOT_PORT = int(os.environ.get("HOONBOT_PORT", 3939))
HOONBOT_HOST = "0.0.0.0"

# --- Messenger ---
MESSENGER_PORT = int(os.environ.get("MESSENGER_PORT", 3000))
MESSENGER_URL = f"http://localhost:{MESSENGER_PORT}"
MESSENGER_BOT_NAME = "Hoonbot"
MESSENGER_API_KEY = ""  # Populated at runtime after bot registration; persisted in DB
MESSENGER_HOME_ROOM_ID = int(os.environ.get("HOONBOT_HOME_ROOM_ID", 1))

# --- LLM API ---
LLM_API_PORT = int(os.environ.get("LLM_API_PORT", 10007))
LLM_API_URL = f"http://localhost:{LLM_API_PORT}"
LLM_API_AGENT_TYPE = "auto"  # chat | react | plan_execute | auto

# --- Storage ---
SOUL_PATH = os.path.join(os.path.dirname(__file__), "SOUL.md")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "hoonbot.db")
MAX_HISTORY_MESSAGES = 50  # Per room

# --- Heartbeat ---
HEARTBEAT_ENABLED = os.environ.get("HOONBOT_HEARTBEAT_ENABLED", "true").lower() == "true"
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("HOONBOT_HEARTBEAT_INTERVAL", 3600))
