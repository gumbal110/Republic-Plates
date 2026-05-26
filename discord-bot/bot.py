"""
Bot de Registro de Placas Vehiculares
República Dominicana · Sistema de Roleplay

Comandos de usuario:
  /solicitar_placa   — Solicitar registro de una nueva placa
  /mis_placas        — Ver tus placas activas
  /mis_solicitudes   — Ver historial de solicitudes
  /consultar_placa   — Consultar info de cualquier placa

Comandos administrativos (requieren rol configurado en ADMIN_ROLE_NAME):
  /ver_solicitudes     — Listar solicitudes pendientes
  /aprobar_solicitud   — Aprobar solicitud y asignar placa
  /rechazar_solicitud  — Rechazar solicitud con motivo
  /revocar_placa       — Revocar una placa activa
  /buscar_placa        — Búsqueda completa de placa
  /estadisticas        — Estadísticas del sistema
"""

import asyncio
import logging
import os
import sys

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db

# ------------------------------------------------------------------ #
#  Logging                                                             #
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("discord-bot/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")

# Reduce noise from discord.py internals
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)


# ------------------------------------------------------------------ #
#  Bot Setup                                                           #
# ------------------------------------------------------------------ #
intents = discord.Intents.default()
intents.guilds = True
intents.members = True


class PlacasBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.plates")
        await self.load_extension("cogs.admin")
        logger.info("Cogs cargados.")

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Comandos sincronizados al servidor %d.", config.GUILD_ID)
        else:
            await self.tree.sync()
            logger.info("Comandos sincronizados globalmente (puede tardar hasta 1 hora).")

    async def on_ready(self) -> None:
        logger.info("=" * 50)
        logger.info("Bot conectado como: %s (ID: %s)", self.user, self.user.id)
        logger.info("Servidores: %d", len(self.guilds))
        logger.info("=" * 50)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="el Registro Vehicular RD 🚗",
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.error("Error en comando '%s': %s", interaction.command, error, exc_info=True)
        msg = discord.Embed(
            title="❌ Error Inesperado",
            description="Ocurrió un error al procesar el comando. Inténtalo de nuevo.",
            color=config.ERROR_COLOR,
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=msg, ephemeral=True)
            else:
                await interaction.response.send_message(embed=msg, ephemeral=True)
        except Exception:
            pass


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #
def main() -> None:
    db.init_db()
    logger.info("Base de datos inicializada en discord-bot/placas_rd.db")

    bot = PlacasBot()

    try:
        bot.run(config.DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Token de Discord inválido. Verifica la variable DISCORD_TOKEN.")
        sys.exit(1)
    except Exception as e:
        logger.critical("Error crítico al iniciar el bot: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
