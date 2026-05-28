"""
Comandos administrativos:
  /limpiar_placa   — eliminar la placa de un oficial
  /ver_placas      — panel paginado de todas las placas
  /buscar_placa    — buscar placa por número
  /estadisticas    — estadísticas del sistema

  Para configurar roles usa /config
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from cogs.views import PlacasView, member_has_action, clear_badge_nickname, _send_log_embed

logger = logging.getLogger(__name__)


class Admin(commands.Cog, name="Administración"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------------------------------------------------- #
    #  /limpiar_placa                                                   #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="limpiar_placa",
        description="[ADMIN] Elimina la placa institucional asignada a un oficial.",
    )
    @app_commands.describe(oficial="El oficial al que se le removerá la placa")
    async def limpiar_placa(
        self, interaction: discord.Interaction, oficial: discord.Member
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "eliminar"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="No tienes el rol necesario para eliminar placas.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        removed = db.remove_badge(
            user_id=str(oficial.id),
            removed_by=str(interaction.user.id),
            removed_by_name=str(interaction.user),
        )

        if not removed:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Sin Placa Asignada",
                    description=f"{oficial.mention} no tiene ninguna placa registrada.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        # Clear nickname immediately
        await clear_badge_nickname(oficial, channel=interaction.channel)

        embed = discord.Embed(
            title="🗑️ Placa Eliminada del Registro",
            color=config.COLOR_RED,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Placa", value=f"`{removed['badge_number']}`", inline=True)
        embed.add_field(name="Oficial", value=oficial.mention, inline=True)
        embed.add_field(name="Eliminado por", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Policía Nacional · Registro Institucional")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await _send_log_embed(
            interaction.guild,
            title="Placa eliminada",
            description=(
                f"{interaction.user.mention} elimino la placa **{removed['badge_number']}** "
                f"de {oficial.mention}."
            ),
            color=config.COLOR_RED,
        )

        try:
            dm_embed = discord.Embed(
                title="🔒 Placa Revocada",
                description=(
                    f"Tu placa institucional **{removed['badge_number']}** ha sido "
                    "eliminada del registro por un superior.\n"
                    "Contacta a la Dirección de Recursos Humanos para más información."
                ),
                color=config.COLOR_RED,
                timestamp=datetime.utcnow(),
            )
            dm_embed.set_footer(text="Policía Nacional · República Dominicana")
            await oficial.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        logger.info("Placa %s eliminada de %s por %s", removed["badge_number"], oficial, interaction.user)

    # ---------------------------------------------------------------- #
    #  /ver_placas                                                      #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="ver_placas",
        description="[ADMIN] Muestra el registro paginado de todas las placas activas.",
    )
    async def ver_placas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "ver"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="No tienes el rol necesario para ver el registro completo.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        badges = db.get_all_badges()
        view = PlacasView(badges)
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    # ---------------------------------------------------------------- #
    #  /buscar_placa                                                    #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="buscar_placa",
        description="[ADMIN] Busca información de una placa por su número.",
    )
    @app_commands.describe(numero="Número de placa a buscar (ej: PN-025)")
    async def buscar_placa(
        self, interaction: discord.Interaction, numero: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        badge = db.get_badge_by_number(numero.strip().upper())

        if not badge:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Placa No Encontrada",
                    description=(
                        f"La placa **`{numero.upper()}`** no existe en el registro institucional.\n"
                        "Verifica el número e inténtalo nuevamente."
                    ),
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🔍 Información de Placa `{badge['badge_number']}`",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Número de Placa", value=f"`{badge['badge_number']}`", inline=True)
        embed.add_field(name="Oficial Asignado", value=f"<@{badge['user_id']}>", inline=True)
        embed.add_field(name="Usuario", value=badge["username"], inline=True)
        embed.add_field(name="Estado", value="✅ Activa", inline=True)
        embed.add_field(name="Asignada por", value=badge["assigned_by"], inline=True)
        embed.add_field(name="Fecha de Emisión", value=badge["assigned_at"][:10], inline=True)
        embed.set_footer(text="Policía Nacional · Dirección de Recursos Humanos")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------------------------------------------------------------- #
    #  /estadisticas                                                    #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="estadisticas",
        description="[ADMIN] Muestra estadísticas del sistema de placas.",
    )
    async def estadisticas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "ver"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="No tienes el rol necesario para ver estadísticas.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        badges = db.get_all_badges()
        embed = discord.Embed(
            title="📊 Estadísticas del Sistema",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="🪪 Placas Activas", value=str(len(badges)), inline=True)
        embed.set_footer(text="Policía Nacional · Dirección de Recursos Humanos")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
