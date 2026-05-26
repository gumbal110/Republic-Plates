import os
from dotenv import load_dotenv

load_dotenv("discord-bot/.env")


def require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Variable de entorno requerida no configurada: {key}\n"
            f"Asegúrate de haber configurado el archivo discord-bot/.env"
        )
    return val


DISCORD_TOKEN: str = require_env("DISCORD_TOKEN")

ADMIN_ROLE_NAME: str = os.getenv("ADMIN_ROLE_NAME", "Gobierno")

LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))
APPROVAL_CHANNEL_ID: int = int(os.getenv("APPROVAL_CHANNEL_ID", "0"))

GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))

BOT_COLOR: int = 0x002D62
SUCCESS_COLOR: int = 0x27AE60
ERROR_COLOR: int = 0xE74C3C
WARNING_COLOR: int = 0xF39C12
INFO_COLOR: int = 0x3498DB

PLATE_EMOJI: str = "🚗"
APPROVE_EMOJI: str = "✅"
REJECT_EMOJI: str = "❌"
PENDING_EMOJI: str = "⏳"
REVOKE_EMOJI: str = "🔒"
LOG_EMOJI: str = "📋"
