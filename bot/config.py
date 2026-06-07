"""Environment config. All env access goes through here."""
import os
from dotenv import load_dotenv

load_dotenv()


def _req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


DISCORD_TOKEN = _req("DISCORD_TOKEN")
DISCORD_GUILD_ID = int(_req("DISCORD_GUILD_ID"))
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "festival-admin")

SUPABASE_URL = _req("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _req("SUPABASE_SERVICE_KEY")

HEALTHCHECK_PORT = int(os.getenv("HEALTHCHECK_PORT", "8765"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

COUNTDOWN_HOUR = int(os.getenv("COUNTDOWN_HOUR", "9"))
COUNTDOWN_MINUTE = int(os.getenv("COUNTDOWN_MINUTE", "0"))
