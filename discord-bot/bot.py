"""
Bot Institucional — Policía Nacional de la República Dominicana
===============================================================
Oficiales:
  /solicitar_placa         — Solicitar asignación de placa
  /turno iniciar           — Iniciar turno con temporizador en vivo
  /turno ver               — Ver todos los turnos activos
  /actividad registrar     — Registrar actividad con 4 imágenes

Administrativos:
  /config_roles            — Configurar roles con permisos
  /limpiar_placa           — Eliminar placa de un oficial
  /ver_placas              — Panel paginado de placas activas
  /buscar_placa            — Buscar placa por número
"""

import logging
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

logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)


# ------------------------------------------------------------------ #
#  Bot                                                                 #
# ------------------------------------------------------------------ #

intents = discord.Intents.default()
intents.guilds = True
intents.members = True


class PNBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.placas")
        await self.load_extension("cogs.admin")
        await self.load_extension("cogs.turnos")
        await self.load_extension("cogs.actividad")
        logger.info("Cogs cargados: placas, admin, turnos, actividad")

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash commands sincronizados al servidor %d.", config.GUILD_ID)
        else:
            await self.tree.sync()
            logger.info("Slash commands sincronizados globalmente.")

    async def on_ready(self) -> None:
        logger.info("=" * 55)
        logger.info("  Bot conectado: %s  (ID: %s)", self.user, self.user.id)
        logger.info("  Servidores activos: %d", len(self.guilds))
        logger.info("=" * 55)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="el Registro Institucional PN 🚔",
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.error(
            "Error en comando '%s': %s",
            getattr(interaction.command, "name", "?"),
            error,
            exc_info=True,
        )
        embed = discord.Embed(
            title="❌ Error Inesperado",
            description="Ocurrió un error al procesar el comando. Inténtalo nuevamente.",
            color=config.COLOR_RED,
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass


# ------------------------------------------------------------------ #
#  Entry point                                                         #
# ------------------------------------------------------------------ #

def main() -> None:
    db.init_db()
    bot = PNBot()
    try:
        bot.run(config.DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Token de Discord inválido. Verifica el secreto DISCORD_TOKEN.")
        sys.exit(1)
    except Exception as e:
        logger.critical("Error crítico al iniciar el bot: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
