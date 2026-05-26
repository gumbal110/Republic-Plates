import os
from dotenv import load_dotenv

load_dotenv("discord-bot/.env")


def require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Variable de entorno requerida no configurada: {key}\n"
            f"Asegúrate de que el secreto está configurado en Replit."
        )
    return val


DISCORD_TOKEN: str = require_env("DISCORD_TOKEN")

GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))

REVIEW_CHANNEL_ID:     int = int(os.getenv("REVIEW_CHANNEL_ID", "0"))
ACTIVITIES_CHANNEL_ID: int = int(os.getenv("ACTIVITIES_CHANNEL_ID", "0"))

# Embed colors
COLOR_NAVY:    int = 0x001F5B
COLOR_GREEN:   int = 0x1E8449
COLOR_RED:     int = 0xC0392B
COLOR_GOLD:    int = 0xD4AC0D
COLOR_GREY:    int = 0x616A6B
COLOR_INFO:    int = 0x1A5276

BADGE_REGEX = r"^PN-\d{3,6}$"
